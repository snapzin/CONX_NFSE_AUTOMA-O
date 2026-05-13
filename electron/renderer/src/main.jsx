import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { AnimatePresence, motion } from 'framer-motion';
import './styles.css';

const api = {
  async call(method, endpoint, body) {
    if (window.electronAPI?.apiCall) {
      return window.electronAPI.apiCall(method, endpoint, body ?? null);
    }

    const response = await fetch(`http://127.0.0.1:17432${endpoint}`, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });

    if (!response.ok) {
      throw new Error(await response.text());
    }

    return response.json();
  },
  get(endpoint) {
    return this.call('GET', endpoint);
  },
  post(endpoint, body = {}) {
    return this.call('POST', endpoint, body);
  },
};

const navItems = [
  { id: 'executar', label: 'Executar', icon: '>' },
  { id: 'config', label: 'Configuracoes', icon: '*' },
  { id: 'sobre', label: 'Sobre', icon: 'i' },
];

const titles = {
  executar: 'Executar',
  config: 'Configuracoes',
  sobre: 'Sobre',
};

function useToasts() {
  const [toasts, setToasts] = useState([]);

  const push = useCallback((message, type = 'info') => {
    const id = window.crypto?.randomUUID ? window.crypto.randomUUID() : String(Date.now());
    setToasts((items) => [...items, { id, message, type }]);
    window.setTimeout(() => {
      setToasts((items) => items.filter((toast) => toast.id !== id));
    }, 4200);
  }, []);

  return { toasts, push };
}

function App() {
  const [page, setPage] = useState('executar');
  const [theme, setTheme] = useState('dark');
  const [status, setStatus] = useState('Pronto');
  const { toasts, push } = useToasts();

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  return (
    <div className="app-shell">
      <Sidebar page={page} setPage={setPage} theme={theme} setTheme={setTheme} />
      <main className="main-area">
        <header className="topbar">
          <h1>{titles[page]}</h1>
          <div className="topbar-status">
            <span className="status-badge" />
            <span>{status}</span>
          </div>
        </header>

        <section className="page-container">
          <AnimatePresence mode="wait">
            <motion.div
              key={page}
              className="page active"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            >
              {page === 'executar' && (
                <ExecutarPage api={api} toast={push} setStatus={setStatus} />
              )}
              {page === 'config' && <ConfigPage api={api} toast={push} />}
              {page === 'sobre' && <SobrePage />}
            </motion.div>
          </AnimatePresence>
        </section>

        <footer className="statusbar">{status === 'Pronto' ? 'Pronto para executar.' : status}</footer>
      </main>
      <ToastViewport toasts={toasts} />
    </div>
  );
}

function Sidebar({ page, setPage, theme, setTheme }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="logo">NFSe</div>
        <div className="version">Automacao - v2.3</div>
      </div>
      <nav className="sidebar-nav">
        {navItems.map((item) => (
          <button
            key={item.id}
            className={`nav-btn ${page === item.id ? 'active' : ''}`}
            type="button"
            onClick={() => setPage(item.id)}
            title={item.label}
          >
            <span className="nav-icon">{item.icon}</span>
            <span className="nav-label">{item.label}</span>
          </button>
        ))}
      </nav>
      <div className="sidebar-footer">
        <div className="theme-label">Tema</div>
        <div className="theme-selector">
          {['dark', 'light'].map((item) => (
            <button
              key={item}
              type="button"
              className={`theme-btn ${theme === item ? 'active' : ''}`}
              onClick={() => setTheme(item)}
            >
              {item === 'dark' ? 'Escuro' : 'Claro'}
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}

function ExecutarPage({ api, toast, setStatus }) {
  const [usePrevMonth, setUsePrevMonth] = useState(true);
  const [certStats, setCertStats] = useState(null);
  const [jobId, setJobId] = useState(null);
  const [jobStatus, setJobStatus] = useState('Pronto');
  const [logs, setLogs] = useState([]);
  const [busy, setBusy] = useState(false);
  const logsRef = useRef(null);

  useEffect(() => {
    logsRef.current?.scrollTo({ top: logsRef.current.scrollHeight });
  }, [logs]);

  useEffect(() => {
    if (!jobId) return undefined;

    let cancelled = false;
    let timer;

    const poll = async () => {
      try {
        const result = await api.get(`/executar/${jobId}/status`);
        if (cancelled) return;

        setLogs(result.logs ?? []);
        setJobStatus(formatStatus(result.status));
        setStatus(formatStatus(result.status));

        if (result.status === 'running') {
          timer = window.setTimeout(poll, 700);
        } else {
          setBusy(false);
          setJobId(null);
          toast(result.status === 'ok' ? 'Execucao concluida.' : `Execucao ${result.status}.`, result.status === 'ok' ? 'success' : 'warning');
        }
      } catch (error) {
        timer = window.setTimeout(poll, 1000);
      }
    };

    poll();

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [api, jobId, setStatus, toast]);

  const countCerts = async () => {
    try {
      setStatus('Contando certificados');
      const result = await api.get('/certificados?incluir_lista=false');
      setCertStats(result);
      setStatus('Pronto');
      toast(`${result.validos} certificados validos encontrados.`, 'success');
    } catch (error) {
      setStatus('Erro ao contar certificados');
      toast('Erro ao contar certificados.', 'error');
    }
  };

  const execute = async () => {
    try {
      setBusy(true);
      setLogs([]);
      setJobStatus('Executando');
      setStatus('Executando automacao');
      const result = await api.post('/executar', {
        dataInicio: usePrevMonth ? null : null,
        dataFim: usePrevMonth ? null : null,
        cnpjs: null,
      });
      setJobId(result.jobId);
      toast('Execucao iniciada.', 'info');
    } catch (error) {
      setBusy(false);
      setStatus('Erro ao iniciar');
      toast('Erro ao iniciar execucao.', 'error');
    }
  };

  const cancel = async () => {
    if (!jobId) return;
    try {
      await api.post(`/executar/${jobId}/cancelar`);
      toast('Cancelamento solicitado.', 'warning');
    } catch (error) {
      toast('Nao foi possivel cancelar.', 'error');
    }
  };

  const stats = [
    ['Status', jobStatus],
    ['Periodo', usePrevMonth ? 'Mes anterior' : 'Manual'],
    ['CNPJs', certStats ? String(certStats.cnpjsUnicos) : 'Todos'],
    ['Certificados', certStats ? `${certStats.validos}/${certStats.total}` : '-'],
  ];

  return (
    <div className="page-inner">
      <div className="stats-row">
        {stats.map(([label, value], index) => (
          <motion.div
            className="stat-card"
            key={label}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.04 }}
          >
            <div className="stat-title">{label}</div>
            <div className="stat-value">{value}</div>
          </motion.div>
        ))}
      </div>

      <div className="form-box">
        <h3>Parametros de execucao</h3>
        <label className="check-row">
          <input
            type="checkbox"
            checked={usePrevMonth}
            onChange={(event) => setUsePrevMonth(event.target.checked)}
          />
          Usar mes anterior automaticamente
        </label>
        <div className="form-actions">
          <button className="btn-secondary" type="button" onClick={countCerts} disabled={busy}>
            Contar certificados
          </button>
          <button className="btn-primary" type="button" onClick={execute} disabled={busy}>
            Executar agora
          </button>
          {busy && (
            <button className="btn-danger" type="button" onClick={cancel}>
              Cancelar
            </button>
          )}
        </div>
      </div>

      <div className="logs-box">
        <h3>Logs de execucao</h3>
        <div id="logs-panel" ref={logsRef}>
          {logs.length === 0 && <div className="log-muted">Aguardando execucao...</div>}
          {logs.map((log, index) => (
            <div className={`log-line log-${String(log.level).toLowerCase()}`} key={`${log.timestamp}-${index}`}>
              {log.message}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ConfigPage({ api, toast }) {
  const [loading, setLoading] = useState(true);
  const [sections, setSections] = useState([]);
  const [values, setValues] = useState({});

  const load = async () => {
    setLoading(true);
    try {
      const result = await api.get('/config');
      setSections(result.sections ?? []);
      setValues(result.values ?? {});
    } catch (error) {
      toast('Erro ao carregar configuracoes.', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const updateValue = (key, value) => {
    setValues((current) => ({ ...current, [key]: value }));
  };

  const save = async () => {
    try {
      await api.post('/config', values);
      toast('Configuracoes salvas.', 'success');
    } catch (error) {
      toast('Erro ao salvar configuracoes.', 'error');
    }
  };

  return (
    <div className="page-inner config-scroll">
      {loading && <div className="empty-state">Carregando configuracoes...</div>}
      {!loading &&
        sections.map((section) => (
          <motion.section
            className="config-section"
            key={section.title}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <h3>{section.title}</h3>
            {section.fields.map(([key, label, type]) => (
              <label className="config-field" key={key}>
                <span>{label}</span>
                <input
                  type={type === 'secret' ? 'password' : 'text'}
                  value={values[key] ?? ''}
                  onChange={(event) => updateValue(key, event.target.value)}
                />
              </label>
            ))}
          </motion.section>
        ))}
      <div className="config-actions">
        <button className="btn-primary" type="button" onClick={save} disabled={loading}>
          Salvar alteracoes
        </button>
        <button className="btn-secondary" type="button" onClick={load} disabled={loading}>
          Recarregar
        </button>
      </div>
    </div>
  );
}

function SobrePage() {
  const rows = useMemo(
    () => [
      ['Framework', 'Electron + React'],
      ['Animacoes', 'Framer Motion'],
      ['Backend', 'FastAPI + Python'],
      ['Automacao', 'Playwright'],
    ],
    [],
  );

  return (
    <div className="page-inner about-container">
      <motion.div
        className="about-card"
        initial={{ opacity: 0, scale: 0.98 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.22 }}
      >
        <h1>NFSe</h1>
        <h2>Automacao</h2>
        <p className="version">Versao 2.3</p>
        <p className="description">
          Automatiza o download de NFSe para multiplos clientes via Playwright local.
        </p>
        <div className="about-info">
          {rows.map(([label, value]) => (
            <div className="info-row" key={label}>
              <span className="label">{label}</span>
              <span className="value">{value}</span>
            </div>
          ))}
        </div>
      </motion.div>
    </div>
  );
}

function ToastViewport({ toasts }) {
  return (
    <div className="toast-container">
      <AnimatePresence>
        {toasts.map((toast) => (
          <motion.div
            className={`toast toast-${toast.type}`}
            key={toast.id}
            initial={{ opacity: 0, x: 24, scale: 0.98 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: 24, scale: 0.98 }}
          >
            {toast.message}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

function formatStatus(status) {
  const map = {
    running: 'Executando',
    ok: 'Concluido',
    cancelado: 'Cancelado',
    erro: 'Erro',
  };
  return map[status] ?? status ?? 'Pronto';
}

createRoot(document.getElementById('root')).render(<App />);
