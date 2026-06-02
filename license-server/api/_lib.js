// Biblioteca compartilhada do servidor de licencas.
// Banco: Upstash Redis (Vercel Marketplace -> Upstash, plano gratuito).
// Env necessarias: UPSTASH_REDIS_REST_URL, UPSTASH_REDIS_REST_TOKEN
import { Redis } from '@upstash/redis';

let _redis = null;
export function redis() {
  if (_redis) return _redis;
  if (process.env.UPSTASH_REDIS_REST_URL && process.env.UPSTASH_REDIS_REST_TOKEN) {
    _redis = Redis.fromEnv();
  }
  return _redis;
}

export const INDEX_SET = 'lic:index';
export const keyPath = (k) => `lic:${k}`;

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
// { clientName, status: "active"|"blocked", maxMachines, machines: {<id>:{firstSeen,lastSeen}},
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

// Chaves legadas em VALID_KEYS (compatibilidade com a versao antiga).
export function legacyKeys() {
  return (process.env.VALID_KEYS || '')
    .split(',')
    .map(normalizeKey)
    .filter(Boolean);
}

// ── HTTP ────────────────────────────────────────────────────────────────────
export function setCors(res, methods = 'POST, OPTIONS') {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', methods);
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, x-client-secret, x-admin-token');
}
