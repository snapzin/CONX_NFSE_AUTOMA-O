const MAX_LOG_LINES = 5000;

const state = {
  running: false,
  logs: [],
  logFilter: "ALL",
  logSearch: "",
  outputDir: "",
  configPath: "",
  appVersion: "-",
  logRenderScheduled: false,
  disposeRunListener: null,
};

const ui = {
  pageTitle: document.getElementById("pageTitle"),
  appVersion: document.getElementById("appVersion"),
  topStatusText: document.getElementById("topStatusText"),
  statusDot: document.getElementById("statusDot"),
  statusBarText: document.getElementById("statusBarText"),

  cardStatus: document.getElementById("cardStatusValue"),
  cardPeriodo: document.getElementById("cardPeriodoValue"),
  cardCnpjs: document.getElementById("cardCnpjsValue"),
  cardUltima: document.getElementById("cardUltimaValue"),

  usePrevMonth: document.getElementById("usePrevMonth"),
  startDate: document.getElementById("startDate"),
  endDate: document.getElementById("endDate"),
  cnpjsInput: document.getElementById("cnpjsInput"),

  runBtn: document.getElementById("runBtn"),
  cancelBtn: document.getElementById("cancelBtn"),
  countCertsBtn: document.getElementById("countCertsBtn"),
  clearLogsBtn: document.getElementById("clearLogsBtn"),
  openOutputBtn: document.getElementById("openOutputBtn"),
  progressBar: document.getElementById("progressBar"),

  logsList: document.getElementById("logsList"),
  logSearch: document.getElementById("logSearch"),
  copyLogsBtn: document.getElementById("copyLogsBtn"),
  filterButtons: [...document.querySelectorAll(".filter-btn")],

  configSections: document.getElementById("configSections"),
  configStatus: document.getElementById("configStatus"),
  saveConfigBtn: document.getElementById("saveConfigBtn"),
  reloadConfigBtn: document.getElementById("reloadConfigBtn"),
  openConfigBtn: document.getElementById("openConfigBtn"),

  aboutTitle: document.getElementById("aboutTitle"),
  diagText: document.getElementById("diagText"),

  themeSwitch: document.getElementById("themeSwitch"),
  menuButtons: [...document.querySelectorAll(".menu-btn")],
  pages: {
    executar: document.getElementById("page-executar"),
    config: document.getElementById("page-config"),
    sobre: document.getElementById("page-sobre"),
  },
};

function nowTime() {
  return new Date().toLocaleTimeString("pt-BR", { hour12: false });
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setStatusBar(text) {
  ui.statusBarText.textContent = text;
}

function setTopStatus(text, tone) {
  ui.topStatusText.textContent = text;
  ui.statusDot.className = "status-dot";

  if (tone === "running") {
    ui.statusDot.classList.add("status-running");
    ui.topStatusText.style.color = "var(--accent)";
    return;
  }
  if (tone === "warning") {
    ui.statusDot.classList.add("status-warning");
    ui.topStatusText.style.color = "var(--warning)";
    return;
  }
  if (tone === "error") {
    ui.statusDot.classList.add("status-error");
    ui.topStatusText.style.color = "var(--danger)";
    return;
  }

  ui.statusDot.classList.add("status-ok");
  ui.topStatusText.style.color = "var(--success)";
}

function appendLog(message, level = "INFO", logger = "nfse.gui", timestamp = nowTime()) {
  state.logs.push({
    message: String(message || ""),
    level: String(level || "INFO").toUpperCase(),
    logger: String(logger || "nfse.gui"),
    timestamp: String(timestamp || nowTime()),
  });

  if (state.logs.length > MAX_LOG_LINES) {
    state.logs.splice(0, state.logs.length - MAX_LOG_LINES);
  }

  scheduleLogRender();
}

function getVisibleLogs() {
  const needle = state.logSearch.trim().toLowerCase();
  return state.logs.filter((entry) => {
    const levelPass = state.logFilter === "ALL" || entry.level === state.logFilter;
    if (!levelPass) {
      return false;
    }
    if (!needle) {
      return true;
    }
    const line = `${entry.timestamp} ${entry.level} ${entry.logger} ${entry.message}`.toLowerCase();
    return line.includes(needle);
  });
}

function renderLogs() {
  const visible = getVisibleLogs();
  if (!visible.length) {
    ui.logsList.innerHTML = '<p class="log-line debug">Sem logs para exibir.</p>';
    return;
  }

  const html = visible
    .map((entry) => {
      const cssLevel = entry.level.toLowerCase();
      const text = `${entry.timestamp}  ${entry.level.padEnd(8, " ")}  ${entry.logger}  ${entry.message}`;
      return `<p class="log-line ${cssLevel}">${escapeHtml(text)}</p>`;
    })
    .join("");

  ui.logsList.innerHTML = html;
  ui.logsList.scrollTop = ui.logsList.scrollHeight;
}

function scheduleLogRender() {
  if (state.logRenderScheduled) {
    return;
  }
  state.logRenderScheduled = true;
  requestAnimationFrame(() => {
    state.logRenderScheduled = false;
    renderLogs();
  });
}

function formatDateToInput(dateObj) {
  const year = dateObj.getFullYear();
  const month = `${dateObj.getMonth() + 1}`.padStart(2, "0");
  const day = `${dateObj.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatInputToBrazilian(dateInputValue) {
  if (!dateInputValue) {
    return "";
  }
  const [year, month, day] = dateInputValue.split("-");
  if (!year || !month || !day) {
    return "";
  }
  return `${day}/${month}/${year}`;
}

function previousMonthRange() {
  const today = new Date();
  const prevMonth = today.getMonth() === 0 ? 11 : today.getMonth() - 1;
  const prevYear = today.getMonth() === 0 ? today.getFullYear() - 1 : today.getFullYear();
  const start = new Date(prevYear, prevMonth, 1);
  const end = new Date(prevYear, prevMonth + 1, 0);
  return { start, end };
}

function previousMonthLabel() {
  const { start } = previousMonthRange();
  const month = `${start.getMonth() + 1}`.padStart(2, "0");
  const year = start.getFullYear();
  return `${month}/${year}`;
}

function setDefaultDates() {
  const { start, end } = previousMonthRange();
  ui.startDate.value = formatDateToInput(start);
  ui.endDate.value = formatDateToInput(end);
}

function updatePeriodoCard() {
  if (ui.usePrevMonth.checked) {
    ui.cardPeriodo.textContent = previousMonthLabel();
    return;
  }
  const start = formatInputToBrazilian(ui.startDate.value);
  const end = formatInputToBrazilian(ui.endDate.value);
  ui.cardPeriodo.textContent = start && end ? `${start} -> ${end}` : "-";
}

function updateCnpjsCard() {
  const raw = ui.cnpjsInput.value.trim();
  if (!raw) {
    ui.cardCnpjs.textContent = "Todos";
    return;
  }
  const parts = raw.split(/[\s,;]+/).filter(Boolean);
  ui.cardCnpjs.textContent = `${parts.length} CNPJ(s)`;
}

function toggleDateInputs() {
  const disabled = ui.usePrevMonth.checked || state.running;
  ui.startDate.disabled = disabled;
  ui.endDate.disabled = disabled;
  updatePeriodoCard();
}

function setProgress(mode) {
  ui.progressBar.classList.remove("indeterminate");
  if (mode === "running") {
    ui.progressBar.classList.add("indeterminate");
    return;
  }
  if (mode === "ok") {
    ui.progressBar.style.width = "100%";
    return;
  }
  ui.progressBar.style.width = "0";
}

function setRunning(running) {
  state.running = running;
  ui.runBtn.disabled = running;
  ui.cancelBtn.disabled = !running;
  ui.countCertsBtn.disabled = running;
  ui.usePrevMonth.disabled = running;
  ui.cnpjsInput.disabled = running;
  ui.runBtn.textContent = running ? "Executando..." : "Executar agora";
  toggleDateInputs();
}

function parseAndValidateCnpjs(rawText) {
  const raw = String(rawText || "").trim();
  if (!raw) {
    return { cnpjs: null };
  }

  const parts = raw.split(/[\s,;]+/).filter(Boolean);
  const invalid = [];
  const cnpjs = [];
  const seen = new Set();

  for (const part of parts) {
    const digits = part.replace(/\D/g, "");
    if (digits.length !== 14) {
      invalid.push(part);
      continue;
    }
    if (!seen.has(digits)) {
      cnpjs.push(digits);
      seen.add(digits);
    }
  }

  if (invalid.length) {
    throw new Error(`CNPJ invalido: ${invalid.slice(0, 3).join(", ")}. Use 14 digitos.`);
  }

  return { cnpjs };
}

function parseRunDates() {
  if (ui.usePrevMonth.checked) {
    return { dataInicio: null, dataFim: null };
  }
  const start = ui.startDate.value;
  const end = ui.endDate.value;
  if (!start || !end) {
    throw new Error("Informe data inicio e data fim.");
  }
  if (start > end) {
    throw new Error("Data inicio nao pode ser maior que data fim.");
  }
  return {
    dataInicio: formatInputToBrazilian(start),
    dataFim: formatInputToBrazilian(end),
  };
}

async function startExecution() {
  if (state.running) {
    return;
  }

  const { dataInicio, dataFim } = parseRunDates();
  const { cnpjs } = parseAndValidateCnpjs(ui.cnpjsInput.value);

  await window.nfseApi.startRun({ dataInicio, dataFim, cnpjs });

  setRunning(true);
  ui.cardStatus.textContent = "Executando";
  ui.cardUltima.textContent = new Date().toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
  setTopStatus("Executando", "running");
  setStatusBar("Execucao em andamento...");
  setProgress("running");
  appendLog("Execucao iniciada pela interface JavaScript.", "INFO", "nfse.gui");
}

async function cancelExecution() {
  if (!state.running) {
    return;
  }
  const result = await window.nfseApi.cancelRun();
  if (!result.ok) {
    appendLog(result.error || "Falha ao cancelar.", "ERROR", "nfse.gui");
    return;
  }
  ui.cardStatus.textContent = "Cancelando...";
  setTopStatus("Cancelando", "warning");
  setStatusBar("Cancelando execucao em andamento...");
}

function onRunFinished(status, message, errorMessage) {
  setRunning(false);

  if (status === "ok") {
    ui.cardStatus.textContent = "Concluido";
    setTopStatus("Pronto", "ok");
    setStatusBar("Execucao finalizada.");
    setProgress("ok");
    appendLog(message || "Execucao concluida.", "INFO", "nfse.gui");
    return;
  }

  if (status === "cancelado") {
    ui.cardStatus.textContent = "Cancelado";
    setTopStatus("Cancelado", "warning");
    setStatusBar("Execucao cancelada.");
    setProgress("idle");
    appendLog(message || "Execucao cancelada.", "WARNING", "nfse.gui");
    return;
  }

  ui.cardStatus.textContent = "Erro";
  setTopStatus("Erro", "error");
  setStatusBar("Execucao finalizada com erro.");
  setProgress("idle");
  appendLog(message || "Execucao finalizada com erro.", "ERROR", "nfse.gui");
  if (errorMessage) {
    appendLog(errorMessage, "ERROR", "nfse.gui");
  }
}

async function countCertificates() {
  if (state.running) {
    return;
  }
  setStatusBar("Contando certificados...");
  const summary = await window.nfseApi.countCertificates();
  setStatusBar(
    `A1: ${summary.total} | e-CNPJ: ${summary.ecnpj} | e-CPF: ${summary.ecpf} | erros: ${summary.errors}`
  );
  appendLog(`Pasta de certificados: ${summary.path}`, "INFO", "nfse.gui");
  appendLog(
    `Resumo certificados: total=${summary.total} | ok=${summary.valid} | erro=${summary.errors} | cnpjs_unicos=${summary.cnpjsUnicos} | cnpjs_duplicados=${summary.cnpjsDuplicados} | arquivos_duplicados=${summary.arquivosDuplicados}`,
    "INFO",
    "nfse.gui"
  );
}

function setFilter(level) {
  state.logFilter = level;
  ui.filterButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.level === level);
  });
  renderLogs();
}

function clearLogs() {
  state.logs = [];
  renderLogs();
}

async function copyLogsToClipboard() {
  const lines = getVisibleLogs().map(
    (entry) => `${entry.timestamp}  ${entry.level.padEnd(8, " ")}  ${entry.logger}  ${entry.message}`
  );
  const text = lines.join("\n");
  if (!text.trim()) {
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    setStatusBar("Logs copiados para a area de transferencia.");
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
    setStatusBar("Logs copiados para a area de transferencia.");
  }
}

function openPage(pageName) {
  const titles = {
    executar: "Executar",
    config: "Configuracoes",
    sobre: "Sobre",
  };
  ui.pageTitle.textContent = titles[pageName] || "NFSe";

  Object.entries(ui.pages).forEach(([name, pageEl]) => {
    pageEl.classList.toggle("active", name === pageName);
  });
  ui.menuButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.page === pageName);
  });
}

function collectConfigValues() {
  const values = {};
  const inputs = ui.configSections.querySelectorAll("[data-config-key]");
  inputs.forEach((input) => {
    values[input.dataset.configKey] = input.value;
  });
  return values;
}

function renderConfigSections(sections, values) {
  ui.configSections.innerHTML = "";

  for (const section of sections) {
    const sectionEl = document.createElement("section");
    sectionEl.className = "config-section";

    const title = document.createElement("h4");
    title.textContent = section.title;
    sectionEl.appendChild(title);

    for (const field of section.fields) {
      const row = document.createElement("div");
      row.className = "config-grid";

      const label = document.createElement("div");
      label.className = "label";
      label.textContent = field.label;
      row.appendChild(label);

      const input = document.createElement("input");
      input.type = field.type === "secret" ? "password" : "text";
      input.value = values[field.key] || "";
      input.dataset.configKey = field.key;
      input.autocomplete = "off";
      row.appendChild(input);

      const rightAction = document.createElement("div");
      if (field.type === "path" || field.type === "dir") {
        const browseBtn = document.createElement("button");
        browseBtn.className = "btn btn-ghost small";
        browseBtn.textContent = "...";
        browseBtn.addEventListener("click", async () => {
          const picked = await window.nfseApi.pickPath(field.type === "dir" ? "dir" : "path");
          if (picked.ok) {
            input.value = picked.value;
          }
        });
        rightAction.appendChild(browseBtn);
      } else if (field.type === "secret") {
        const revealBtn = document.createElement("button");
        revealBtn.className = "btn btn-ghost small";
        revealBtn.textContent = "Ver";
        revealBtn.addEventListener("click", () => {
          input.type = input.type === "password" ? "text" : "password";
        });
        rightAction.appendChild(revealBtn);
      }
      row.appendChild(rightAction);
      sectionEl.appendChild(row);
    }

    ui.configSections.appendChild(sectionEl);
  }
}

function updateAbout(configResponse) {
  const diagnostics = configResponse.diagnostics || {};
  const portal = diagnostics.portalUrl || "-";
  const extension = diagnostics.extensionDir || "-";
  const output = diagnostics.outputDir || "-";
  const py = diagnostics.pythonVersion || "-";
  const now = diagnostics.now || "-";

  ui.aboutTitle.textContent = `${configResponse.appTitle || "NFSe Automacao"} v${
    configResponse.appVersion || "-"
  }`;
  ui.diagText.textContent = [
    `Python          ${py}`,
    `Portal NFSe     ${portal}`,
    `Extensao        ${extension}`,
    `Pasta de saida  ${output}`,
    `Data atual      ${now}`,
  ].join("\n");
}

async function loadConfig() {
  const configResponse = await window.nfseApi.getConfig();
  state.appVersion = configResponse.appVersion || "-";
  state.outputDir = configResponse.values?.PASTA_SAIDA || "";
  state.configPath = configResponse.configPath || "";

  ui.appVersion.textContent = `v${state.appVersion}`;
  renderConfigSections(configResponse.sections || [], configResponse.values || {});
  updateAbout(configResponse);
  ui.configStatus.textContent = `Config carregado de: ${state.configPath || "-"}`;
  appendLog("Configuracoes carregadas do disco.", "INFO", "nfse.gui");
}

async function saveConfig() {
  const values = collectConfigValues();
  const response = await window.nfseApi.saveConfig(values);
  await loadConfig();
  ui.configStatus.textContent = `Configuracoes salvas. Backup: ${response.backupPath || "config.py.bak"}`;
  setStatusBar("Configuracoes salvas com sucesso.");
}

async function openConfigInEditor() {
  if (!state.configPath) {
    return;
  }
  const result = await window.nfseApi.openPath(state.configPath);
  if (!result.ok) {
    appendLog(result.error || "Falha ao abrir config.py.", "ERROR", "nfse.gui");
  }
}

async function openOutputDir() {
  if (!state.outputDir) {
    setStatusBar("Pasta de saida nao configurada.");
    return;
  }
  const result = await window.nfseApi.openPath(state.outputDir);
  if (!result.ok) {
    appendLog(result.error || "Falha ao abrir pasta de saida.", "ERROR", "nfse.gui");
  }
}

function bindEvents() {
  ui.menuButtons.forEach((button) => {
    button.addEventListener("click", () => openPage(button.dataset.page));
  });

  ui.themeSwitch.addEventListener("change", () => {
    document.body.classList.toggle("theme-light", ui.themeSwitch.checked);
  });

  ui.usePrevMonth.addEventListener("change", toggleDateInputs);
  ui.startDate.addEventListener("change", updatePeriodoCard);
  ui.endDate.addEventListener("change", updatePeriodoCard);
  ui.cnpjsInput.addEventListener("input", updateCnpjsCard);

  ui.runBtn.addEventListener("click", async () => {
    try {
      await startExecution();
    } catch (error) {
      appendLog(error.message || String(error), "ERROR", "nfse.gui");
      setStatusBar(error.message || String(error));
    }
  });

  ui.cancelBtn.addEventListener("click", async () => {
    try {
      await cancelExecution();
    } catch (error) {
      appendLog(error.message || String(error), "ERROR", "nfse.gui");
    }
  });

  ui.countCertsBtn.addEventListener("click", async () => {
    try {
      await countCertificates();
    } catch (error) {
      appendLog(error.message || String(error), "ERROR", "nfse.gui");
      setStatusBar("Falha ao contar certificados.");
    }
  });

  ui.clearLogsBtn.addEventListener("click", clearLogs);
  ui.copyLogsBtn.addEventListener("click", copyLogsToClipboard);
  ui.openOutputBtn.addEventListener("click", openOutputDir);

  ui.filterButtons.forEach((button) => {
    button.addEventListener("click", () => setFilter(button.dataset.level));
  });
  ui.logSearch.addEventListener("input", () => {
    state.logSearch = ui.logSearch.value;
    renderLogs();
  });

  ui.saveConfigBtn.addEventListener("click", async () => {
    try {
      await saveConfig();
    } catch (error) {
      appendLog(error.message || String(error), "ERROR", "nfse.gui");
      ui.configStatus.textContent = `Erro ao salvar: ${error.message || String(error)}`;
    }
  });

  ui.reloadConfigBtn.addEventListener("click", async () => {
    try {
      await loadConfig();
      setStatusBar("Configuracoes recarregadas do disco.");
    } catch (error) {
      appendLog(error.message || String(error), "ERROR", "nfse.gui");
    }
  });

  ui.openConfigBtn.addEventListener("click", openConfigInEditor);

  document.addEventListener("keydown", async (event) => {
    if (!event.ctrlKey) {
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      try {
        await startExecution();
      } catch (error) {
        appendLog(error.message || String(error), "ERROR", "nfse.gui");
      }
      return;
    }
    if (event.key.toLowerCase() === "l") {
      event.preventDefault();
      clearLogs();
    }
  });
}

function bindRunEvents() {
  state.disposeRunListener = window.nfseApi.onRunEvent((eventPayload) => {
    if (!eventPayload || typeof eventPayload !== "object") {
      return;
    }

    if (eventPayload.event === "log") {
      appendLog(
        eventPayload.message || "",
        eventPayload.level || "INFO",
        eventPayload.logger || "nfse",
        eventPayload.timestamp || nowTime()
      );
      return;
    }

    if (eventPayload.event === "state") {
      if (eventPayload.state === "canceling") {
        ui.cardStatus.textContent = "Cancelando...";
        setTopStatus("Cancelando", "warning");
        setStatusBar("Cancelando execucao em andamento...");
      }
      if (eventPayload.message) {
        appendLog(eventPayload.message, "INFO", "nfse.gui");
      }
      return;
    }

    if (eventPayload.event === "finished") {
      onRunFinished(eventPayload.status, eventPayload.message, eventPayload.error);
    }
  });
}

async function bootstrap() {
  if (!window.nfseApi) {
    ui.logsList.textContent = "Erro: bridge Electron nao disponivel.";
    return;
  }

  bindEvents();
  bindRunEvents();
  setDefaultDates();
  toggleDateInputs();
  updateCnpjsCard();
  setFilter("ALL");
  setTopStatus("Pronto", "ok");

  try {
    await loadConfig();
    setStatusBar("Pronto para executar.");
    appendLog("Interface pronta para uso.", "INFO", "nfse.gui");
  } catch (error) {
    appendLog(error.message || String(error), "ERROR", "nfse.gui");
    setStatusBar("Falha ao carregar configuracoes.");
  }
}

bootstrap();
