// Biblioteca compartilhada do servidor de licencas.
// Banco: Upstash Redis (Vercel Marketplace -> Upstash, plano gratuito).
// Env necessarias: UPSTASH_REDIS_REST_URL, UPSTASH_REDIS_REST_TOKEN
import { Redis } from '@upstash/redis';
import { randomBytes } from 'crypto';

let _redis = null;
export function redis() {
  if (_redis) return _redis;
  const url   = process.env.KV_REST_API_URL   || process.env.UPSTASH_REDIS_REST_URL;
  const token = process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN;
  if (url && token) _redis = new Redis({ url, token });
  return _redis;
}

export const INDEX_SET = 'lic:index';
export const keyPath   = (k) => `lic:${k}`;

// ── Chaves ────────────────────────────────────────────────────────────────────
export function normalizeKey(k) {
  return String(k || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
}

export function formatKey(k) {
  const n = normalizeKey(k);
  return (n.match(/.{1,4}/g) || []).join('-');
}

export function maskKey(k) {
  const n = normalizeKey(k);
  return n.length > 10 ? n.slice(0, 4) + '...' + n.slice(-4) : n.slice(0, 3) + '***';
}

export function genKey() {
  // Usa crypto para aleatoriedade criptograficamente segura.
  // Alfabeto de 32 chars (sem 0/O/1/I) => modulo sem bias: 256/32 = 8 exato.
  const ALF = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  const buf  = randomBytes(16);
  let s = 'NFSE';
  for (let i = 0; i < 16; i++) s += ALF[buf[i] & 31];
  return s;
}

// ── Registros ─────────────────────────────────────────────────────────────────
function parseRec(raw) {
  if (raw == null) return null;
  try { return typeof raw === 'string' ? JSON.parse(raw) : raw; }
  catch { return null; }
}

export async function getRecord(k) {
  const r = redis();
  if (!r) return null;
  return parseRec(await r.get(keyPath(k)));
}

export async function saveRecord(k, rec) {
  const r = redis();
  if (!r) throw new Error('Banco (Upstash Redis) nao configurado.');
  // Pipeline: set + sadd em um unico round-trip
  const p = r.pipeline();
  p.set(keyPath(k), JSON.stringify(rec));
  p.sadd(INDEX_SET, k);
  await p.exec();
}

export async function deleteRecord(k) {
  const r = redis();
  if (!r) throw new Error('Banco (Upstash Redis) nao configurado.');
  // Pipeline: del + srem em um unico round-trip
  const p = r.pipeline();
  p.del(keyPath(k));
  p.srem(INDEX_SET, k);
  await p.exec();
}

export async function listRecords() {
  const r = redis();
  if (!r) return [];
  const keys = await r.smembers(INDEX_SET);
  if (!keys?.length) return [];
  // mget: unico round-trip para todos os registros (vs N gets sequenciais)
  const vals = await r.mget(...keys.map(keyPath));
  const out  = [];
  for (let i = 0; i < keys.length; i++) {
    const rec = parseRec(vals[i]);
    if (rec) out.push({ key: keys[i], ...rec });
  }
  return out;
}

// Chaves legadas em VALID_KEYS (compatibilidade com versao antiga).
// Calculado uma vez por instancia Lambda — VALID_KEYS nao muda em runtime.
export const LEGACY_KEYS = (process.env.VALID_KEYS || '')
  .split(',').map(normalizeKey).filter(Boolean);

// Mantido por compatibilidade com imports existentes
export function legacyKeys() { return LEGACY_KEYS; }

// ── HTTP ──────────────────────────────────────────────────────────────────────
export function setCors(res, methods = 'POST, OPTIONS') {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', methods);
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, x-client-secret, Authorization');
}
