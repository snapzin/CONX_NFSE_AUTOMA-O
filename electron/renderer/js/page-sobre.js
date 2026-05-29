/**
 * page-sobre.js - Página Sobre
 */
class PageSobre {
  static async render() {
    const content = document.querySelector('#page-sobre .page-content');
    content.innerHTML = `
      <div class="page-inner about-container">
        <div class="about-card">
          <h1>NFSe</h1>
          <h2>Automacao</h2>
          <p class="version">Versão 2.3</p>
          <p class="description">
            Automatiza o download de NFSe para múltiplos clientes<br>
            via Playwright local, sem dependência de API externa.
          </p>
          <p class="copyright">(c) CONX Contabilidade</p>

          <div class="about-info">
            <div class="info-row">
              <span class="label">Framework</span>
              <span class="value">Electron + FastAPI</span>
            </div>
            <div class="info-row">
              <span class="label">Backend</span>
              <span class="value">Python 3.12+</span>
            </div>
            <div class="info-row">
              <span class="label">Automação</span>
              <span class="value">Playwright</span>
            </div>
          </div>
        </div>
      </div>
    `;
  }
}
