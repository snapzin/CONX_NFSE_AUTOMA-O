const path = require("path");
const { app, BrowserWindow, dialog, ipcMain, shell } = require("electron");
const { spawn, spawnSync } = require("child_process");

const ROOT_DIR = path.resolve(__dirname, "..");
const BRIDGE_PATH = path.join(ROOT_DIR, "nfse_bridge.py");
const PYTHON_ENV = { ...process.env, PYTHONIOENCODING: "utf-8" };
const LOCAL_VENV_PYTHON = path.join(ROOT_DIR, ".venv", "Scripts", "python.exe");

let mainWindow = null;
let runningProcess = null;
let pythonRuntime = null;

const PYTHON_CANDIDATES = [
  { command: LOCAL_VENV_PYTHON, args: [] },
  { command: "python", args: [] },
  { command: "py", args: ["-3"] },
  { command: "python3", args: [] },
];

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1240,
    height: 840,
    minWidth: 980,
    minHeight: 700,
    title: "NFSe Automacao (JavaScript)",
    backgroundColor: "#0b1220",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  mainWindow.loadFile(path.join(__dirname, "renderer", "index.html"));

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

function resolvePythonRuntime() {
  if (pythonRuntime) {
    return pythonRuntime;
  }

  const candidates = [];
  if (process.env.NFSE_PYTHON) {
    candidates.push({ command: process.env.NFSE_PYTHON, args: [] });
  }
  candidates.push(...PYTHON_CANDIDATES);

  for (const candidate of candidates) {
    try {
      const test = spawnSync(candidate.command, [...candidate.args, "--version"], {
        cwd: ROOT_DIR,
        env: PYTHON_ENV,
        windowsHide: true,
        timeout: 5000,
      });
      if (test.error) {
        continue;
      }
      if (test.status === 0) {
        pythonRuntime = candidate;
        return pythonRuntime;
      }
    } catch {
      // Keep trying next candidate.
    }
  }

  throw new Error(
    "Nao foi possivel localizar Python. Configure a variavel NFSE_PYTHON com o caminho do executavel."
  );
}

function spawnBridge(commandArgs) {
  const runtime = resolvePythonRuntime();
  return spawn(runtime.command, [...runtime.args, BRIDGE_PATH, ...commandArgs], {
    cwd: ROOT_DIR,
    env: PYTHON_ENV,
    windowsHide: true,
    stdio: ["pipe", "pipe", "pipe"],
  });
}

function parseLastJsonFromOutput(outputText) {
  const lines = String(outputText || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  for (let i = lines.length - 1; i >= 0; i -= 1) {
    try {
      return JSON.parse(lines[i]);
    } catch {
      // Keep trying previous lines.
    }
  }

  throw new Error("Resposta JSON invalida do bridge.");
}

function runBridgeJson(commandArgs, inputText = "") {
  return new Promise((resolve, reject) => {
    let stdout = "";
    let stderr = "";

    let child;
    try {
      child = spawnBridge(commandArgs);
    } catch (error) {
      reject(error);
      return;
    }

    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString("utf-8");
    });

    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString("utf-8");
    });

    child.on("error", (error) => reject(error));

    child.on("close", (code) => {
      try {
        const parsed = parseLastJsonFromOutput(stdout);
        if (code !== 0 || parsed.ok === false) {
          const message =
            parsed.error || parsed.message || stderr.trim() || `Bridge finalizou com codigo ${code}.`;
          reject(new Error(message));
          return;
        }
        resolve(parsed);
      } catch (error) {
        const fallback = stderr.trim() || stdout.trim() || String(error);
        reject(new Error(fallback));
      }
    });

    if (inputText) {
      child.stdin.write(inputText);
    }
    child.stdin.end();
  });
}

function sendRunEvent(payload) {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }
  mainWindow.webContents.send("run:event", payload);
}

function attachLineStream(stream, onLine) {
  let buffer = "";

  stream.on("data", (chunk) => {
    buffer += chunk.toString("utf-8");
    let breakIndex = buffer.indexOf("\n");
    while (breakIndex >= 0) {
      const line = buffer.slice(0, breakIndex).replace(/\r$/, "").trim();
      buffer = buffer.slice(breakIndex + 1);
      if (line) {
        onLine(line);
      }
      breakIndex = buffer.indexOf("\n");
    }
  });

  stream.on("end", () => {
    const last = buffer.trim();
    if (last) {
      onLine(last);
    }
  });
}

function normalizeRunLine(line, source) {
  try {
    const parsed = JSON.parse(line);
    if (parsed && typeof parsed === "object") {
      return parsed;
    }
  } catch {
    // Fallback below.
  }

  return {
    event: "log",
    timestamp: new Date().toLocaleTimeString("pt-BR", { hour12: false }),
    level: source === "stderr" ? "ERROR" : "INFO",
    logger: source === "stderr" ? "bridge.stderr" : "bridge.stdout",
    message: line,
  };
}

ipcMain.handle("app:get-config", async () => runBridgeJson(["get-config"]));

ipcMain.handle("config:save", async (_event, values) => {
  const payload = JSON.stringify(values || {});
  return runBridgeJson(["set-config"], payload);
});

ipcMain.handle("certs:count", async () => runBridgeJson(["count-certs"]));

ipcMain.handle("dialog:pick-path", async (_event, kind) => {
  const isDir = kind === "dir";
  const options = {
    title: isDir ? "Selecione uma pasta" : "Selecione um arquivo",
    properties: [isDir ? "openDirectory" : "openFile"],
  };
  const result = await dialog.showOpenDialog(mainWindow, options);
  if (result.canceled || !result.filePaths.length) {
    return { ok: false };
  }
  return { ok: true, value: result.filePaths[0] };
});

ipcMain.handle("path:open", async (_event, targetPath) => {
  if (!targetPath) {
    return { ok: false, error: "Caminho vazio." };
  }
  const openError = await shell.openPath(String(targetPath));
  if (openError) {
    return { ok: false, error: openError };
  }
  return { ok: true };
});

ipcMain.handle("run:start", async (_event, payload) => {
  if (runningProcess && !runningProcess.killed) {
    throw new Error("Ja existe uma execucao em andamento.");
  }

  let child;
  try {
    child = spawnBridge(["run"]);
  } catch (error) {
    throw new Error(String(error.message || error));
  }

  let finishedReceived = false;
  runningProcess = child;

  attachLineStream(child.stdout, (line) => {
    const eventPayload = normalizeRunLine(line, "stdout");
    if (eventPayload.event === "finished") {
      finishedReceived = true;
    }
    sendRunEvent(eventPayload);
  });

  attachLineStream(child.stderr, (line) => {
    sendRunEvent(normalizeRunLine(line, "stderr"));
  });

  child.on("close", (code) => {
    if (!finishedReceived) {
      sendRunEvent({
        event: "finished",
        status: code === 0 ? "ok" : "erro",
        message: code === 0 ? "Execucao finalizada." : "Execucao finalizada com erro.",
        error: code === 0 ? "" : `Processo finalizado com codigo ${code}.`,
      });
    }
    runningProcess = null;
  });

  child.on("error", (error) => {
    sendRunEvent({
      event: "finished",
      status: "erro",
      message: "Falha ao iniciar execucao.",
      error: String(error.message || error),
    });
    runningProcess = null;
  });

  child.stdin.write(`${JSON.stringify(payload || {})}\n`);

  return { ok: true };
});

ipcMain.handle("run:cancel", async () => {
  if (!runningProcess || runningProcess.killed) {
    return { ok: false, error: "Nao ha execucao em andamento." };
  }
  runningProcess.stdin.write("cancel\n");
  return { ok: true };
});

app.whenReady().then(() => {
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  if (runningProcess && !runningProcess.killed) {
    try {
      runningProcess.stdin.write("cancel\n");
    } catch {
      // Ignore.
    }
  }
});
