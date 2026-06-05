// API de gerenciamento de licencas (protegida por usuario + senha via Basic Auth).
// POST {op, ...} + header Authorization: Basic base64(ADMIN_USER:ADMIN_PASS)
//
// ops:
//   list                                          -> todas as licencas + detalhes
//   create {clientName, maxMachines, days, key?}  -> cria (gera chave se nao vier)
//   update {key, clientName?, status?, maxMachines?, days?, expiresAt?, notes?}
//   block  {key} / unblock {key}
//   delete {key}
//   removeMachine {key, machine_id}
import {
  getRecord, saveRecord, deleteRecord, listRecords,
  normalizeKey, formatKey, genKey, setCors, redis,
} from './_lib.js';
import nodemailer from 'nodemailer';

// ── Lockout progressivo ────────────────────────────────────────────────────────
// 1º bloqueio: 15 min | 2º: 1h | 3º: 6h | 4º+: 24h
const MAX_ATTEMPTS      = 5;
const LOCKOUT_DURATIONS = [15 * 60, 60 * 60, 6 * 60 * 60, 24 * 60 * 60];

// Fallback in-memory quando Redis nao esta configurado.
// ip -> { count, lockouts, blockedUntil }
const _mem     = new Map();
const MAX_MIPS = 300;

function lockoutDuration(lockouts) {
  return LOCKOUT_DURATIONS[Math.min(lockouts, LOCKOUT_DURATIONS.length - 1)];
}

function fmtDuration(secs) {
  if (secs >= 3600) {
    const h = Math.floor(secs / 3600), m = Math.floor((secs % 3600) / 60);
    return m > 0 ? `${h}h ${m}min` : `${h} hora${h > 1 ? 's' : ''}`;
  }
  return `${Math.floor(secs / 60)} minutos`;
}

function _pruneMemIfNeeded() {
  if (_mem.size < MAX_MIPS) return;
  const now = Date.now();
  for (const [k, v] of _mem) {
    if ((!v.blockedUntil || v.blockedUntil < now) && v.count === 0) _mem.delete(k);
  }
}

// Retorna { blocked, lockouts, remainingSecs }
async function getBlockState(ip) {
  const r = redis();
  if (r) {
    // Pipeline: blocked + lockouts + ttl em um unico round-trip
    const p = r.pipeline();
    p.get(`admin:blocked:${ip}`);
    p.get(`admin:lockouts:${ip}`);
    p.ttl(`admin:blocked:${ip}`);
    const [blocked, lockoutsRaw, ttl] = await p.exec().catch(() => [null, null, 0]);
    const lockouts = Number(lockoutsRaw || 0);
    const remaining = Number(ttl) > 0 ? Number(ttl) : 0;
    return { blocked: !!blocked, lockouts, remainingSecs: remaining };
  }
  const e = _mem.get(ip);
  if (!e) return { blocked: false, lockouts: 0, remainingSecs: 0 };
  const remaining = e.blockedUntil ? Math.ceil((e.blockedUntil - Date.now()) / 1000) : 0;
  return { blocked: remaining > 0, lockouts: e.lockouts || 0, remainingSecs: Math.max(0, remaining) };
}

// Retorna { count, lockouts, durSecs, blocked }
// blocked=true indica que este request disparou um novo bloqueio
async function recordFailure(ip) {
  const r = redis();
  if (r) {
    // Pipeline 1: le lockouts + incrementa tentativas em paralelo
    const p1 = r.pipeline();
    p1.get(`admin:lockouts:${ip}`);
    p1.incr(`admin:attempts:${ip}`);
    const [lockoutsRaw, count] = await p1.exec().catch(() => [null, MAX_ATTEMPTS]);

    const lockouts = Number(lockoutsRaw || 0);
    const durSecs  = lockoutDuration(lockouts);

    if (Number(count) >= MAX_ATTEMPTS) {
      const newLockouts = lockouts + 1;
      // Pipeline 2: aplica bloqueio atomicamente
      const p2 = r.pipeline();
      p2.set(`admin:blocked:${ip}`,  '1',              { ex: durSecs });
      p2.set(`admin:lockouts:${ip}`, String(newLockouts), { ex: 30 * 24 * 3600 });
      p2.del(`admin:attempts:${ip}`);
      await p2.exec().catch(() => {});
      return { count: Number(count), lockouts: newLockouts, durSecs, blocked: true };
    }

    // Atualiza TTL do contador de tentativas
    await r.expire(`admin:attempts:${ip}`, durSecs).catch(() => {});
    return { count: Number(count), lockouts, durSecs, blocked: false };
  }

  // Fallback in-memory
  _pruneMemIfNeeded();
  const now = Date.now();
  const e   = _mem.get(ip) || { count: 0, lockouts: 0, blockedUntil: null };
  e.count++;
  const durSecs = lockoutDuration(e.lockouts);
  if (e.count >= MAX_ATTEMPTS) {
    e.lockouts++;
    e.blockedUntil = now + durSecs * 1000;
    e.count = 0;
    _mem.set(ip, e);
    return { count: 0, lockouts: e.lockouts, durSecs, blocked: true };
  }
  _mem.set(ip, e);
  return { count: e.count, lockouts: e.lockouts, durSecs, blocked: false };
}

async function clearFailures(ip) {
  const r = redis();
  if (r) {
    // del aceita multiplas chaves — unico round-trip
    await r.del(`admin:attempts:${ip}`, `admin:blocked:${ip}`).catch(() => {});
    // lockouts mantem — historico de bloqueios do IP
  } else {
    const e = _mem.get(ip);
    if (e) { e.count = 0; e.blockedUntil = null; }
  }
}

// ── Geolocalização de IP ──────────────────────────────────────────────────────
async function getGeoIP(ip) {
  if (!ip || ip === 'unknown' || /^(127\.|10\.|192\.168\.|::1)/.test(ip)) return null;
  try {
    const r = await fetch(
      `http://ip-api.com/json/${ip}?fields=status,country,regionName,city,isp,lat,lon`,
      { signal: AbortSignal.timeout(3000) }
    );
    const d = await r.json();
    return d.status === 'success' ? d : null;
  } catch {
    return null;
  }
}

// ── Alerta por email ───────────────────────────────────────────────────────────
async function sendAlert(ip, lockouts, durSecs) {
  const smtpUser = process.env.SMTP_USER;
  const smtpPass = process.env.SMTP_PASS;
  if (!smtpUser || !smtpPass) return;

  const alertTo  = process.env.ALERT_EMAIL || smtpUser;
  const when     = new Date().toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' });
  const durLabel = fmtDuration(durSecs);
  const geo      = await getGeoIP(ip);

  const severity = lockouts <= 1
    ? { color: '#f5a623', bg: 'rgba(245,166,35,.08)', border: 'rgba(245,166,35,.2)', label: 'Alerta', icon: '⚠' }
    : lockouts <= 2
    ? { color: '#ff453a', bg: 'rgba(255,69,58,.08)',  border: 'rgba(255,69,58,.2)',  label: 'Atenção', icon: '🚨' }
    : { color: '#ff2d55', bg: 'rgba(255,45,85,.12)',  border: 'rgba(255,45,85,.3)',  label: 'ATAQUE PERSISTENTE', icon: '🔴' };

  const title = lockouts <= 1
    ? 'Tentativa de acesso bloqueada'
    : lockouts <= 2
    ? 'Ataque repetido detectado'
    : 'Ataque persistente — ação recomendada';

  const subtitle = lockouts <= 1
    ? 'Um IP desconhecido tentou acessar o painel 5 vezes e foi bloqueado automaticamente.'
    : lockouts <= 2
    ? `Este IP já foi bloqueado <strong>${lockouts} vezes</strong>. O padrão de ataque está se repetindo.`
    : `Este IP foi bloqueado <strong>${lockouts} vezes</strong>. Considere bloquear permanentemente este endereço.`;

  const footerMsg = lockouts <= 1
    ? `O acesso será liberado automaticamente em ${durLabel}. Se foi você testando, ignore este email.`
    : `O acesso está bloqueado por ${durLabel}. Recomendamos alterar a senha de administrador se não reconhecer este IP.`;

  try {
    const transporter = nodemailer.createTransport({
      service: 'gmail',
      auth: { user: smtpUser, pass: smtpPass },
    });
    await transporter.sendMail({
      from:    `"CONX Licenças" <${smtpUser}>`,
      to:      alertTo,
      subject: `${severity.icon} ${title} — CONX Licenças`,
      html: `<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#080808;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#080808;padding:40px 16px">
<tr><td align="center">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:520px">

  <tr><td style="background:#141414;border:1px solid #1e1e1e;border-radius:16px 16px 0 0;padding:24px 32px 20px;border-bottom:none">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td><span style="display:inline-block;width:8px;height:8px;background:${severity.color};border-radius:50%;margin-right:8px;vertical-align:middle"></span>
        <span style="font-size:10.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:#686868;vertical-align:middle">CONX Contabilidade · Segurança</span></td>
      <td align="right"><span style="font-size:10px;color:#3a3a3a">${when}</span></td>
    </tr></table>
    <h1 style="margin:18px 0 8px;font-size:20px;font-weight:700;color:#f0f0f0;letter-spacing:-.02em;line-height:1.3">${title}</h1>
    <p style="margin:0;font-size:13.5px;color:#686868;line-height:1.6">${subtitle}</p>
  </td></tr>

  <tr><td style="background:#0d0d0d;border-left:1px solid #1e1e1e;border-right:1px solid #1e1e1e;padding:14px 32px">
    <table cellpadding="0" cellspacing="0"><tr>
      <td style="background:${severity.bg};border:1px solid ${severity.border};border-radius:8px;padding:10px 16px">
        <span style="font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:${severity.color}">${severity.icon} ${severity.label} · Bloqueado por ${durLabel}</span>
      </td>
    </tr></table>
  </td></tr>

  <tr><td style="background:#141414;border-left:1px solid #1e1e1e;border-right:1px solid #1e1e1e;padding:4px 32px 20px">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td style="padding:14px 0;border-bottom:1px solid #1a1a1a;width:130px">
          <span style="font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:#3a3a3a">Endereço IP</span></td>
        <td style="padding:14px 0;border-bottom:1px solid #1a1a1a">
          <span style="font-size:13px;font-family:'SF Mono',Menlo,Consolas,monospace;color:#f0f0f0;letter-spacing:.05em">${ip}</span></td>
      </tr>
      ${geo ? `
      <tr>
        <td style="padding:14px 0;border-bottom:1px solid #1a1a1a">
          <span style="font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:#3a3a3a">Localização</span></td>
        <td style="padding:14px 0;border-bottom:1px solid #1a1a1a">
          <span style="font-size:13px;color:#f0f0f0">${geo.city}${geo.regionName ? ', ' + geo.regionName : ''}, ${geo.country}</span>
          ${geo.lat && geo.lon ? `&nbsp;<a href="https://maps.google.com/?q=${geo.lat},${geo.lon}" style="font-size:11px;color:#686868;text-decoration:none">ver mapa ↗</a>` : ''}
        </td>
      </tr>
      <tr>
        <td style="padding:14px 0;border-bottom:1px solid #1a1a1a">
          <span style="font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:#3a3a3a">Provedor</span></td>
        <td style="padding:14px 0;border-bottom:1px solid #1a1a1a">
          <span style="font-size:13px;color:#f0f0f0">${geo.isp || '—'}</span></td>
      </tr>` : ''}
      <tr>
        <td style="padding:14px 0;border-bottom:1px solid #1a1a1a">
          <span style="font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:#3a3a3a">Tentativas</span></td>
        <td style="padding:14px 0;border-bottom:1px solid #1a1a1a">
          <span style="font-size:13px;color:#f0f0f0">5 de 5&nbsp;</span>
          <span style="font-size:11px;color:#686868">(${lockouts}º bloqueio neste IP)</span></td>
      </tr>
      <tr>
        <td style="padding:14px 0"><span style="font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:#3a3a3a">Liberação</span></td>
        <td style="padding:14px 0"><span style="font-size:13px;color:#f0f0f0">Automática em ${durLabel}</span></td>
      </tr>
    </table>
  </td></tr>

  <tr><td style="background:#0d0d0d;border:1px solid #1e1e1e;border-top:none;border-radius:0 0 16px 16px;padding:18px 32px">
    <p style="margin:0;font-size:12px;color:#3a3a3a;line-height:1.7">${footerMsg}</p>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>`,
    });
  } catch (err) {
    console.error('sendAlert error:', err?.message);
  }
}

// ── Handler principal ──────────────────────────────────────────────────────────
export default async function handler(req, res) {
  setCors(res);
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ ok: false, message: 'Metodo nao permitido' });

  const ip = (req.headers['x-forwarded-for'] || '').split(',')[0].trim() || 'unknown';

  const blockState = await getBlockState(ip);
  if (blockState.blocked) {
    return res.status(429).json({
      ok: false,
      message: `Acesso bloqueado. Tente novamente em ${fmtDuration(blockState.remainingSecs)}.`,
    });
  }

  // Extrai credenciais Basic Auth
  const basicMatch = (req.headers['authorization'] || '').match(/^Basic (.+)$/i);
  let user, pass;
  if (basicMatch) {
    try { [user, pass] = Buffer.from(basicMatch[1], 'base64').toString('utf8').split(':'); } catch {}
  }

  if (!user || user !== process.env.ADMIN_USER || pass !== process.env.ADMIN_PASS) {
    const { count, lockouts, durSecs, blocked } = await recordFailure(ip);
    if (blocked) {
      // FIX: antes verificava count===0 (so funcionava no path in-memory).
      // Agora usa o campo `blocked` retornado por recordFailure, correto em ambos os paths.
      await sendAlert(ip, lockouts, durSecs).catch(() => {});
      return res.status(429).json({
        ok: false,
        message: `Acesso bloqueado por ${fmtDuration(durSecs)}. Um alerta foi enviado ao administrador.`,
      });
    }
    const remaining = Math.max(0, MAX_ATTEMPTS - count);
    return res.status(401).json({
      ok: false,
      message: `Usuário ou senha incorretos. ${remaining} tentativa(s) restante(s).`,
    });
  }

  await clearFailures(ip);

  if (!redis()) {
    return res.status(500).json({
      ok: false,
      message: 'Banco (Upstash Redis) nao configurado. Defina UPSTASH_REDIS_REST_URL e UPSTASH_REDIS_REST_TOKEN.',
    });
  }

  const body = req.body || {};
  const op   = body.op;

  const daysToExpiry = (days) => {
    if (days === null) return null;
    if (days === undefined || days === '') return undefined;
    const n = Number(days);
    if (!Number.isFinite(n) || n <= 0) return null;
    return new Date(Date.now() + n * 86400_000).toISOString();
  };

  try {
    if (op === 'list') {
      const recs  = await listRecords();
      const items = recs.map((r) => ({
        key:          r.key,
        keyFmt:       formatKey(r.key),
        clientName:   r.clientName  || '',
        status:       r.status      || 'active',
        maxMachines:  r.maxMachines || 1,
        machines:     r.machines    || {},
        machineCount: Object.keys(r.machines || {}).length,
        expiresAt:    r.expiresAt   || null,
        createdAt:    r.createdAt   || null,
        lastSeen:     r.lastSeen    || null,
        notes:        r.notes       || '',
      }));
      items.sort((a, b) => (a.clientName || '').localeCompare(b.clientName || ''));
      return res.status(200).json({ ok: true, total: items.length, items });
    }

    if (op === 'create') {
      const k = body.key ? normalizeKey(body.key) : genKey();
      if (await getRecord(k)) return res.status(409).json({ ok: false, message: 'Chave ja existe.' });
      const rec = {
        clientName:  String(body.clientName || '').trim(),
        status:      'active',
        maxMachines: Math.max(1, Number(body.maxMachines || 1)),
        machines:    {},
        expiresAt:   daysToExpiry(body.days) ?? null,
        createdAt:   new Date().toISOString(),
        lastSeen:    null,
        notes:       String(body.notes || ''),
      };
      await saveRecord(k, rec);
      return res.status(200).json({ ok: true, key: k, keyFmt: formatKey(k), record: rec });
    }

    if (op === 'update') {
      const k   = normalizeKey(body.key);
      const rec = await getRecord(k);
      if (!rec) return res.status(404).json({ ok: false, message: 'Chave nao encontrada.' });
      if (body.clientName  !== undefined) rec.clientName  = String(body.clientName).trim();
      if (body.status      !== undefined) rec.status      = body.status === 'blocked' ? 'blocked' : 'active';
      if (body.maxMachines !== undefined) rec.maxMachines = Math.max(1, Number(body.maxMachines));
      if (body.notes       !== undefined) rec.notes       = String(body.notes);
      if (body.expiresAt   !== undefined) {
        rec.expiresAt = body.expiresAt || null;
      } else {
        const e = daysToExpiry(body.days);
        if (e !== undefined) rec.expiresAt = e;
      }
      await saveRecord(k, rec);
      return res.status(200).json({ ok: true, record: rec });
    }

    if (op === 'block' || op === 'unblock') {
      const k   = normalizeKey(body.key);
      const rec = await getRecord(k);
      if (!rec) return res.status(404).json({ ok: false, message: 'Chave nao encontrada.' });
      rec.status = op === 'block' ? 'blocked' : 'active';
      await saveRecord(k, rec);
      return res.status(200).json({ ok: true, status: rec.status });
    }

    if (op === 'removeMachine') {
      const k   = normalizeKey(body.key);
      const rec = await getRecord(k);
      if (!rec) return res.status(404).json({ ok: false, message: 'Chave nao encontrada.' });
      if (rec.machines) delete rec.machines[String(body.machine_id)];
      await saveRecord(k, rec);
      return res.status(200).json({ ok: true, record: rec });
    }

    if (op === 'delete') {
      const k = normalizeKey(body.key);
      await deleteRecord(k);
      return res.status(200).json({ ok: true });
    }

    return res.status(400).json({ ok: false, message: `Operacao desconhecida: ${op}` });
  } catch (err) {
    console.error('admin error:', err?.message);
    return res.status(500).json({ ok: false, message: String(err?.message || err) });
  }
}
