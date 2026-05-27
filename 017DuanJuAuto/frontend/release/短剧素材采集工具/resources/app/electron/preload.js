const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('native', {
  pickDirectory: (options) => ipcRenderer.invoke('dialog:pick-directory', options || {}),
  openFolder: (folderPath) => ipcRenderer.invoke('dialog:open-folder', folderPath),
  pickFile: (options) => ipcRenderer.invoke('dialog:pick-file', options || {}),
})
