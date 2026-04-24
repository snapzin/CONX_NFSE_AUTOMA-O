const { contextBridge, ipcRenderer } = require('electron');

// Expõe um API restrito ao renderer
contextBridge.exposeInMainWorld('electronAPI', {
  apiCall: (method, endpoint, body = null) =>
    ipcRenderer.invoke('api-call', method, endpoint, body),
});
