/**
 * splash.js - Gerencia splash screen
 */
class Splash {
  static async waitForBackend() {
    const splash = document.getElementById('splash');
    const text = splash.querySelector('.splash-text');
    const messages = [
      'Inicializando...',
      'Carregando configurações...',
      'Validando certificados...',
      'Finalizando...',
    ];
    let msgIndex = 0;

    const updateMessage = () => {
      text.textContent = messages[Math.floor((msgIndex++) / 3) % messages.length];
    };

    updateMessage();
    const msgInterval = setInterval(updateMessage, 400);

    // Aguarda backend estar pronto
    let ready = false;
    while (!ready) {
      try {
        await API.get('/health');
        ready = true;
      } catch (e) {
        await new Promise(r => setTimeout(r, 500));
      }
    }

    clearInterval(msgInterval);

    // Anima saída
    splash.classList.add('exit');
    await new Promise(r => setTimeout(r, 400));
    splash.style.display = 'none';

    // Mostra app
    document.getElementById('app').style.display = 'flex';

    ToastManager.show('Tudo pronto!', 'success', 2000);
  }
}
