/**
 * api.js - Cliente HTTP para FastAPI backend
 */
class API {
  static async get(endpoint) {
    return window.electronAPI.apiCall('GET', endpoint);
  }

  static async post(endpoint, body = {}) {
    return window.electronAPI.apiCall('POST', endpoint, body);
  }

  static async getConfig() {
    return this.get('/config');
  }

  static async setConfig(values) {
    return this.post('/config', values);
  }

  static async getCertificados(incluirLista = false) {
    return this.get(`/certificados?incluir_lista=${incluirLista}`);
  }

  static async startExecution(dataInicio, dataFim, cnpjs) {
    return this.post('/executar', {
      dataInicio,
      dataFim,
      cnpjs,
    });
  }

  static async getJobStatus(jobId) {
    return this.get(`/executar/${jobId}/status`);
  }

  static async cancelJob(jobId) {
    return this.post(`/executar/${jobId}/cancelar`);
  }
}
