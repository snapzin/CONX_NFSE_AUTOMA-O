/**
 * page-executar.js - Página de execução
 */
class PageExecutar {
  static _currentJobId = null;

  static async render() {
    const content = document.querySelector('#page-executar .page-content');
    content.innerHTML = `
      <div class="page-inner">
        <div class="stats-row">
          <div class="stat-card">
            <div class="stat-title">Status</div>
            <div class="stat-value">Pronto</div>
          </div>
          <div class="stat-card">
            <div class="stat-title">Período</div>
            <div class="stat-value" id="stat-period">Mês anterior</div>
          </div>
          <div class="stat-card">
            <div class="stat-title">CNPJs</div>
            <div class="stat-value">Todos</div>
          </div>
          <div class="stat-card">
            <div class="stat-title">Último</div>
            <div class="stat-value">-</div>
          </div>
        </div>

        <div class="form-box">
          <h3>Parâmetros de execução</h3>
          <div class="form-group">
            <label><input type="checkbox" id="use-prev-month" checked> Usar mês anterior automaticamente</label>
          </div>
          <div class="form-actions">
            <button id="btn-executar" class="btn-primary">▶ Executar agora</button>
            <button id="btn-cancelar" class="btn-danger" style="display:none;">Cancelar</button>
          </div>
        </div>

        <div class="logs-box">
          <h3>Logs de execução</h3>
          <div id="logs-panel"></div>
        </div>
      </div>
    `;

    PageExecutar.attachListeners();
  }

  static attachListeners() {
    document.getElementById('btn-executar').addEventListener('click', () => PageExecutar.execute());
    document.getElementById('btn-cancelar').addEventListener('click', () => PageExecutar.cancel());
  }

  static async execute() {
    try {
      document.getElementById('btn-executar').disabled = true;
      document.getElementById('btn-cancelar').disabled = false;
      document.getElementById('btn-cancelar').style.display = 'inline-block';

      const result = await API.startExecution(null, null, null);
      PageExecutar._currentJobId = result.jobId;
      PageExecutar.monitorJob(result.jobId);
    } catch (e) {
      ToastManager.show('Erro ao iniciar execução', 'error');
      document.getElementById('btn-executar').disabled = false;
      document.getElementById('btn-cancelar').style.display = 'none';
      PageExecutar._currentJobId = null;
    }
  }

  static async monitorJob(jobId) {
    const logsPanel = document.getElementById('logs-panel');
    logsPanel.innerHTML = '';
    let lastCount = 0;

    const poll = async () => {
      try {
        const status = await API.getJobStatus(jobId);

        status.logs.slice(lastCount).forEach(log => {
          const div = document.createElement('div');
          div.className = `log-line log-${log.level.toLowerCase()}`;
          div.textContent = log.message;
          logsPanel.appendChild(div);
          logsPanel.scrollTop = logsPanel.scrollHeight;
        });
        lastCount = status.logs.length;

        if (status.status === 'running') {
          setTimeout(poll, 500);
        } else {
          document.getElementById('btn-executar').disabled = false;
          const btnCancel = document.getElementById('btn-cancelar');
          btnCancel.disabled = true;
          btnCancel.style.display = 'none';
          btnCancel.textContent = 'Cancelar';
          PageExecutar._currentJobId = null;
          const msgMap = { ok: 'Execução concluída!', cancelado: 'Execução cancelada.' };
          const kindMap = { ok: 'success', cancelado: 'warning' };
          const msg = msgMap[status.status] || `Execução ${status.status}`;
          const kind = kindMap[status.status] || 'error';
          ToastManager.show(msg, kind);
        }
      } catch (e) {
        console.error(e);
        setTimeout(poll, 500);
      }
    };

    poll();
  }

  static async cancel() {
    if (!PageExecutar._currentJobId) {
      ToastManager.show('Nenhuma execução em andamento', 'warning');
      return;
    }
    try {
      document.getElementById('btn-cancelar').disabled = true;
      document.getElementById('btn-cancelar').textContent = 'Cancelando...';
      await API.cancelJob(PageExecutar._currentJobId);
      ToastManager.show('Cancelamento solicitado', 'warning');
    } catch (e) {
      ToastManager.show('Erro ao cancelar', 'error');
      document.getElementById('btn-cancelar').disabled = false;
      document.getElementById('btn-cancelar').textContent = 'Cancelar';
    }
  }
}
