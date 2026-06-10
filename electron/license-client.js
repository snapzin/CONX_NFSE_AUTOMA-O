const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');

const DEFAULT_LICENSE_SERVER_URL = 'https://license-server-sigma-topaz.vercel.app';
const DEFAULT_CLIENT_SECRET = 'nfse-v1-a7f3c9b2d4e6f8a1b3c5d7e9f0a2b4c6';
const TIMEOUT_MS = 8000;

function cleanBaseUrl(url) {
  return String(url || DEFAULT_LICENSE_SERVER_URL).trim().replace(/\/+$/, '');
}

function getLicenseSettings() {
  const serverUrl = cleanBaseUrl(process.env.NFSE_LICENSE_SERVER_URL);
  return {
    serverUrl,
    validationUrl: String(process.env.NFSE_LICENSE_VALIDATE_URL || `${serverUrl}/api/validate`).trim(),
    adminUrl: String(process.env.NFSE_LICENSE_ADMIN_URL || `${serverUrl}/api/admin`).trim(),
    clientesUrl: String(process.env.NFSE_CLIENTES_URL || `${serverUrl}/api/clientes`).trim(),
    clientSecret: String(process.env.NFSE_CLIENT_SECRET || DEFAULT_CLIENT_SECRET).trim(),
  };
}

function normalizeKey(key) {
  return String(key || '').toUpperCase().replace(/[^A-Z0-9]/g, '').trim();
}

function keyHint(key) {
  const clean = normalizeKey(key);
  return clean.length > 12 ? `${clean.slice(0, 8)}...${clean.slice(-4)}` : clean || null;
}

function pythonPlatformMachine() {
  if (process.platform === 'win32') {
    if (process.arch === 'x64') return 'AMD64';
    if (process.arch === 'ia32') return 'x86';
    return process.arch.toUpperCase();
  }
  if (process.arch === 'x64') return 'x86_64';
  return process.arch;
}

function pythonPlatformSystem() {
  if (process.platform === 'win32') return 'Windows';
  if (process.platform === 'darwin') return 'Darwin';
  if (process.platform === 'linux') return 'Linux';
  return process.platform;
}

function getMachineId() {
  const raw = `${os.hostname()}|${pythonPlatformMachine()}|${pythonPlatformSystem()}`;
  return crypto.createHash('sha256').update(raw).digest('hex').slice(0, 32);
}

function createLicenseClient(app) {
  const licenseFile = path.join(app.getPath('userData'), 'license.key');
  const settings = getLicenseSettings();

  function loadKey() {
    try {
      if (!fs.existsSync(licenseFile)) return null;
      return normalizeKey(fs.readFileSync(licenseFile, 'utf8'));
    } catch {
      return null;
    }
  }

  function saveKey(key) {
    const clean = normalizeKey(key);
    fs.mkdirSync(path.dirname(licenseFile), { recursive: true });
    fs.writeFileSync(licenseFile, clean, 'utf8');
    return clean;
  }

  function deactivate() {
    try {
      if (fs.existsSync(licenseFile)) fs.unlinkSync(licenseFile);
    } catch {
      // Nothing useful to do here; status will fail closed next time.
    }
    return { ok: true };
  }

  async function validateKey(key) {
    const clean = normalizeKey(key);
    if (!clean) {
      return { licensed: false, message: 'Nenhuma licenca ativada.', key_hint: null };
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

    try {
      const response = await fetch(settings.validationUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-client-secret': settings.clientSecret,
        },
        body: JSON.stringify({ key: clean, machine_id: getMachineId() }),
        signal: controller.signal,
      });

      let data = {};
      try {
        data = await response.json();
      } catch {
        data = {};
      }

      if (!response.ok) {
        return {
          licensed: false,
          message: data.message || `Servidor de licencas respondeu HTTP ${response.status}.`,
          key_hint: keyHint(clean),
          server_url: settings.serverUrl,
        };
      }

      return {
        licensed: Boolean(data.valid),
        message: String(data.message || ''),
        key_hint: keyHint(clean),
        server_url: settings.serverUrl,
      };
    } catch (error) {
      const timedOut = error?.name === 'AbortError';
      return {
        licensed: false,
        message: timedOut
          ? 'Tempo esgotado ao consultar o servidor de licencas.'
          : 'Sem conexao com o servidor de licencas.',
        key_hint: keyHint(clean),
        server_url: settings.serverUrl,
      };
    } finally {
      clearTimeout(timer);
    }
  }

  async function status() {
    const key = loadKey();
    if (!key) {
      return {
        licensed: false,
        message: 'Nenhuma licenca ativada.',
        key_hint: null,
        server_url: settings.serverUrl,
      };
    }
    return validateKey(key);
  }

  async function activate(key) {
    const result = await validateKey(key);
    if (!result.licensed) {
      const error = new Error(result.message || 'Licenca invalida.');
      error.status = 402;
      throw error;
    }
    saveKey(key);
    return {
      ok: true,
      message: result.message,
      key_hint: result.key_hint,
      server_url: settings.serverUrl,
    };
  }

  return {
    activate,
    deactivate,
    getMachineId,
    getSavedKey: loadKey,
    getSettings: () => ({ ...settings, clientSecret: settings.clientSecret ? '<configured>' : '' }),
    status,
  };
}

module.exports = { createLicenseClient, getLicenseSettings, getMachineId, normalizeKey };
