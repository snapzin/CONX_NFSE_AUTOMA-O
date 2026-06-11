// Valida chaves de licenca NFSe Automacao.
// Chamado pelo app: POST {key, machine_id} + header x-client-secret -> {valid, message}
//
// Env no Vercel:
//   CLIENT_SECRET  = mesmo valor de _CLIENT_SECRET em api/license.py (opcional)
//   VALID_KEYS / ALLOW_LEGACY_KEYS=1 = chaves legadas (opcional e desativado por padrao)
//   UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN = banco (Upstash)
import crypto from 'crypto';
import {
  getRecord, saveRecord, legacyKeys, normalizeKey, setCors, setSecurityHeaders,
  rateLimit, clientIp,
} from './_lib.js';

const CONTACT = 'zayonantunes@gmail.com';

function isMachineBlocked(machine) {
  return machine?.status === 'blocked';
}

function activeMachineCount(machines) {
  return Object.values(machines || {}).filter((m) => !isMachineBlocked(m)).length;
}

export default async function handler(req, res) {
  setSecurityHeaders(res);
  setCors(req, res);
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') {
    return res.status(405).json({ valid: false, message: 'Metodo nao permitido' });
  }

  // Verificacao do segredo do cliente (se configurado).
  const CLIENT_SECRET = process.env.CLIENT_SECRET;
  if (CLIENT_SECRET) {
    if ((req.headers['x-client-secret'] || '') !== CLIENT_SECRET) {
      return res.status(403).json({ valid: false, message: 'Acesso nao autorizado' });
    }
  }

  const ip = clientIp(req);
  if (await rateLimit(`validate:ip:${ip}`, 80, 60)) {
    return res.status(429).json({ valid: false, message: 'Muitas requisicoes. Tente novamente.' });
  }

  const { key, machine_id } = req.body || {};
  if (!key) return res.status(400).json({ valid: false, message: 'Chave nao informada' });

  const k = normalizeKey(key);
  const keyHash = crypto.createHash('sha256').update(k).digest('hex').slice(0, 16);
  if (await rateLimit(`validate:key:${keyHash}`, 20, 60)) {
    return res.status(429).json({ valid: false, message: 'Muitas tentativas para esta chave. Tente novamente.' });
  }
  const mid = String(machine_id || '').trim().toLowerCase();
  if (!/^[a-f0-9]{32}$/.test(mid)) {
    return res.status(400).json({ valid: false, message: 'Identificador de maquina invalido' });
  }
  const inval = (msg) => res.status(200).json({ valid: false, message: msg });

  try {
    const rec = await getRecord(k);

    // Fallback legado: chave em VALID_KEYS (sem vinculo/validade).
    if (!rec) {
      if (legacyKeys().includes(k)) {
        return res.status(200).json({ valid: true, message: 'Licenca valida.' });
      }
      return inval(`Chave invalida ou expirada. Entre em contato: ${CONTACT}`);
    }

    if (rec.status === 'blocked') {
      return inval(`Licenca bloqueada. Entre em contato: ${CONTACT}`);
    }
    if (rec.expiresAt && Date.now() > new Date(rec.expiresAt).getTime()) {
      return inval(`Licenca expirada em ${new Date(rec.expiresAt).toLocaleDateString('pt-BR')}. Contato: ${CONTACT}`);
    }

    // Vinculo de maquina.
    const machines = rec.machines || {};
    const max = Number(rec.maxMachines || 1);
    const nowIso = new Date().toISOString();

    if (isMachineBlocked(machines[mid])) {
      return inval(`Esta maquina foi bloqueada para esta licenca. Contato: ${CONTACT}`);
    }

    if (machines[mid]) {
      machines[mid].lastSeen = nowIso;
      machines[mid].status = machines[mid].status || 'active';
    } else if (activeMachineCount(machines) < max) {
      machines[mid] = { firstSeen: nowIso, lastSeen: nowIso, status: 'active' };
    } else {
      return inval(`Limite de ${max} maquina(s) atingido para esta licenca. Contato: ${CONTACT}`);
    }

    rec.machines = machines;
    rec.lastSeen = nowIso;
    await saveRecord(k, rec);

    return res.status(200).json({ valid: true, message: 'Licenca valida.' });
  } catch (err) {
    // Se o banco falhar, tenta o fallback legado para nao derrubar clientes.
    if (legacyKeys().includes(k)) {
      return res.status(200).json({ valid: true, message: 'Licenca valida.' });
    }
    console.error('validate error:', err?.message);
    return inval('Servidor de licencas indisponivel. Tente novamente.');
  }
}
