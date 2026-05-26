const { execFile, spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const cwd = __dirname;
const viteBin = path.join(cwd, 'node_modules', 'vite', 'bin', 'vite.js');
const electronBin = path.join(cwd, 'node_modules', 'electron', 'cli.js');
const electronExe = process.platform === 'win32'
  ? path.join(cwd, 'node_modules', 'electron', 'dist', 'electron.exe')
  : path.join(cwd, 'node_modules', 'electron', 'dist', 'Electron.app', 'Contents', 'MacOS', 'Electron');
const rendererUrl = process.env.VITE_DEV_SERVER_URL || 'http://127.0.0.1:5173';

let viteProcess;
let electronProcess;
let shuttingDown = false;

const killTree = (child) => {
  if (!child || child.killed) {
    return;
  }

  if (process.platform === 'win32') {
    execFile('taskkill', ['/PID', String(child.pid), '/T', '/F'], () => {});
    return;
  }

  try {
    child.kill('SIGTERM');
  } catch {
    // Process already exited.
  }
};

const shutdown = (code = 0) => {
  if (shuttingDown) {
    return;
  }
  shuttingDown = true;
  killTree(electronProcess);
  killTree(viteProcess);
  setTimeout(() => process.exit(code), 300);
};

const pipe = (child, label) => {
  child.stdout.on('data', (data) => process.stdout.write(`[${label}] ${data}`));
  child.stderr.on('data', (data) => process.stderr.write(`[${label}] ${data}`));
};

const waitForRenderer = async () => {
  const timeoutAt = Date.now() + 60_000;
  while (Date.now() < timeoutAt) {
    try {
      const response = await fetch(rendererUrl);
      if (response.ok) {
        return;
      }
    } catch {
      // Vite is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Timeout aguardando renderer em ${rendererUrl}`);
};

async function main() {
  viteProcess = spawn(process.execPath, [viteBin], {
    cwd,
    env: process.env,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  pipe(viteProcess, 'vite');

  viteProcess.on('exit', (code) => {
    if (!shuttingDown && !electronProcess) {
      console.error(`[vite] Encerrado antes do Electron iniciar (codigo ${code})`);
      shutdown(code || 1);
    }
  });

  await waitForRenderer();

  const electronCommand = process.versions.electron ? process.execPath : process.execPath;
  const electronArgs = process.versions.electron ? ['.'] : [electronBin, '.'];
  const electronEnv = {
    ...process.env,
    VITE_DEV_SERVER_URL: rendererUrl,
  };
  delete electronEnv.ELECTRON_RUN_AS_NODE;

  electronProcess = spawn(electronCommand, electronArgs, {
    cwd,
    env: electronEnv,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  pipe(electronProcess, 'electron');

  electronProcess.on('exit', (code) => shutdown(code || 0));
}

function run() {
  process.on('SIGINT', () => shutdown(0));
  process.on('SIGTERM', () => shutdown(0));

  main().catch((error) => {
    console.error(error);
    shutdown(1);
  });
}

function relaunchWithElectronNode() {
  const child = spawn(electronExe, [__filename], {
    cwd,
    env: {
      ...process.env,
      ELECTRON_RUN_AS_NODE: '1',
    },
    stdio: 'inherit',
  });

  child.on('exit', (code) => process.exit(code || 0));
  child.on('error', (error) => {
    console.error(error);
    process.exit(1);
  });
}

if (!process.versions.electron && fs.existsSync(electronExe)) {
  relaunchWithElectronNode();
} else {
  run();
}
