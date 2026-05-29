/**
 * watch-and-install.mjs
 * Assiste mudanças em renderer/src/ e reinstala o app automaticamente.
 * Uso: node watch-and-install.mjs
 */

import { watch } from 'node:fs';
import { execSync, spawn } from 'node:child_process';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dir = dirname(fileURLToPath(import.meta.url));
const SRC_DIR = join(__dir, 'renderer', 'src');
const APP_SRC = '/Applications/NFSe Automacao.app';
const APP_DST = join(__dir, 'dist', 'mac', 'NFSe Automacao.app');

let debounce = null;
let building = false;

const log = (msg) => console.log(`[${new Date().toLocaleTimeString('pt-BR')}] ${msg}`);

function run(cmd, opts = {}) {
  execSync(cmd, { cwd: __dir, stdio: 'inherit', ...opts });
}

async function buildAndInstall() {
  if (building) return;
  building = true;
  const start = Date.now();
  try {
    log('🔨 Construindo renderer...');
    run('npm run build:renderer');

    log('📦 Empacotando app...');
    run('npx electron-builder --mac --dir 2>&1 | grep -v "^  •\\|skipped\\|identity"', { shell: true });

    log('🚀 Instalando em /Applications...');
    run(`rm -rf "${APP_SRC}" && cp -R "${APP_DST}" "/Applications/"`, { shell: true });

    const elapsed = ((Date.now() - start) / 1000).toFixed(1);
    log(`✅ App atualizado em ${elapsed}s — reabra o NFSe Automacao para ver as mudanças.`);
  } catch (err) {
    log(`❌ Erro: ${err.message}`);
  } finally {
    building = false;
  }
}

// Assiste mudanças na pasta src/
watch(SRC_DIR, { recursive: true }, (event, filename) => {
  if (!filename) return;
  clearTimeout(debounce);
  debounce = setTimeout(() => {
    log(`📝 Alteração detectada: ${filename}`);
    buildAndInstall();
  }, 1500); // aguarda 1.5s sem novas mudanças antes de buildar
});

log(`👀 Assistindo ${SRC_DIR}`);
log('   Salve qualquer arquivo em renderer/src/ para acionar o build automático.');
log('   Ctrl+C para parar.\n');
