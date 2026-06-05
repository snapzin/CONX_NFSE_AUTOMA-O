// Valida chaves de licenca NFSe Automacao.
// Chamado pelo app: POST {key, machine_id, machine_name} + header x-client-secret
//
// Env no Vercel:
//   CLIENT_SECRET  = mesmo valor de _CLIENT_SECRET em api/license.py (opcional)
//   VALID_KEYS     = chaves legadas (compat com versao antiga; opcional)
//   UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN = banco (Upstash)
import {
  getRecord, saveRecord, LEGACY_KEYS, normalizeKey, setCors,
} from './_lib.js';

const CONTACT = 'zayonantunes@gmail.com';

// Rate limiting em memoria por instancia Lambda.
// Mapa: ip -> { count, start }
const _hits    = new Map();
const MAX_RPS  = 30;
const WIN_MS   = 60_000;
const MAX_IPS  = 500; // limite para evitar crescimento ilimitado do Map

function _isRateLimited(ip) {
  const now = Date.now();
  // Limpa entradas expiradas quando o Map chega ao limite
  if (_hits.size >= MAX_IPS) {
    for (const [k, v] of _hits) {
      if (now - v.start > WIN_MS) _hits.delete(k);
    }
  }
  const e = _hits.get(ip) || { count: 0, start: now };
  if (now - e.start > WIN_MS) {
    _hits.set(ip, { count: 1, start: now });
    return false;
  }
  e.count++;
  _hits.set(ip, e);
  return e.count > MAX_RPS;
}

export default async function handler(req, res) {
  setCors(res);
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') {
    return res.status(405).json({ valid: false, message: 'Metodo nao permitido' });
  }

  const CLIENT_SECRET = process.env.CLIENT_SECRET;
  if (CLIENT_SECRET && (req.headers['x-client-secret'] || '') !== CLIENT_SECRET) {
    return res.status(403).json({ valid: false, message: 'Acesso nao autorizado' });
  }

  const ip = req.headers['x-forwarded-for']?.split(',')[0]?.trim() || 'unknown';
  if (_isRateLimited(ip)) {
    return res.status(429).json({ valid: false, message: 'Muitas requisicoes. Tente novamente.' });
  }

  const { key, machine_id, machine_name } = req.body || {};
  if (!key) return res.status(400).json({ valid: false, message: 'Chave nao informada' });

  const k     = normalizeKey(key);
  const mid   = String(machine_id || 'unknown');
  const mname = String(machine_name || '').trim().slice(0, 64);
  const inval = (msg) => res.status(200).json({ valid: false, message: msg });

  try {
    const rec = await getRecord(k);

    if (!rec) {
      return LEGACY_KEYS.includes(k)
        ? res.status(200).json({ valid: true, message: 'Licenca valida.' })
        : inval(`Chave invalida ou expirada. Entre em contato: ${CONTACT}`);
    }

    if (rec.status === 'blocked') {
      return inval(`Licenca bloqueada. Entre em contato: ${CONTACT}`);
    }
    if (rec.expiresAt && Date.now() > Date.parse(rec.expiresAt)) {
      return inval(`Licenca expirada em ${new Date(rec.expiresAt).toLocaleDateString('pt-BR')}. Contato: ${CONTACT}`);
    }

    const machines = rec.machines || {};
    const max      = Number(rec.maxMachines || 1);
    const nowIso   = new Date().toISOString();

    if (machines[mid]) {
      machines[mid].lastSeen = nowIso;
      machines[mid].ip       = ip;
      if (mname) machines[mid].name = mname;
    } else if (Object.keys(machines).length < max) {
      machines[mid] = { firstSeen: nowIso, lastSeen: nowIso, ip, name: mname || null };
    } else {
      return inval(`Limite de ${max} maquina(s) atingido para esta licenca. Contato: ${CONTACT}`);
    }

    rec.machines = machines;
    rec.lastSeen = nowIso;
    await saveRecord(k, rec);

    return res.status(200).json({ valid: true, message: 'Licenca valida.' });
  } catch (err) {
    if (LEGACY_KEYS.includes(k)) {
      return res.status(200).json({ valid: true, message: 'Licenca valida.' });
    }
    console.error('validate error:', err?.message);
    return inval('Servidor de licencas indisponivel. Tente novamente.');
  }
}
