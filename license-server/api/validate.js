// Vercel serverless function — valida chaves de licença NFSe Automação
// Deploy: vercel --prod (dentro da pasta license-server/)
//
// Variáveis de ambiente no Vercel:
//   VALID_KEYS  = "CHAVE1,CHAVE2,CHAVE3"  (sem espaços, maiúsculas, sem traços)
//   ADMIN_TOKEN = "token-secreto-para-gerenciar"

export default function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') {
    return res.status(405).json({ valid: false, message: 'Método não permitido' });
  }

  const { key, machine_id, action } = req.body || {};

  // ── Rota de gerenciamento (adicionar/revogar chaves em runtime) ──────────────
  if (action === 'admin') {
    const token = req.headers['x-admin-token'];
    if (!token || token !== process.env.ADMIN_TOKEN) {
      return res.status(401).json({ ok: false, message: 'Não autorizado' });
    }
    // Para listar chaves ativas:
    const keys = getValidKeys();
    return res.status(200).json({ ok: true, total: keys.length, keys });
  }

  // ── Validação de licença ────────────────────────────────────────────────────
  if (!key) {
    return res.status(400).json({ valid: false, message: 'Chave não informada' });
  }

  const normalizedKey = key.toUpperCase().replace(/-/g, '').trim();
  const validKeys = getValidKeys();
  const isValid = validKeys.includes(normalizedKey);

  // Log para monitoramento (visível nos logs do Vercel)
  console.log(JSON.stringify({
    ts: new Date().toISOString(),
    key_prefix: normalizedKey.slice(0, 6) + '...',
    machine_id: machine_id || 'unknown',
    valid: isValid,
  }));

  if (isValid) {
    return res.status(200).json({ valid: true, message: 'Licença válida.' });
  }

  return res.status(200).json({
    valid: false,
    message: 'Chave inválida ou expirada. Entre em contato: conxcontabil@gmail.com',
  });
}

function getValidKeys() {
  return (process.env.VALID_KEYS || '')
    .split(',')
    .map(k => k.trim().toUpperCase().replace(/-/g, ''))
    .filter(Boolean);
}
