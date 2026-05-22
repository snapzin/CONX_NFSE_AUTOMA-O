const { app, BrowserWindow, ipcMain, Menu } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

let mainWindow;
let pythonProcess;

const API_PORT = 17432;
const API_URL = `http://127.0.0.1:${API_PORT}`;

// Detectar se está em modo produção (empacotado)
const isProd = app.isPackaged;
const DEV_RENDERER_URL = process.env.VITE_DEV_SERVER_URL || 'http://127.0.0.1:5173';

// Caminho para o Python (apenas em desenvolvimento)
const getPythonPath = () => {
  if (process.env.NFSE_PYTHON_PATH) {
    return process.env.NFSE_PYTHON_PATH;
  }

  const projectRoot = path.join(__dirname, '..');
  const venvPython = process.platform === 'win32'
    ? path.join(projectRoot, '.venv', 'Scripts', 'python.exe')
    : path.join(projectRoot, '.venv', 'bin', 'python');

  if (fs.existsSync(venvPython)) {
    return venvPython;
  }

  return process.platform === 'win32' ? 'python' : 'python3';
};

// ============================================================================
// Spawn Python backend
// ============================================================================
const startPythonBackend = () => {
  return new Promise((resolve, reject) => {
    let command, args, cwd;

    if (isProd && process.platform === 'win32') {
      // Produção Windows: server.exe standalone (PyInstaller) em resources/backend/
      command = path.join(process.resourcesPath, 'backend', 'server.exe');
      args = [];
      cwd = path.join(process.resourcesPath, 'backend');
    } else {
      // Desenvolvimento ou macOS: usa Python do projeto
      command = getPythonPath();
      args = [path.join(__dirname, '..', 'api_server.py')];
      cwd = path.join(__dirname, '..');
    }

    console.log(`[Main] Iniciando backend: ${command}`);

    pythonProcess = spawn(command, args, {
      stdio: ['ignore', 'pipe', 'pipe'],
      detached: false,
      cwd,
      env: {
        ...process.env,
        PYTHONIOENCODING: 'utf-8',
        PYTHONUTF8: '1',
      },
    });

    // Log do stdout/stderr do Python
    pythonProcess.stdout.on('data', (data) => {
      console.log(`[Python] ${data.toString().trim()}`);
    });

    pythonProcess.stderr.on('data', (data) => {
      console.error(`[Python stderr] ${data.toString().trim()}`);
    });

    pythonProcess.on('error', (err) => {
      console.error(`[Python] Erro ao iniciar: ${err}`);
      reject(err);
    });

    // Polling /health até responder (máx 15s)
    let retries = 0;
    const maxRetries = 30; // 30 * 500ms = 15s

    const checkHealth = async () => {
      try {
        const response = await fetch(`${API_URL}/health`);
        if (response.ok) {
          console.log('[Main] Backend respondendo');
          resolve();
          return;
        }
      } catch (e) {
        // Esperado no início
      }

      retries++;
      if (retries >= maxRetries) {
        reject(new Error('Timeout ao inicializar backend'));
        return;
      }

      setTimeout(checkHealth, 500);
    };

    checkHealth();
  });
};

// ============================================================================
// Criar janela principal
// ============================================================================
const createWindow = () => {
  mainWindow = new BrowserWindow({
    width: 1180,
    height: 760,
    minWidth: 980,
    minHeight: 660,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  if (isProd) {
    mainWindow.loadFile(path.join(__dirname, 'renderer-dist', 'index.html'));
  } else {
    mainWindow.loadURL(DEV_RENDERER_URL).catch(() => {
      const builtIndex = path.join(__dirname, 'renderer-dist', 'index.html');
      const legacyIndex = path.join(__dirname, 'renderer', 'index.html');
      mainWindow.loadFile(fs.existsSync(builtIndex) ? builtIndex : legacyIndex);
    });
  }

  // DevTools desativado por padrao — abra manualmente com Ctrl+Shift+I se precisar

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
};

// ============================================================================
// IPC handlers (comunicação renderer → main)
// ============================================================================
ipcMain.handle('api-call', async (event, method, endpoint, body) => {
  try {
    const options = {
      method,
      headers: { 'Content-Type': 'application/json' },
    };

    if (body) {
      options.body = JSON.stringify(body);
    }

    const response = await fetch(`${API_URL}${endpoint}`, options);

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`HTTP ${response.status}: ${error}`);
    }

    return await response.json();
  } catch (error) {
    console.error(`[API Call] ${method} ${endpoint}:`, error);
    throw error;
  }
});

// ============================================================================
// App lifecycle
// ============================================================================
app.on('ready', async () => {
  try {
    // Remove o menu padrao (File, Edit, View, Window, Help)
    Menu.setApplicationMenu(null);

    // Splash screen (janela pequena enquanto carrega)
    const splashWindow = new BrowserWindow({
      width: 480,
      height: 360,
      frame: false,
      resizable: false,
      center: true,
      alwaysOnTop: true,
      backgroundColor: '#000000',
      show: false,
      webPreferences: {
        nodeIntegration: false,
        contextIsolation: true,
        sandbox: true,
      },
    });

    splashWindow.once('ready-to-show', () => {
      if (!splashWindow.isDestroyed()) {
        splashWindow.show();
      }
    });

    const splashPath = path.join(__dirname, 'splash.html');
    if (fs.existsSync(splashPath)) {
      splashWindow.loadFile(splashPath);
    } else {
      splashWindow.loadURL('data:text/html,<h1>Iniciando...</h1>');
    }

    // Inicia backend (nao crasha o app se falhar — apenas loga)
    console.log('[Main] Iniciando backend Python...');
    try {
      await startPythonBackend();
    } catch (error) {
      console.warn('[Main] Backend nao respondeu (continuando sem ele):', error.message);
    }

    // Fecha splash e abre main
    if (!splashWindow.isDestroyed()) {
      splashWindow.close();
    }
    createWindow();
  } catch (error) {
    console.error('[Main] Erro fatal:', error);
    app.quit();
  }
});

app.on('window-all-closed', () => {
  // Encerra processo Python ao fechar o app
  if (pythonProcess) {
    try {
      if (process.platform === 'win32') {
        require('child_process').exec(`taskkill /PID ${pythonProcess.pid} /T /F`);
      } else {
        process.kill(-pythonProcess.pid);
      }
    } catch (e) {
      console.warn('[Main] Falha ao matar Python:', e);
    }
  }

  app.quit();
});

app.on('activate', () => {
  if (mainWindow === null) {
    createWindow();
  }
});
