/**
 * app.js - Roteador e inicializador do app
 */
document.addEventListener('DOMContentLoaded', async () => {
  // Aguarda backend estar pronto
  await Splash.waitForBackend();

  // Roteador de páginas
  const pages = {
    'executar': PageExecutar,
    'config': PageConfig,
    'sobre': PageSobre,
  };

  let currentPage = 'executar';

  const showPage = async (name) => {
    if (!pages[name]) return;

    const navBtns = document.querySelectorAll('.nav-btn');
    navBtns.forEach(btn => {
      btn.classList.toggle('active', btn.dataset.page === name);
    });

    const pageElements = document.querySelectorAll('.page');
    pageElements.forEach(page => {
      page.classList.toggle('active', page.id === `page-${name}`);
    });

    const titles = {
      'executar': 'Executar',
      'config': 'Configurações',
      'sobre': 'Sobre',
    };

    document.getElementById('page-title').textContent = titles[name] || name;
    currentPage = name;

    await pages[name].render();
  };

  // Event listeners
  document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => showPage(btn.dataset.page));
  });

  document.querySelectorAll('.theme-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.documentElement.dataset.theme = btn.dataset.theme;
    });
  });

  // Página inicial
  await showPage('executar');
});
