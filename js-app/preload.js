const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("nfseApi", {
  getConfig: () => ipcRenderer.invoke("app:get-config"),
  saveConfig: (values) => ipcRenderer.invoke("config:save", values),
  countCertificates: () => ipcRenderer.invoke("certs:count"),
  pickPath: (kind) => ipcRenderer.invoke("dialog:pick-path", kind),
  openPath: (targetPath) => ipcRenderer.invoke("path:open", targetPath),
  startRun: (payload) => ipcRenderer.invoke("run:start", payload),
  cancelRun: () => ipcRenderer.invoke("run:cancel"),
  onRunEvent: (handler) => {
    const listener = (_event, payload) => handler(payload);
    ipcRenderer.on("run:event", listener);
    return () => ipcRenderer.removeListener("run:event", listener);
  },
});
