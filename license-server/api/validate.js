// Vercel serverless function — valida chaves de licença NFSe Automação
// Deploy: vercel --prod (dentro de license-server/)
//
// Variáveis de ambiente no Vercel:
//   VALID_KEYS     = "CHAVE1,CHAVE2,CHAVE3"  (sem espaços, maiúsculas, sem traços)
//   ADMIN_TOKEN    = "token-secreto-para-gerenciar"
//   CLIENT_SECRET  = "mesmo valor que _CLIENT_SECRET em api/license.py"

const CONTACT = 'zayonantunes@gmail.com';

// Rate limiting em memória (por invocação Lambda — redefine a cada cold start)
// Bloqueia IPs que excedem MAX_REQ_PER_IP requisições na janela WINDOW_MS
const _hits = new Map();
const MAX_REQ_PER_IP = 30;
const WINDOW_MS = 60_000;

function _isRateLimited(ip) {
  const now = Date.now();
  const entry = _hits.get(ip) || { count: 0, start: now };
  if (now - entry.start > WINDOW_MS) {
    _hits.set(ip, { count: 1, start: now });
    return false;
  }
  entry.count++;
  _hits.set(ip, entry);
  return entry.count > MAX_REQ_PER_IP;
}

export default function handler(req, res) {
  setCorsHeaders(res);

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') {
    return res.status(405).json({ valid: false, message: 'Método não permitido' });
  }

  // ── Verificação do CLIENT_SECRET ─────────────────────────────────────────
  const CLIENT_SECRET = process.env.CLIENT_SECRET;
  if (CLIENT_SECRET) {
    const clientSecret = req.headers['x-client-secret'] || '';
    if (!clientSecret || clientSecret !== CLIENT_SECRET) {
      return res.status(403).json({ valid: false, message: 'Acesso não autorizado' });
    }
  }

  // ── Rate limiting por IP ─────────────────────────────────────────────────
  const ip = req.headers['x-forwarded-for']?.split(',')[0]?.trim() || 'unknown';
  if (_isRateLimited(ip)) {
    return res.status(429).json({ valid: false, message: 'Muitas requisições. Tente novamente.' });
  }

  const { key, machine_id, action, show_keys } = req.body || {};

  if (action === 'admin') return handleAdmin(req, res, show_keys);

  if (!key) {
    return res.status(400).json({ valid: false, message: 'Chave não informada' });
  }

  const normalized = normalizeKey(key);
  const isValid = getValidKeys().includes(normalized);

  console.log(JSON.stringify({
    ts: new Date().toISOString(),
    key_prefix: normalized.slice(0, 6) + '...',
    machine_id: machine_id || 'unknown',
    ip,
    valid: isValid,
  }));

  return res.status(200).json(
    isValid
      ? { valid: true,  message: 'Licença válida.' }
      : { valid: false, message: `Chave inválida ou expirada. Entre em contato: ${CONTACT}` }
  );
}

// ── Rota de gerenciamento ─────────────────────────────────────────────────────

function handleAdmin(req, res, show_keys) {
  const token = req.headers['x-admin-token'];
  if (!token || token !== process.env.ADMIN_TOKEN) {
    return res.status(401).json({ ok: false, message: 'Não autorizado' });
  }
  const keys = getValidKeys();
  return res.status(200).json({
    ok: true,
    total: keys.length,
    keys: show_keys === true ? keys : keys.map(maskKey),
  });
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function normalizeKey(k) {
  return String(k).toUpperCase().replace(/-/g, '').trim();
}

function maskKey(k) {
  return k.length > 10
    ? k.slice(0, 6) + '...' + k.slice(-4)
    : k.slice(0, 3) + '***';
}

function getValidKeys() {
  return (process.env.VALID_KEYS || '')
    .split(',')
    .map(normalizeKey)
    .filter(Boolean);
}

function setCorsHeaders(res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, x-client-secret');
}
