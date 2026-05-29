const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  apiCall: (method, endpoint, body = null) =>
    ipcRenderer.invoke('api-call', method, endpoint, body),
  selectFolder: () =>
    ipcRenderer.invoke('select-folder'),
});
