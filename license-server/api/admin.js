// API de gerenciamento de licencas (protegida por x-admin-token).
// POST {op, ...} + header x-admin-token == ADMIN_TOKEN
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

export default async function handler(req, res) {
  setCors(res);
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ ok: false, message: 'Metodo nao permitido' });

  if (!process.env.ADMIN_TOKEN || (req.headers['x-admin-token'] || '') !== process.env.ADMIN_TOKEN) {
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
        machineCount: Object.keys(r.machines || {}).length,
        expiresAt: r.expiresAt || null,
        createdAt: r.createdAt || null,
        lastSeen: r.lastSeen || null,
        notes: r.notes || '',
      }));
      items.sort((a, b) => (a.clientName || '').localeCompare(b.clientName || ''));
      return res.status(200).json({ ok: true, total: items.length, items });
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
