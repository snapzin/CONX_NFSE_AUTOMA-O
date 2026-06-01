import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { AnimatePresence, motion } from 'framer-motion';
import './styles.css';

const api = {
  async call(method, endpoint, body) {
    // Caminho normal: IPC via preload (Electron) — inclui x-api-token automaticamente
    if (window.electronAPI?.apiCall) {
      return window.electronAPI.apiCall(method, endpoint, body ?? null);
    }

    // Fallback para dev mode sem Electron (ex: Vite direto no browser)
    // Nesse contexto NFSE_API_TOKEN não está definido no servidor, então sem auth.
    const response = await fetch(`http://127.0.0.1:17432${endpoint}`, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: body && Object.keys(body).length ? JSON.stringify(body) : undefined,
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`HTTP ${response.status}: ${text}`);
    }

    return response.json();
  },
  get(endpoint) {
    return this.call('GET', endpoint);
  },
  post(endpoint, body = null) {
    return this.call('POST', endpoint, body);
  },
};

// Senha do modo Desenvolvedor. Altere antes de usar em producao.
const DEV_PASSWORD = 'dev@2024';

const Icon = {
  Play: () => (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M4 2.5L13 8L4 13.5V2.5Z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
    </svg>
  ),
  Users: () => (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="6" cy="5" r="2.4" stroke="currentColor" strokeWidth="1.3" />
      <path d="M1.5 14c0-2.49 2.01-4.5 4.5-4.5s4.5 2.01 4.5 4.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
      <path d="M10.5 4.2a2.2 2.2 0 1 1 0 4.4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
      <path d="M11.5 9.8c1.7.4 3 1.9 3 3.7" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  ),
  Settings: () => (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="8" cy="8" r="2.2" stroke="currentColor" strokeWidth="1.3" />
      <path d="M8 1.5v1.8M8 12.7v1.8M14.5 8h-1.8M3.3 8H1.5M12.6 3.4l-1.3 1.3M4.7 11.3l-1.3 1.3M12.6 12.6l-1.3-1.3M4.7 4.7L3.4 3.4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  ),
  Info: () => (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.3" />
      <path d="M8 7v4M8 5v.4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  ),
  Lock: () => (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="3" y="7" width="10" height="7" rx="1" stroke="currentColor" strokeWidth="1.3" />
      <path d="M5 7V5a3 3 0 0 1 6 0v2" stroke="currentColor" strokeWidth="1.3" />
    </svg>
  ),
  Code: () => (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M5 4L1.5 8L5 12M11 4l3.5 4L11 12M9.5 3l-3 10" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  Check: () => (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M3 8.5L6.5 12L13 4.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  Cross: () => (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  Spinner: () => (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" className="spin">
      <path d="M8 1.5a6.5 6.5 0 1 1-6.5 6.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
};

const navItems = [
  { id: 'executar', label: 'Executar', icon: <Icon.Play /> },
  { id: 'clientes', label: 'Clientes', icon: <Icon.Users /> },
  { id: 'config', label: 'Configurações', icon: <Icon.Settings /> },
  { id: 'sobre', label: 'Sobre', icon: <Icon.Info /> },
  { id: 'dev', label: 'Desenvolvedor', icon: <Icon.Code />, requiresAuth: true },
];

const titles = {
  executar: 'Executar',
  clientes: 'Clientes',
  config: 'Configuracoes',
  sobre: 'Sobre',
  dev: 'Desenvolvedor',
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
  const [status, setStatus] = useState('Pronto');
  const [devUnlocked, setDevUnlocked] = useState(false);
  const [showPwdModal, setShowPwdModal] = useState(false);
  const [sharedJobLogs, setSharedJobLogs] = useState([]);
  const [sharedJobStatus, setSharedJobStatus] = useState('Pronto');
  const [license, setLicense] = useState({ licensed: null, message: '', key_hint: null });
  const [showActivateModal, setShowActivateModal] = useState(false);
  const [onboarding, setOnboarding] = useState(false);
  const [onboardingSuggestions, setOnboardingSuggestions] = useState({});
  const { toasts, push } = useToasts();

  useEffect(() => {
    // Mostra o onboarding apenas se os caminhos NAO foram resolvidos
    // automaticamente (pasta de certificados inexistente ou sem .pfx).
    // As sugestoes auto-detectadas pre-preenchem o wizard.
    api.get('/paths/status').then((status) => {
      if (status?.needsSetup) {
        setOnboardingSuggestions(status.suggestions || {});
        setOnboarding(true);
      }
    }).catch(() => {});
  }, []);

  const refreshLicense = useCallback(async () => {
    try {
      const result = await api.get('/license/status');
      setLicense(result);
    } catch {
      setLicense({ licensed: false, message: 'Servidor indisponível.', key_hint: null });
    }
  }, []);

  useEffect(() => { refreshLicense(); }, [refreshLicense]);

  useEffect(() => {
    document.documentElement.dataset.theme = 'dark';
  }, []);

  const tryGoToPage = (targetPage) => {
    const navItem = navItems.find((n) => n.id === targetPage);
    if (navItem?.requiresAuth && !devUnlocked) {
      setShowPwdModal(true);
      return;
    }
    setPage(targetPage);
  };

  const handlePwdSubmit = (pwd) => {
    if (pwd === DEV_PASSWORD) {
      setDevUnlocked(true);
      setShowPwdModal(false);
      setPage('dev');
      push('Modo desenvolvedor desbloqueado.', 'success');
    } else {
      push('Senha incorreta.', 'error');
    }
  };

  if (onboarding) {
    return (
      <OnboardingWizard
        api={api}
        suggestions={onboardingSuggestions}
        onComplete={() => setOnboarding(false)}
      />
    );
  }

  return (
    <div className="app-shell">
      <Sidebar
        page={page}
        setPage={tryGoToPage}
        devUnlocked={devUnlocked}
        onLockDev={() => { setDevUnlocked(false); setPage('executar'); push('Modo dev bloqueado.', 'info'); }}
      />
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
                <ExecutarPage
                  api={api}
                  toast={push}
                  setStatus={setStatus}
                  onLogsUpdate={setSharedJobLogs}
                  onJobStatusUpdate={setSharedJobStatus}
                  license={license}
                  onActivate={() => setShowActivateModal(true)}
                />
              )}
              {page === 'clientes' && <ClientesPage api={api} toast={push} />}
              {page === 'config' && <ConfigPage api={api} toast={push} />}
              {page === 'sobre' && <SobrePage />}
              {page === 'dev' && devUnlocked && (
                <DeveloperPage
                  api={api}
                  toast={push}
                  logs={sharedJobLogs}
                  jobStatus={sharedJobStatus}
                />
              )}
            </motion.div>
          </AnimatePresence>
        </section>

        <footer className="statusbar">{status === 'Pronto' ? 'Pronto para executar.' : status}</footer>
      </main>
      <ToastViewport toasts={toasts} />
      {showActivateModal && (
        <ActivationModal
          api={api}
          onSuccess={() => {
            setShowActivateModal(false);
            refreshLicense();
            push('Licença ativada com sucesso!', 'success');
          }}
          onCancel={() => setShowActivateModal(false)}
          toast={push}
        />
      )}
      {showPwdModal && (
        <PasswordModal
          onSubmit={handlePwdSubmit}
          onCancel={() => setShowPwdModal(false)}
        />
      )}
    </div>
  );
}

function PasswordModal({ onSubmit, onCancel }) {
  const [pwd, setPwd] = useState('');
  const inputRef = useRef(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const submit = (e) => {
    e?.preventDefault?.();
    onSubmit(pwd);
  };

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <form className="modal-box" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <div className="modal-icon"><Icon.Lock /></div>
        <h3>Acesso restrito</h3>
        <p>Digite a senha de desenvolvedor para visualizar logs técnicos.</p>
        <input
          ref={inputRef}
          type="password"
          value={pwd}
          onChange={(e) => setPwd(e.target.value)}
          placeholder="••••••"
          className="modal-input"
        />
        <div className="modal-actions">
          <button type="button" className="btn-secondary" onClick={onCancel}>Cancelar</button>
          <button type="submit" className="btn-primary">Entrar</button>
        </div>
      </form>
    </div>
  );
}

const ONBOARDING_STEPS = [
  { id: 'welcome' },
  { id: 'certs',  key: 'PASTA_CERTS' },
  { id: 'saida',  key: 'PASTA_SAIDA' },
  { id: 'done' },
];

function OnboardingWizard({ api, suggestions, onComplete }) {
  const [step, setStep] = useState(0);
  const [pastaCerts, setPastaCerts] = useState(suggestions?.PASTA_CERTS || '');
  const [pastaSaida, setPastaSaida] = useState(suggestions?.PASTA_SAIDA || '');
  const [saving, setSaving] = useState(false);

  const selectFolder = async (setter) => {
    const path = await window.electronAPI?.selectFolder?.();
    if (path) setter(path);
  };

  const finish = async () => {
    setSaving(true);
    try {
      const current = await api.get('/config');
      const values = { ...(current?.values || {}), PASTA_CERTS: pastaCerts, PASTA_SAIDA: pastaSaida };
      await api.post('/config', values);
      onComplete();
    } catch {
      onComplete();
    } finally {
      setSaving(false);
    }
  };

  const canNext = step === 1 ? !!pastaCerts : step === 2 ? !!pastaSaida : true;

  return (
    <div className="onboarding-backdrop">
      <motion.div
        className="onboarding-box"
        key={step}
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.22 }}
      >
        {/* Progress dots */}
        <div className="onboarding-dots">
          {ONBOARDING_STEPS.map((_, i) => (
            <span key={i} className={`onboarding-dot ${i === step ? 'active' : i < step ? 'done' : ''}`} />
          ))}
        </div>

        {/* Step: Welcome */}
        {step === 0 && (
          <>
            <div className="onboarding-icon">
              <img src="./conx-logo.png" alt="CONX" style={{ width: 120 }} />
            </div>
            <h2 className="onboarding-title">Bem-vindo ao NFSe Automação</h2>
            <p className="onboarding-desc">
              Vamos configurar o sistema em menos de 1 minuto.<br />
              Você só precisa indicar onde estão seus certificados digitais e onde quer salvar as notas.
            </p>
          </>
        )}

        {/* Step: Pasta certificados */}
        {step === 1 && (
          <>
            <div className="onboarding-step-num">Passo 1 de 2</div>
            <h2 className="onboarding-title">Pasta dos certificados</h2>
            <p className="onboarding-desc">
              Selecione a pasta onde estão os arquivos <strong>.pfx</strong> dos certificados digitais dos seus clientes.
              O sistema vai ler todos automaticamente.
            </p>
            <div className="onboarding-field">
              <input
                type="text"
                value={pastaCerts}
                onChange={(e) => setPastaCerts(e.target.value)}
                placeholder="Ex: C:\Certificados ou /Users/você/Certificados"
                readOnly
              />
              <button className="btn-secondary" type="button" onClick={() => selectFolder(setPastaCerts)}>
                Selecionar pasta
              </button>
            </div>
            {pastaCerts && (
              <div className="onboarding-path-ok">
                <Icon.Check /> {pastaCerts}
              </div>
            )}
          </>
        )}

        {/* Step: Pasta saída */}
        {step === 2 && (
          <>
            <div className="onboarding-step-num">Passo 2 de 2</div>
            <h2 className="onboarding-title">Pasta de destino dos XMLs</h2>
            <p className="onboarding-desc">
              Selecione a pasta onde as notas fiscais baixadas serão salvas.<br />
              O sistema criará subpastas por CNPJ automaticamente.
            </p>
            <div className="onboarding-field">
              <input
                type="text"
                value={pastaSaida}
                onChange={(e) => setPastaSaida(e.target.value)}
                placeholder="Ex: C:\NFSe\Downloads"
                readOnly
              />
              <button className="btn-secondary" type="button" onClick={() => selectFolder(setPastaSaida)}>
                Selecionar pasta
              </button>
            </div>
            {pastaSaida && (
              <div className="onboarding-path-ok">
                <Icon.Check /> {pastaSaida}
              </div>
            )}
          </>
        )}

        {/* Step: Done */}
        {step === 3 && (
          <>
            <div className="onboarding-done-icon"><Icon.Check /></div>
            <h2 className="onboarding-title">Tudo pronto!</h2>
            <p className="onboarding-desc">
              As configurações foram salvas. Clique em <strong>Começar</strong> para acessar o sistema.
            </p>
          </>
        )}

        {/* Actions */}
        <div className="onboarding-actions">
          {step > 0 && step < 3 && (
            <button className="btn-secondary" type="button" onClick={() => setStep(s => s - 1)}>
              Voltar
            </button>
          )}
          {step < 2 && (
            <button className="btn-primary" type="button" onClick={() => setStep(s => s + 1)} disabled={!canNext}>
              {step === 0 ? 'Começar configuração' : 'Próximo'}
            </button>
          )}
          {step === 2 && (
            <button className="btn-primary" type="button" onClick={() => { finish(); setStep(3); }} disabled={!canNext || saving}>
              {saving ? <Icon.Spinner /> : null} Salvar e continuar
            </button>
          )}
          {step === 3 && (
            <button className="btn-primary" type="button" onClick={onComplete}>
              Começar
            </button>
          )}
        </div>
      </motion.div>
    </div>
  );
}

function ActivationModal({ api, onSuccess, onCancel, toast }) {
  const [key, setKey] = useState('');
  const [loading, setLoading] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

  const formatKey = (value) => {
    const clean = value.toUpperCase().replace(/[^A-Z0-9]/g, '');
    const parts = clean.match(/.{1,4}/g) || [];
    return parts.slice(0, 5).join('-');
  };

  const submit = async (e) => {
    e?.preventDefault?.();
    if (!key.trim()) return;
    setLoading(true);
    try {
      await api.post('/license/activate', { key: key.replace(/-/g, '') });
      onSuccess();
    } catch (err) {
      const msg = err?.message?.replace(/^HTTP \d+: /, '') || 'Chave inválida.';
      toast(msg, 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <form className="modal-box" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <div className="modal-icon"><Icon.Lock /></div>
        <h3>Ativar licença</h3>
        <p>Insira a chave de ativação fornecida pela CONX Contabilidade.</p>
        <input
          ref={inputRef}
          type="text"
          value={key}
          onChange={(e) => setKey(formatKey(e.target.value))}
          placeholder="NFSE-XXXX-XXXX-XXXX-XXXX"
          className="modal-input"
          maxLength={24}
          spellCheck={false}
          autoComplete="off"
        />
        <div className="modal-actions">
          <button type="button" className="btn-secondary" onClick={onCancel} disabled={loading}>Cancelar</button>
          <button type="submit" className="btn-primary" disabled={loading || key.length < 4}>
            {loading ? <Icon.Spinner /> : null} Ativar
          </button>
        </div>
        <p style={{ marginTop: 16, fontSize: 11, color: 'var(--text-2)' }}>
          Para adquirir uma licença: conxcontabil@gmail.com
        </p>
      </form>
    </div>
  );
}

function LicenseBanner({ license, onActivate }) {
  if (license.licensed === null) return null;
  if (license.licensed === true) return null;

  return (
    <div className="license-banner">
      <div className="license-banner-icon"><Icon.Lock /></div>
      <div className="license-banner-text">
        <strong>Licença não ativada</strong>
        <span>{license.message}</span>
      </div>
      <button className="btn-primary" type="button" onClick={onActivate}>
        Ativar agora
      </button>
    </div>
  );
}

function Sidebar({ page, setPage, devUnlocked, onLockDev }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <img src="./conx-logo.png" alt="CONX" className="logo-img" />
      </div>
      <nav className="sidebar-nav">
        {navItems.map((item) => {
          const isLocked = item.requiresAuth && !devUnlocked;
          return (
            <button
              key={item.id}
              className={`nav-btn ${page === item.id ? 'active' : ''} ${isLocked ? 'nav-btn-locked' : ''}`}
              type="button"
              onClick={() => setPage(item.id)}
              title={isLocked ? `${item.label} (requer senha)` : item.label}
            >
              <span className="nav-icon">{item.icon}</span>
              <span className="nav-label">{item.label}</span>
              {isLocked && <span className="nav-lock"><Icon.Lock /></span>}
              {item.requiresAuth && devUnlocked && (
                <span
                  className="nav-unlock-action"
                  onClick={(e) => { e.stopPropagation(); onLockDev?.(); }}
                  title="Bloquear modo dev"
                >×</span>
              )}
            </button>
          );
        })}
      </nav>
      <div className="sidebar-footer-brand">
        Automação NFSe<br />v2.3
      </div>
    </aside>
  );
}

function parseProgress(logs) {
  let total = 0;
  const clients = [];

  for (const log of logs || []) {
    const msg = String(log.message || '');

    const totalM = msg.match(/CNPJs alvo:\s*(\d+)/);
    if (totalM) total = Math.max(total, parseInt(totalM[1], 10));

    const clientM = msg.match(/\[(\d+)\/(\d+)\]\s+Cliente XLSX:\s+'([^']*)'\s+\(CNPJ\s+(\d+)/);
    if (clientM) {
      // Marca anterior como ok se ainda estava 'running'
      if (clients.length > 0 && clients[clients.length - 1].status === 'running') {
        clients[clients.length - 1].status = 'ok';
      }
      const idx = parseInt(clientM[1], 10);
      const tot = parseInt(clientM[2], 10);
      total = Math.max(total, tot);
      clients.push({
        idx,
        cnpj: clientM[4],
        nome: clientM[3] || clientM[4],
        status: 'running',
        message: '',
      });
      continue;
    }

    if (String(log.level || '').toUpperCase() === 'ERROR' && clients.length > 0) {
      const last = clients[clients.length - 1];
      last.status = 'error';
      let errMsg = msg.replace(/\[[^\]]+\]\s*Falha\s+na\s+automacao\s+local:\s*/i, '');
      errMsg = errMsg.split('\n')[0].slice(0, 240);
      last.message = errMsg;
    }
  }

  return { total, clients };
}

function ExecutarPage({ api, toast, setStatus, onLogsUpdate, onJobStatusUpdate, license, onActivate }) {
  const [usePrevMonth, setUsePrevMonth] = useState(true);
  const [tipoNota, setTipoNota] = useState('ambas'); // 'emitidas' | 'recebidas' | 'ambas'
  const [jobId, setJobId] = useState(null);
  const [jobStatus, setJobStatus] = useState('Pronto');
  const [logs, setLogs] = useState([]);
  const [busy, setBusy] = useState(false);

  // Datas padrao = primeiro/ultimo dia do mes anterior (formato ISO yyyy-mm-dd)
  const calcMesAnterior = () => {
    const hoje = new Date();
    const fimAnt = new Date(hoje.getFullYear(), hoje.getMonth(), 0);
    const inicioAnt = new Date(fimAnt.getFullYear(), fimAnt.getMonth(), 1);
    const fmt = (d) => d.toISOString().slice(0, 10);
    return { inicio: fmt(inicioAnt), fim: fmt(fimAnt) };
  };
  const [{ inicio: defaultInicio, fim: defaultFim }] = useState(calcMesAnterior);
  const [dataInicio, setDataInicio] = useState(defaultInicio);
  const [dataFim, setDataFim] = useState(defaultFim);

  // Compartilha logs/status com a tela Desenvolvedor
  useEffect(() => { onLogsUpdate?.(logs); }, [logs, onLogsUpdate]);
  useEffect(() => { onJobStatusUpdate?.(jobStatus); }, [jobStatus, onJobStatusUpdate]);

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

  // ISO yyyy-mm-dd -> BR dd/mm/yyyy (formato esperado pelo backend)
  const isoToBr = (iso) => {
    if (!iso) return null;
    const [y, m, d] = iso.split('-');
    return `${d}/${m}/${y}`;
  };

  const execute = async () => {
    if (!usePrevMonth) {
      if (!dataInicio || !dataFim) {
        toast('Informe data inicial e final.', 'warning');
        return;
      }
      if (dataInicio > dataFim) {
        toast('Data inicial deve ser menor ou igual a data final.', 'warning');
        return;
      }
    }
    try {
      setBusy(true);
      setLogs([]);
      setJobStatus('Executando');
      setStatus('Executando automacao');
      const result = await api.post('/executar', {
        dataInicio: usePrevMonth ? null : isoToBr(dataInicio),
        dataFim: usePrevMonth ? null : isoToBr(dataFim),
        cnpjs: null,
        tipos: tipoNota,
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

  const isoToBrShort = (iso) => {
    if (!iso) return '-';
    const [y, m, d] = iso.split('-');
    return `${d}/${m}/${y.slice(2)}`;
  };
  const periodoStat = usePrevMonth
    ? 'Mês anterior'
    : (dataInicio && dataFim ? `${isoToBrShort(dataInicio)} → ${isoToBrShort(dataFim)}` : 'Manual');

  const progress = parseProgress(logs);
  const okCount = progress.clients.filter((c) => c.status === 'ok').length;
  const errCount = progress.clients.filter((c) => c.status === 'error').length;
  const runningCount = progress.clients.filter((c) => c.status === 'running').length;
  const processed = okCount + errCount;
  const totalEsperado = Math.max(progress.total, progress.clients.length);
  const pct = totalEsperado > 0 ? Math.round((processed / totalEsperado) * 100) : 0;
  const currentClient = progress.clients.find((c) => c.status === 'running');

  const stats = [
    ['Status', jobStatus],
    ['Período', periodoStat],
    ['Progresso', totalEsperado > 0 ? `${processed} / ${totalEsperado}` : '—'],
    ['Erros', String(errCount)],
  ];

  const isLicensed = license?.licensed === true;

  return (
    <div className="page-inner">
      <LicenseBanner license={license} onActivate={onActivate} />
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

        <div className="tipo-row">
          <span className="tipo-label">Tipo de nota</span>
          <div className="tipo-options">
            {[['emitidas', 'Emitidas'], ['recebidas', 'Recebidas'], ['ambas', 'Ambas']].map(([val, label]) => (
              <button
                key={val}
                type="button"
                className={tipoNota === val ? 'btn-primary' : 'btn-secondary'}
                onClick={() => setTipoNota(val)}
                style={{ padding: '6px 16px' }}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <label className="check-row">
          <input
            type="checkbox"
            checked={usePrevMonth}
            onChange={(event) => setUsePrevMonth(event.target.checked)}
          />
          Usar mês anterior automaticamente
        </label>

        {!usePrevMonth && (
          <div className="date-range">
            <div className="date-field">
              <span>Data inicial</span>
              <input
                type="date"
                value={dataInicio}
                onChange={(e) => setDataInicio(e.target.value)}
                max={dataFim || undefined}
              />
            </div>
            <div className="date-field">
              <span>Data final</span>
              <input
                type="date"
                value={dataFim}
                onChange={(e) => setDataFim(e.target.value)}
                min={dataInicio || undefined}
              />
            </div>
          </div>
        )}

        <div className="form-actions">
          <button className="btn-primary" type="button" onClick={execute} disabled={busy || !isLicensed}>
            Executar agora
          </button>
          {!isLicensed && license?.licensed === false && (
            <span className="license-inline-hint" onClick={onActivate}>
              <Icon.Lock /> Licença necessária — clique para ativar
            </span>
          )}
          {busy && (
            <button className="btn-danger" type="button" onClick={cancel}>
              Cancelar
            </button>
          )}
        </div>
      </div>

      {totalEsperado > 0 && (
        <div className="progress-box">
          <div className="progress-header">
            <div className="progress-title">
              {busy && runningCount > 0
                ? `Processando ${processed + 1} de ${totalEsperado}`
                : busy
                  ? 'Iniciando...'
                  : `${processed} de ${totalEsperado} processado(s)`}
            </div>
            <div className="progress-pct">{pct}%</div>
          </div>
          <div className="progress-bar">
            <div className="progress-bar-fill" style={{ width: `${pct}%` }} />
          </div>

          {currentClient && (
            <div className="progress-current">
              <Icon.Spinner />
              <span>{currentClient.nome}</span>
              <span className="progress-current-cnpj">CNPJ {currentClient.cnpj}</span>
            </div>
          )}

          {progress.clients.length > 0 && (
            <div className="progress-list">
              {progress.clients.map((c) => (
                <div className={`progress-item progress-${c.status}`} key={`${c.idx}-${c.cnpj}`}>
                  <span className="progress-item-icon">
                    {c.status === 'ok' && <Icon.Check />}
                    {c.status === 'error' && <Icon.Cross />}
                    {c.status === 'running' && <Icon.Spinner />}
                  </span>
                  <span className="progress-item-nome">{c.nome}</span>
                  {c.status === 'error' && c.message && (
                    <span className="progress-item-msg" title={c.message}>{c.message}</span>
                  )}
                </div>
              ))}
            </div>
          )}

          {!busy && processed > 0 && (
            <div className="progress-summary">
              <span><Icon.Check /> {okCount} concluído(s)</span>
              {errCount > 0 && <span className="err"><Icon.Cross /> {errCount} com erro</span>}
            </div>
          )}
        </div>
      )}

      {totalEsperado === 0 && !busy && (
        <div className="empty-progress">
          <p>Clique em <strong>Executar agora</strong> para iniciar o download das notas.</p>
        </div>
      )}
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

function ClientesPage({ api, toast }) {
  const [clientes, setClientes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [filtro, setFiltro] = useState('');
  const [pathInfo, setPathInfo] = useState('');

  const carregar = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/clientes');
      setClientes((res?.clientes || []).map((c) => ({ ...c })));
      setPathInfo(res?.path || '');
    } catch (err) {
      toast(`Falha ao carregar clientes: ${err?.message || err}`, 'error');
    } finally {
      setLoading(false);
    }
  }, [api, toast]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  const formatarDoc = (raw) => {
    const d = String(raw || '').replace(/\D/g, '');
    if (d.length === 11) {
      return d.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, '$1.$2.$3-$4');
    }
    if (d.length === 14) {
      return d.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, '$1.$2.$3/$4-$5');
    }
    return raw;
  };

  const adicionar = () => {
    setClientes((cs) => [...cs, { documento: '', nome: '' }]);
  };

  const remover = (idx) => {
    setClientes((cs) => cs.filter((_, i) => i !== idx));
  };

  const editar = (idx, campo, valor) => {
    setClientes((cs) => cs.map((c, i) => (i === idx ? { ...c, [campo]: valor } : c)));
  };

  const salvar = async () => {
    setSaving(true);
    try {
      const payload = {
        clientes: clientes
          .map((c) => ({
            documento: String(c.documento || '').replace(/\D/g, ''),
            nome: String(c.nome || '').trim(),
          }))
          .filter((c) => c.documento || c.nome),
      };
      const res = await api.post('/clientes', payload);
      toast(`${res?.salvos ?? payload.clientes.length} cliente(s) salvo(s).`, 'success');
    } catch (err) {
      toast(`Falha ao salvar: ${err?.message || err}`, 'error');
    } finally {
      setSaving(false);
    }
  };

  const filtrados = clientes
    .map((c, idx) => ({ ...c, _idx: idx }))
    .filter((c) => {
      if (!filtro) return true;
      const f = filtro.toLowerCase();
      const doc = String(c.documento || '').replace(/\D/g, '');
      return doc.includes(f.replace(/\D/g, '')) ||
             String(c.nome || '').toLowerCase().includes(f);
    });

  return (
    <div className="page-inner">
      <div className="clientes-toolbar">
        <input
          type="text"
          placeholder="Filtrar por CNPJ/CPF ou nome..."
          value={filtro}
          onChange={(e) => setFiltro(e.target.value)}
          className="clientes-filter"
        />
        <div className="clientes-actions">
          <button type="button" className="btn-secondary" onClick={carregar} disabled={loading}>
            Recarregar
          </button>
          <button type="button" className="btn-secondary" onClick={adicionar}>
            + Adicionar
          </button>
          <button type="button" className="btn-primary" onClick={salvar} disabled={saving}>
            {saving ? 'Salvando...' : 'Salvar'}
          </button>
        </div>
      </div>

      {pathInfo && (
        <div className="clientes-path">Arquivo: {pathInfo}</div>
      )}

      <div className="clientes-table-wrap">
        <table className="clientes-table">
          <thead>
            <tr>
              <th style={{ width: '40px' }}>#</th>
              <th style={{ width: '180px' }}>CNPJ / CPF</th>
              <th>Nome do Cliente</th>
              <th style={{ width: '60px' }}></th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan="4" className="clientes-empty">Carregando...</td></tr>
            )}
            {!loading && filtrados.length === 0 && (
              <tr>
                <td colSpan="4" className="clientes-empty">
                  {clientes.length === 0
                    ? 'Nenhum cliente cadastrado. Clique em "+ Adicionar".'
                    : 'Nenhum resultado para o filtro.'}
                </td>
              </tr>
            )}
            {!loading && filtrados.map((c) => (
              <tr key={c._idx}>
                <td className="clientes-idx">{c._idx + 1}</td>
                <td>
                  <input
                    type="text"
                    value={c.documento || ''}
                    placeholder="00.000.000/0000-00"
                    onChange={(e) => editar(c._idx, 'documento', e.target.value)}
                    onBlur={(e) => editar(c._idx, 'documento', formatarDoc(e.target.value))}
                  />
                </td>
                <td>
                  <input
                    type="text"
                    value={c.nome || ''}
                    placeholder="Nome / Razão social"
                    onChange={(e) => editar(c._idx, 'nome', e.target.value)}
                  />
                </td>
                <td>
                  <button
                    type="button"
                    className="btn-row-remove"
                    onClick={() => remover(c._idx)}
                    title="Remover"
                  >×</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="clientes-count">
        Total: {clientes.length} cliente(s)
      </div>
    </div>
  );
}

function DeveloperPage({ api, toast, logs, jobStatus }) {
  const [filter, setFilter] = useState('');
  const [level, setLevel] = useState('all');
  const [autoScroll, setAutoScroll] = useState(true);
  const [systemInfo, setSystemInfo] = useState(null);
  const [licenseInfo, setLicenseInfo] = useState(null);
  const [deactivating, setDeactivating] = useState(false);
  const logsRef = useRef(null);

  const fetchInfo = useCallback(async () => {
    try {
      const cfg = await api.get('/config');
      const certs = await api.get('/certificados').catch(() => null);
      setSystemInfo({ cfg, certs });
    } catch (e) {
      // silencioso
    }
  }, [api]);

  const fetchLicense = useCallback(async () => {
    try {
      const result = await api.get('/license/status');
      setLicenseInfo(result);
    } catch {
      setLicenseInfo(null);
    }
  }, [api]);

  const deactivateLicense = async () => {
    if (!window.confirm('Desativar a licença? O sistema ficará bloqueado até uma nova ativação.')) return;
    setDeactivating(true);
    try {
      await api.post('/license/deactivate');
      toast('Licença desativada.', 'warning');
      fetchLicense();
    } catch {
      toast('Erro ao desativar licença.', 'error');
    } finally {
      setDeactivating(false);
    }
  };

  useEffect(() => { fetchInfo(); fetchLicense(); }, [fetchInfo, fetchLicense]);

  useEffect(() => {
    if (autoScroll && logsRef.current) {
      logsRef.current.scrollTop = logsRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  const filtered = (logs || []).filter((log) => {
    if (level !== 'all' && String(log.level || '').toUpperCase() !== level.toUpperCase()) {
      return false;
    }
    if (filter && !String(log.message || '').toLowerCase().includes(filter.toLowerCase())) {
      return false;
    }
    return true;
  });

  const copyLogs = () => {
    const text = filtered
      .map((l) => `[${l.level}] ${l.message}`)
      .join('\n');
    if (navigator.clipboard && text) {
      navigator.clipboard.writeText(text);
      toast('Logs copiados.', 'success');
    }
  };

  return (
    <div className="page-inner">
      <div className="dev-info-box">
        <h3>Informações do sistema</h3>
        {systemInfo ? (
          <div className="dev-info-grid">
            <div className="info-row"><span className="label">XLSX Path</span><span className="value">{systemInfo.cfg?.values?.XLSX_PATH || '—'}</span></div>
            <div className="info-row"><span className="label">Pasta certificados</span><span className="value">{systemInfo.cfg?.values?.PASTA_CERTS || '—'}</span></div>
            <div className="info-row"><span className="label">Pasta saída</span><span className="value">{systemInfo.cfg?.values?.PASTA_SAIDA || '—'}</span></div>
            <div className="info-row"><span className="label">Chrome User Data</span><span className="value">{systemInfo.cfg?.values?.CHROME_USER_DATA_DIR || '—'}</span></div>
            <div className="info-row"><span className="label">Extension ID</span><span className="value">{systemInfo.cfg?.values?.CHROME_EXTENSION_ID || '—'}</span></div>
            <div className="info-row"><span className="label">Status job atual</span><span className="value">{jobStatus || 'Pronto'}</span></div>
            {systemInfo.certs && (
              <>
                <div className="info-row"><span className="label">Certificados (total)</span><span className="value">{systemInfo.certs.total}</span></div>
                <div className="info-row"><span className="label">Válidos</span><span className="value">{systemInfo.certs.validos}</span></div>
                <div className="info-row"><span className="label">CNPJs únicos</span><span className="value">{systemInfo.certs.cnpjsUnicos}</span></div>
                <div className="info-row"><span className="label">CNPJs duplicados</span><span className="value">{systemInfo.certs.cnpjsDuplicados}</span></div>
              </>
            )}
          </div>
        ) : (
          <p style={{ color: 'var(--text-2)', fontSize: 12 }}>Carregando...</p>
        )}
        <div className="form-actions" style={{ marginTop: 14 }}>
          <button className="btn-secondary" type="button" onClick={fetchInfo}>Atualizar</button>
        </div>
      </div>

      <div className="dev-info-box">
        <h3>Licença</h3>
        {licenseInfo ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <span style={{ fontSize: 11, color: 'var(--text-2)' }}>Chave ativa</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: licenseInfo.licensed ? 'var(--success)' : 'var(--danger)', letterSpacing: '0.06em' }}>
                {licenseInfo.key_hint || '—'}
              </span>
              <span style={{ fontSize: 11, color: 'var(--text-2)', marginTop: 2 }}>{licenseInfo.message}</span>
            </div>
            {licenseInfo.key_hint && (
              <button
                className="btn-danger"
                type="button"
                onClick={deactivateLicense}
                disabled={deactivating}
              >
                {deactivating ? <Icon.Spinner /> : null}
                Desativar licença
              </button>
            )}
          </div>
        ) : (
          <p style={{ color: 'var(--text-2)', fontSize: 12 }}>Carregando...</p>
        )}
      </div>

      <div className="logs-box dev-logs-box">
        <h3>Logs técnicos</h3>
        <div className="dev-logs-toolbar">
          <input
            type="text"
            placeholder="Filtrar mensagem..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="dev-logs-filter"
          />
          <select
            value={level}
            onChange={(e) => setLevel(e.target.value)}
            className="dev-logs-level"
          >
            <option value="all">Todos</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
            <option value="CRITICAL">CRITICAL</option>
          </select>
          <label className="dev-logs-check">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
            />
            Auto-rolar
          </label>
          <button type="button" className="btn-secondary" onClick={copyLogs}>Copiar</button>
        </div>
        <div id="logs-panel" ref={logsRef}>
          {filtered.length === 0 && <div className="log-muted">Nenhum log para exibir.</div>}
          {filtered.map((log, index) => (
            <div className={`log-line log-${String(log.level).toLowerCase()}`} key={`${log.timestamp}-${index}`}>
              <span className="log-level">[{log.level}]</span> {log.message}
            </div>
          ))}
        </div>
      </div>
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
