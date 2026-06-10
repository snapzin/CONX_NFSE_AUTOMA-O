// Clientes por maquina.
// Chamado pelo app: POST {op:"get"|"save", key, machine_id, clientes?}
// Guarda em Redis separado por licenca + maquina.
import crypto from 'crypto';
import {
  getRecord, saveRecord, normalizeKey, maskKey, setCors, setSecurityHeaders,
  rateLimit, clientIp, redis,
} from './_lib.js';

const CONTACT = 'zayonantunes@gmail.com';
const MAX_CLIENTES = 5000;

function isMachineBlocked(machine) {
  return machine?.status === 'blocked';
}

function activeMachineCount(machines) {
  return Object.values(machines || {}).filter((m) => !isMachineBlocked(m)).length;
}

function clientesPath(key, machineId) {
  const keyHash = crypto.createHash('sha256').update(key).digest('hex').slice(0, 24);
  return `clientes:${keyHash}:${machineId}`;
}

function normalizeClientes(items) {
  const out = [];
  for (const item of Array.isArray(items) ? items : []) {
    if (!item || typeof item !== 'object') continue;
    const documento = String(item.documento || '').replace(/\D/g, '').slice(0, 32);
    const nome = String(item.nome || '').trim().slice(0, 200);
    if (documento || nome) out.push({ documento, nome });
    if (out.length >= MAX_CLIENTES) break;
  }
  return out;
}

async function ensureLicensedMachine(key, machineId) {
  const rec = await getRecord(key);
  if (!rec) {
    return { ok: false, status: 402, message: `Chave invalida ou expirada. Entre em contato: ${CONTACT}` };
  }
  if (rec.status === 'blocked') {
    return { ok: false, status: 402, message: `Licenca bloqueada. Entre em contato: ${CONTACT}` };
  }
  if (rec.expiresAt && Date.now() > new Date(rec.expiresAt).getTime()) {
    return {
      ok: false,
      status: 402,
      message: `Licenca expirada em ${new Date(rec.expiresAt).toLocaleDateString('pt-BR')}. Contato: ${CONTACT}`,
    };
  }

  const machines = rec.machines || {};
  const max = Number(rec.maxMachines || 1);
  const nowIso = new Date().toISOString();

  if (isMachineBlocked(machines[machineId])) {
    return { ok: false, status: 402, message: `Esta maquina foi bloqueada para esta licenca. Contato: ${CONTACT}` };
  }

  if (machines[machineId]) {
    machines[machineId].lastSeen = nowIso;
    machines[machineId].status = machines[machineId].status || 'active';
  } else if (activeMachineCount(machines) < max) {
    machines[machineId] = { firstSeen: nowIso, lastSeen: nowIso, status: 'active' };
  } else {
    return { ok: false, status: 402, message: `Limite de ${max} maquina(s) atingido para esta licenca. Contato: ${CONTACT}` };
  }

  rec.machines = machines;
  rec.lastSeen = nowIso;
  return { ok: true, rec, nowIso };
}

export default async function handler(req, res) {
  setSecurityHeaders(res);
  setCors(req, res);
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') {
    return res.status(405).json({ ok: false, message: 'Metodo nao permitido' });
  }

  const CLIENT_SECRET = process.env.CLIENT_SECRET;
  if (CLIENT_SECRET && (req.headers['x-client-secret'] || '') !== CLIENT_SECRET) {
    return res.status(403).json({ ok: false, message: 'Acesso nao autorizado' });
  }

  if (await rateLimit(`clientes:ip:${clientIp(req)}`, 120, 60)) {
    return res.status(429).json({ ok: false, message: 'Muitas requisicoes. Tente novamente.' });
  }

  if (!redis()) {
    return res.status(500).json({ ok: false, message: 'Banco (Upstash Redis) nao configurado.' });
  }

  const body = req.body || {};
  const op = String(body.op || 'get').toLowerCase();
  const key = normalizeKey(body.key);
  const machineId = String(body.machine_id || '').trim().toLowerCase();

  if (!key) return res.status(400).json({ ok: false, message: 'Chave nao informada.' });
  if (!/^[a-f0-9]{32}$/.test(machineId)) {
    return res.status(400).json({ ok: false, message: 'Identificador de maquina invalido.' });
  }
  if (!['get', 'save'].includes(op)) {
    return res.status(400).json({ ok: false, message: `Operacao desconhecida: ${op}` });
  }

  try {
    const licensed = await ensureLicensedMachine(key, machineId);
    if (!licensed.ok) {
      return res.status(licensed.status || 402).json({ ok: false, message: licensed.message });
    }

    const r = redis();
    const dataKey = clientesPath(key, machineId);
    const location = `Servidor: maquina ${machineId.slice(0, 8)} (${maskKey(key)})`;

    if (op === 'get') {
      const saved = await r.get(dataKey);
      const data = typeof saved === 'string' ? JSON.parse(saved) : saved;
      await saveRecord(key, licensed.rec);
      return res.status(200).json({
        ok: true,
        clientes: normalizeClientes(data?.clientes || []),
        salvos: Number(data?.clientes?.length || 0),
        machine_id: machineId,
        updatedAt: data?.updatedAt || null,
        location,
        path: location,
      });
    }

    const clientes = normalizeClientes(body.clientes || []);
    const updatedAt = new Date().toISOString();
    await r.set(dataKey, JSON.stringify({ clientes, updatedAt }));
    licensed.rec.machines[machineId].clientCount = clientes.length;
    licensed.rec.machines[machineId].clientsUpdatedAt = updatedAt;
    await saveRecord(key, licensed.rec);

    return res.status(200).json({
      ok: true,
      clientes,
      salvos: clientes.length,
      machine_id: machineId,
      updatedAt,
      location,
      path: location,
    });
  } catch (err) {
    console.error('clientes error:', err?.message);
    return res.status(500).json({ ok: false, message: String(err?.message || err) });
  }
}
