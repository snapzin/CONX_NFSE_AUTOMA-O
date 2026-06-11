// Biblioteca compartilhada do servidor de licencas.
// Banco: Upstash Redis (Vercel Marketplace -> Upstash, plano gratuito).
// Env necessarias: UPSTASH_REDIS_REST_URL, UPSTASH_REDIS_REST_TOKEN
import { Redis } from '@upstash/redis';

let _redis = null;
const _memoryHits = new Map();
export function redis() {
  if (_redis) return _redis;
  // Aceita os dois padroes de nome: integracao Vercel (KV_*) e Upstash direto.
  const url = process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL;
  const token = process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN;
  if (url && token) {
    _redis = new Redis({ url, token });
  }
  return _redis;
}

function memoryRateLimit(id, limit, windowSecs) {
  const now = Date.now();
  const windowMs = windowSecs * 1000;
  const e = _memoryHits.get(id) || { count: 0, start: now };
  if (now - e.start > windowMs) {
    _memoryHits.set(id, { count: 1, start: now });
    return false;
  }
  e.count += 1;
  _memoryHits.set(id, e);
  return e.count > limit;
}

export async function rateLimit(id, limit = 60, windowSecs = 60) {
  const safeId = String(id || 'unknown').replace(/[^a-zA-Z0-9:._-]/g, '_').slice(0, 160);
  const r = redis();
  if (!r) return memoryRateLimit(safeId, limit, windowSecs);
  const bucket = Math.floor(Date.now() / (windowSecs * 1000));
  const key = `rl:${safeId}:${bucket}`;
  try {
    const count = await r.incr(key);
    if (Number(count) === 1) {
      await r.expire(key, windowSecs + 10);
    }
    return Number(count) > limit;
  } catch {
    return memoryRateLimit(safeId, limit, windowSecs);
  }
}

export function clientIp(req) {
  return req.headers['x-forwarded-for']?.split(',')[0]?.trim()
    || req.headers['x-real-ip']
    || req.socket?.remoteAddress
    || 'unknown';
}

export const INDEX_SET = 'lic:index';
export const keyPath = (k) => `lic:${k}`;
export const ADMIN_USER_INDEX_SET = 'admin:user:index';
export const adminUserPath = (u) => `admin:user:${u}`;

// ── Chaves ──────────────────────────────────────────────────────────────────
export function normalizeKey(k) {
  return String(k || '').toUpperCase().replace(/[^A-Z0-9]/g, '').trim();
}

export function formatKey(k) {
  // Exibicao amigavel: grupos de 4 (ex.: NFSE-XXXX-XXXX-XXXX-XXXX)
  const n = normalizeKey(k);
  return (n.match(/.{1,4}/g) || []).join('-');
}

export function maskKey(k) {
  const n = normalizeKey(k);
  return n.length > 10 ? n.slice(0, 4) + '...' + n.slice(-4) : n.slice(0, 3) + '***';
}

export function genKey() {
  // 20 caracteres alfanumericos (sem 0/O/1/I para evitar confusao), prefixo NFSE.
  const alf = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  let s = 'NFSE';
  for (let i = 0; i < 16; i++) s += alf[Math.floor(Math.random() * alf.length)];
  return s; // normalizado (sem tracos)
}

// ── Registros ─────────────────────────────────────────────────────────────────
// Formato do registro (JSON em lic:<KEY>):
// { clientName, status: "active"|"blocked", maxMachines,
//   machines: {<id>:{firstSeen,lastSeen,status:"active"|"blocked",blockedAt?}},
//   expiresAt: ISO|null, createdAt: ISO, notes }
export async function getRecord(k) {
  const r = redis();
  if (!r) return null;
  const rec = await r.get(keyPath(k));
  if (!rec) return null;
  return typeof rec === 'string' ? JSON.parse(rec) : rec;
}

export async function saveRecord(k, rec) {
  const r = redis();
  if (!r) throw new Error('Banco (Upstash Redis) nao configurado.');
  await r.set(keyPath(k), JSON.stringify(rec));
  await r.sadd(INDEX_SET, k);
}

export async function deleteRecord(k) {
  const r = redis();
  if (!r) throw new Error('Banco (Upstash Redis) nao configurado.');
  await r.del(keyPath(k));
  await r.srem(INDEX_SET, k);
}

export async function listRecords() {
  const r = redis();
  if (!r) return [];
  const keys = await r.smembers(INDEX_SET);
  if (!keys || keys.length === 0) return [];
  const out = [];
  for (const k of keys) {
    const rec = await getRecord(k);
    if (rec) out.push({ key: k, ...rec });
  }
  return out;
}

// Usuarios administrativos do painel.
export function normalizeAdminUser(u) {
  return String(u || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._@-]/g, '')
    .slice(0, 80);
}

export async function getAdminUser(username) {
  const r = redis();
  if (!r) return null;
  const user = normalizeAdminUser(username);
  if (!user) return null;
  const rec = await r.get(adminUserPath(user));
  if (!rec) return null;
  return typeof rec === 'string' ? JSON.parse(rec) : rec;
}

export async function saveAdminUser(username, rec) {
  const r = redis();
  if (!r) throw new Error('Banco (Upstash Redis) nao configurado.');
  const user = normalizeAdminUser(username);
  if (!user) throw new Error('Usuario invalido.');
  await r.set(adminUserPath(user), JSON.stringify({ ...rec, username: user }));
  await r.sadd(ADMIN_USER_INDEX_SET, user);
}

export async function deleteAdminUser(username) {
  const r = redis();
  if (!r) throw new Error('Banco (Upstash Redis) nao configurado.');
  const user = normalizeAdminUser(username);
  if (!user) throw new Error('Usuario invalido.');
  await r.del(adminUserPath(user));
  await r.srem(ADMIN_USER_INDEX_SET, user);
}

export async function listAdminUsers() {
  const r = redis();
  if (!r) return [];
  const users = await r.smembers(ADMIN_USER_INDEX_SET);
  if (!users || users.length === 0) return [];
  const out = [];
  for (const username of users) {
    const rec = await getAdminUser(username);
    if (rec) {
      out.push({
        username: rec.username || username,
        createdAt: rec.createdAt || null,
        createdBy: rec.createdBy || '',
      });
    }
  }
  out.sort((a, b) => a.username.localeCompare(b.username));
  return out;
}

// Chaves legadas em VALID_KEYS (compatibilidade com a versao antiga).
export function legacyKeys() {
  if (process.env.ALLOW_LEGACY_KEYS !== '1') return [];
  return (process.env.VALID_KEYS || '')
    .split(',')
    .map(normalizeKey)
    .filter(Boolean);
}

// ── HTTP ────────────────────────────────────────────────────────────────────
export function setCors(req, res, methods = 'POST, OPTIONS') {
  const allowed = (process.env.ALLOWED_ORIGINS || 'https://license-server-sigma-topaz.vercel.app')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
  const origin = req?.headers?.origin || '';
  if (origin && allowed.includes(origin)) {
    res.setHeader('Access-Control-Allow-Origin', origin);
  }
  res.setHeader('Access-Control-Allow-Methods', methods);
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, x-client-secret, x-admin-token, x-admin-user, x-admin-pass');
}

export function setSecurityHeaders(res) {
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('X-Frame-Options', 'DENY');
  res.setHeader('Referrer-Policy', 'no-referrer');
  res.setHeader('Permissions-Policy', 'camera=(), microphone=(), geolocation=(), payment=()');
}
