// API de gerenciamento de licencas.
// Preferencial: POST {op, ...} + headers x-admin-user / x-admin-pass.
// Legado: header x-admin-token == ADMIN_TOKEN.
//
// ops:
//   list                                          -> todas as licencas + detalhes
//   create {clientName, maxMachines, days, key?}  -> cria (gera chave se nao vier)
//   update {key, clientName?, status?, maxMachines?, days?, expiresAt?, notes?}
//   block  {key} / unblock {key}
//   delete {key}
//   removeMachine {key, machine_id}                 -> bloqueia esta maquina
//   unblockMachine {key, machine_id}                -> desbloqueia esta maquina
import crypto from 'crypto';
import {
  getRecord, saveRecord, deleteRecord, listRecords,
  normalizeKey, formatKey, genKey, setCors, setSecurityHeaders, redis,
  rateLimit, clientIp, normalizeAdminUser, getAdminUser, saveAdminUser,
  deleteAdminUser, listAdminUsers,
} from './_lib.js';

const PASSWORD_ITERATIONS = 150000;

function isMachineBlocked(machine) {
  return machine?.status === 'blocked';
}

function activeMachineCount(machines) {
  return Object.values(machines || {}).filter((m) => !isMachineBlocked(m)).length;
}

function safeEqual(a, b) {
  const left = Buffer.from(String(a || ''));
  const right = Buffer.from(String(b || ''));
  if (left.length !== right.length) return false;
  return crypto.timingSafeEqual(left, right);
}

function hashPassword(password) {
  const salt = crypto.randomBytes(16).toString('hex');
  const hash = crypto.pbkdf2Sync(
    String(password || ''),
    salt,
    PASSWORD_ITERATIONS,
    32,
    'sha256',
  ).toString('hex');
  return { hash, salt, iterations: PASSWORD_ITERATIONS, algorithm: 'pbkdf2-sha256' };
}

function verifyPassword(password, rec) {
  if (!rec?.hash || !rec?.salt) return false;
  const iterations = Number(rec.iterations || PASSWORD_ITERATIONS);
  const candidate = crypto.pbkdf2Sync(
    String(password || ''),
    String(rec.salt),
    iterations,
    32,
    'sha256',
  ).toString('hex');
  return safeEqual(candidate, rec.hash);
}

async function authenticate(req) {
  const expectedUser = process.env.ADMIN_USER || '';
  const expectedPass = process.env.ADMIN_PASS || '';
  const gotUser = req.headers['x-admin-user'] || '';
  const gotPass = req.headers['x-admin-pass'] || '';

  if (expectedUser && expectedPass && safeEqual(gotUser, expectedUser) && safeEqual(gotPass, expectedPass)) {
    return { ok: true, username: String(expectedUser), source: 'env' };
  }

  const expectedToken = process.env.ADMIN_TOKEN || '';
  const gotToken = req.headers['x-admin-token'] || '';
  if (expectedToken && safeEqual(gotToken, expectedToken)) {
    return { ok: true, username: 'token-admin', source: 'token' };
  }

  const user = normalizeAdminUser(gotUser);
  if (!user || !gotPass) return { ok: false };
  const rec = await getAdminUser(user);
  if (rec && verifyPassword(gotPass, rec)) {
    return { ok: true, username: user, source: 'redis' };
  }

  return { ok: false };
}

export default async function handler(req, res) {
  setSecurityHeaders(res);
  setCors(req, res);
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ ok: false, message: 'Metodo nao permitido' });

  if (await rateLimit(`admin:ip:${clientIp(req)}`, 20, 60)) {
    return res.status(429).json({ ok: false, message: 'Muitas tentativas. Tente novamente.' });
  }

  const auth = await authenticate(req);
  if (!auth.ok) {
    return res.status(401).json({ ok: false, message: 'Nao autorizado' });
  }
  if (!redis()) {
    return res.status(500).json({ ok: false, message: 'Banco (Upstash Redis) nao configurado. Defina UPSTASH_REDIS_REST_URL e UPSTASH_REDIS_REST_TOKEN.' });
  }

  const body = req.body || {};
  const op = body.op;
  const daysToExpiry = (days) => {
    if (days === null) return null;            // explicitamente sem validade
    if (days === undefined || days === '') return undefined; // nao mexe
    const n = Number(days);
    if (!Number.isFinite(n) || n <= 0) return null;
    return new Date(Date.now() + n * 86400_000).toISOString();
  };

  try {
    if (op === 'list') {
      const recs = await listRecords();
      const items = recs.map((r) => ({
        key: r.key,
        keyFmt: formatKey(r.key),
        clientName: r.clientName || '',
        status: r.status || 'active',
        maxMachines: r.maxMachines || 1,
        machines: r.machines || {},
        machineCount: activeMachineCount(r.machines || {}),
        blockedMachineCount: Object.values(r.machines || {}).filter(isMachineBlocked).length,
        expiresAt: r.expiresAt || null,
        createdAt: r.createdAt || null,
        lastSeen: r.lastSeen || null,
        notes: r.notes || '',
      }));
      items.sort((a, b) => (a.clientName || '').localeCompare(b.clientName || ''));
      return res.status(200).json({ ok: true, total: items.length, items });
    }

    if (op === 'listUsers') {
      const users = await listAdminUsers();
      const envUser = process.env.ADMIN_USER
        ? [{
            username: process.env.ADMIN_USER,
            createdAt: null,
            createdBy: 'Vercel env',
            source: 'env',
          }]
        : [];
      return res.status(200).json({ ok: true, users: [...envUser, ...users] });
    }

    if (op === 'createUser') {
      const username = normalizeAdminUser(body.username);
      const password = String(body.password || '');
      if (username.length < 3) {
        return res.status(400).json({ ok: false, message: 'Usuario deve ter pelo menos 3 caracteres.' });
      }
      if (password.length < 8) {
        return res.status(400).json({ ok: false, message: 'Senha deve ter pelo menos 8 caracteres.' });
      }
      if (await getAdminUser(username)) {
        return res.status(409).json({ ok: false, message: 'Usuario ja existe.' });
      }
      await saveAdminUser(username, {
        ...hashPassword(password),
        createdAt: new Date().toISOString(),
        createdBy: auth.username || '',
      });
      return res.status(200).json({ ok: true, user: { username } });
    }

    if (op === 'deleteUser') {
      const username = normalizeAdminUser(body.username);
      if (!username) return res.status(400).json({ ok: false, message: 'Usuario nao informado.' });
      if (auth.source === 'redis' && username === auth.username) {
        return res.status(409).json({ ok: false, message: 'Voce nao pode excluir o usuario em uso.' });
      }
      if (!(await getAdminUser(username))) {
        return res.status(404).json({ ok: false, message: 'Usuario nao encontrado.' });
      }
      await deleteAdminUser(username);
      return res.status(200).json({ ok: true });
    }

    if (op === 'create') {
      let k = body.key ? normalizeKey(body.key) : genKey();
      if (await getRecord(k)) return res.status(409).json({ ok: false, message: 'Chave ja existe.' });
      const rec = {
        clientName: String(body.clientName || '').trim(),
        status: 'active',
        maxMachines: Math.max(1, Number(body.maxMachines || 1)),
        machines: {},
        expiresAt: daysToExpiry(body.days) ?? null,
        createdAt: new Date().toISOString(),
        lastSeen: null,
        notes: String(body.notes || ''),
      };
      await saveRecord(k, rec);
      return res.status(200).json({ ok: true, key: k, keyFmt: formatKey(k), record: rec });
    }

    if (op === 'update') {
      const k = normalizeKey(body.key);
      const rec = await getRecord(k);
      if (!rec) return res.status(404).json({ ok: false, message: 'Chave nao encontrada.' });
      if (body.clientName !== undefined) rec.clientName = String(body.clientName).trim();
      if (body.status !== undefined) rec.status = body.status === 'blocked' ? 'blocked' : 'active';
      if (body.maxMachines !== undefined) rec.maxMachines = Math.max(1, Number(body.maxMachines));
      if (body.notes !== undefined) rec.notes = String(body.notes);
      if (body.expiresAt !== undefined) rec.expiresAt = body.expiresAt || null;
      else {
        const e = daysToExpiry(body.days);
        if (e !== undefined) rec.expiresAt = e;
      }
      await saveRecord(k, rec);
      return res.status(200).json({ ok: true, record: rec });
    }

    if (op === 'block' || op === 'unblock') {
      const k = normalizeKey(body.key);
      const rec = await getRecord(k);
      if (!rec) return res.status(404).json({ ok: false, message: 'Chave nao encontrada.' });
      rec.status = op === 'block' ? 'blocked' : 'active';
      await saveRecord(k, rec);
      return res.status(200).json({ ok: true, status: rec.status });
    }

    if (op === 'removeMachine') {
      const k = normalizeKey(body.key);
      const rec = await getRecord(k);
      if (!rec) return res.status(404).json({ ok: false, message: 'Chave nao encontrada.' });
      const mid = String(body.machine_id || '');
      if (!mid) return res.status(400).json({ ok: false, message: 'Maquina nao informada.' });
      rec.machines = rec.machines || {};
      rec.machines[mid] = {
        ...(rec.machines[mid] || {}),
        status: 'blocked',
        blockedAt: new Date().toISOString(),
      };
      await saveRecord(k, rec);
      return res.status(200).json({ ok: true, record: rec });
    }

    if (op === 'unblockMachine') {
      const k = normalizeKey(body.key);
      const rec = await getRecord(k);
      if (!rec) return res.status(404).json({ ok: false, message: 'Chave nao encontrada.' });
      const mid = String(body.machine_id || '');
      if (!mid) return res.status(400).json({ ok: false, message: 'Maquina nao informada.' });
      if (!rec.machines?.[mid]) return res.status(404).json({ ok: false, message: 'Maquina nao encontrada.' });
      if (isMachineBlocked(rec.machines[mid]) && activeMachineCount(rec.machines) >= Number(rec.maxMachines || 1)) {
        return res.status(409).json({ ok: false, message: 'Limite de maquinas ativas atingido.' });
      }
      rec.machines[mid].status = 'active';
      delete rec.machines[mid].blockedAt;
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
