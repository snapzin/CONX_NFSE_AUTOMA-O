/**
 * toasts.js - Sistema de notificações (toasts)
 */
class ToastManager {
  static show(message, kind = 'info', duration = 3000) {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${kind}`;
    toast.innerHTML = `
      <div class="toast-content">
        <span class="toast-icon">${ToastManager.getIcon(kind)}</span>
        <span class="toast-message">${message}</span>
      </div>
    `;

    container.appendChild(toast);

    setTimeout(() => {
      toast.classList.add('exit');
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }

  static getIcon(kind) {
    const icons = {
      'info': 'ℹ',
      'success': '✓',
      'warning': '⚠',
      'error': '✕',
    };
    return icons[kind] || icons.info;
  }
}
