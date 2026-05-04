/**
 * page-config.js - Página de configurações
 */
class PageConfig {
  static async render() {
    const content = document.querySelector('#page-config .page-content');
    content.innerHTML = `
      <div class="page-inner">
        <div class="config-scroll">
          <div id="config-sections"></div>
          <div class="config-actions">
            <button id="btn-save-config" class="btn-primary">Salvar alterações</button>
            <button id="btn-reload-config" class="btn-secondary">Recarregar</button>
          </div>
        </div>
      </div>
    `;

    try {
      const config = await API.getConfig();
      PageConfig.renderSections(config.sections, config.values);
      PageConfig.attachListeners();
    } catch (e) {
      content.innerHTML = `<p class="error">Erro ao carregar configurações: ${e}</p>`;
    }
  }

  static renderSections(sections, values) {
    const container = document.getElementById('config-sections');
    container.innerHTML = '';

    sections.forEach(section => {
      const sectionDiv = document.createElement('div');
      sectionDiv.className = 'config-section';
      sectionDiv.innerHTML = `<h3>${section.title}</h3>`;

      section.fields.forEach(([key, label, type]) => {
        const value = values[key] || '';
        const fieldDiv = document.createElement('div');
        fieldDiv.className = 'config-field';

        const isPath = type === 'path' || type === 'dir';
        const inputType = type === 'secret' ? 'password' : 'text';

        fieldDiv.innerHTML = `
          <label>${label}</label>
          <div class="config-field-input-group">
            <input type="${inputType}"
                   name="${key}"
                   value="${value}"
                   placeholder="${label}"
                   ${isPath ? 'readonly' : ''}>
            ${isPath ? `<button class="btn-browse" data-key="${key}" data-type="${type}">📁</button>` : ''}
          </div>
        `;
        sectionDiv.appendChild(fieldDiv);
      });

      container.appendChild(sectionDiv);
    });

    // Attach browse listeners
    document.querySelectorAll('.btn-browse').forEach(btn => {
      btn.addEventListener('click', () => PageConfig.browsePath(btn.dataset.key, btn.dataset.type));
    });
  }

  static async browsePath(key, type) {
    const input = document.querySelector(`input[name="${key}"]`);
    // Simula seleção de pasta (em produção, usaria Electron dialog)
    const newPath = prompt(`Selecione o caminho para ${key}:\n(Digite o caminho completo)`, input.value);
    if (newPath) {
      input.value = newPath;
    }
  }

  static attachListeners() {
    document.getElementById('btn-save-config').addEventListener('click', () => PageConfig.save());
    document.getElementById('btn-reload-config').addEventListener('click', () => PageConfig.render());
  }

  static async save() {
    const fields = document.querySelectorAll('.config-field input');
    const values = {};

    fields.forEach(field => {
      values[field.name] = field.value;
    });

    try {
      await API.setConfig(values);
      ToastManager.show('Configurações salvas com sucesso!', 'success');
    } catch (e) {
      ToastManager.show('Erro ao salvar configurações', 'error');
    }
  }
}
