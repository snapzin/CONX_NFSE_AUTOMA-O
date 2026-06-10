const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  apiCall: (method, endpoint, body = null) =>
    ipcRenderer.invoke('api-call', method, endpoint, body),
  licenseStatus: () =>
    ipcRenderer.invoke('license-status'),
  licenseActivate: (key) =>
    ipcRenderer.invoke('license-activate', key),
  licenseDeactivate: () =>
    ipcRenderer.invoke('license-deactivate'),
  selectFolder: () =>
    ipcRenderer.invoke('select-folder'),
});
