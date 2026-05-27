const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('native', {
  pickDirectory: (options) => ipcRenderer.invoke('dialog:pick-directory', options || {}),
  openFolder: (folderPath) => ipcRenderer.invoke('dialog:open-folder', folderPath),
  pickFile: (options) => ipcRenderer.invoke('dialog:pick-file', options || {}),
  minimize: () => ipcRenderer.invoke('window:minimize'),
  maximize: () => ipcRenderer.invoke('window:maximize'),
  close: () => ipcRenderer.invoke('window:close'),
  isMaximized: () => ipcRenderer.invoke('window:isMaximized'),
  onMaximizeChange: (cb) => {
    ipcRenderer.on('window:maximizeChange', (_e, val) => cb(val))
  },
})
