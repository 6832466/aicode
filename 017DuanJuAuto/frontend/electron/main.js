const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron')
const path = require('path')
const fs = require('fs')
const { spawn, exec } = require('child_process')
const http = require('http')

let backendProcess = null

// ── 端口释放 ──

function killPort(port) {
  return new Promise((resolve) => {
    const cmd = process.platform === 'win32'
      ? `netstat -ano | findstr :${port}`
      : `lsof -ti:${port}`
    exec(cmd, (err, stdout) => {
      if (err || !stdout) return resolve()
      const lines = stdout.trim().split(/\r?\n/)
      for (const line of lines) {
        const pid = line.trim().split(/\s+/).pop()
        if (pid && /^\d+$/.test(pid)) {
          const kill = process.platform === 'win32'
            ? `taskkill /PID ${pid} /F`
            : `kill -9 ${pid}`
          exec(kill, () => {})
        }
      }
      setTimeout(resolve, 500)
    })
  })
}

// ── 残留文件清理 ──

function cleanupResidualFiles() {
  const backendDir = path.join(__dirname, '..', '..', 'backend')
  const configDir = path.join(backendDir, 'config')
  const patterns = ['.hongguo_', '.webengine_profile']
  for (const dir of [backendDir, configDir]) {
    try {
      const entries = fs.readdirSync(dir)
      for (const entry of entries) {
        if (patterns.some(p => entry.startsWith(p))) {
          const full = path.join(dir, entry)
          fs.rmSync(full, { recursive: true, force: true })
        }
      }
    } catch (_) { /* ignore */ }
  }
}

function findPython() {
  const candidates = [
    path.join(__dirname, '..', '..', 'eaglepy310', 'python.exe'),
    path.join(__dirname, '..', '..', '..', 'eaglepy310', 'python.exe'),
    'python',
    'python3',
  ]
  for (const p of candidates) {
    try {
      if (p === 'python' || p === 'python3') {
        const r = require('child_process').spawnSync(p, ['--version'])
        if (r.status === 0) return p
      } else if (fs.existsSync(p)) {
        return p
      }
    } catch (_) { /* continue */ }
  }
  return 'python'
}

function startBackend() {
  const port = 8200
  const backendExe = path.join(process.resourcesPath, 'backend', 'backend.exe')
  const useExe = fs.existsSync(backendExe)

  let cmd, backendArgs, cwd

  if (useExe) {
    cmd = backendExe
    backendArgs = [String(port)]
    cwd = path.join(process.resourcesPath, 'backend')
  } else {
    const pythonExe = findPython()
    const backendDir = path.join(__dirname, '..', '..', 'backend')
    cmd = pythonExe
    backendArgs = ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(port), '--log-level', 'warning']
    cwd = backendDir
  }

  console.log('启动后端:', cmd, backendArgs.join(' '))

  // 释放端口后启动
  killPort(port).then(() => {
    const spawnEnv = { ...process.env }
    const browsersPath = path.join(process.resourcesPath, 'playwright-browsers')
    if (fs.existsSync(browsersPath)) {
      spawnEnv.PLAYWRIGHT_BROWSERS_PATH = browsersPath
    }

    backendProcess = spawn(cmd, backendArgs, {
      cwd: cwd,
      stdio: ['ignore', 'pipe', 'pipe'],
      env: spawnEnv,
    })

    backendProcess.stdout.on('data', data => {
      console.log(`[后端] ${data.toString('utf-8')}`)
    })

    backendProcess.stderr.on('data', data => {
      console.error(`[后端错误] ${data.toString('utf-8')}`)
    })

    backendProcess.on('exit', (code, signal) => {
      console.log(`后端退出，code=${code}, signal=${signal}`)
    })
  })
}

function waitForBackendReady(retries = 60, delay = 500) {
  return new Promise((resolve, reject) => {
    let attempts = 0
    const check = () => {
      const req = http.get('http://127.0.0.1:8200/', res => {
        res.destroy()
        resolve(true)
      }).on('error', () => {
        if (++attempts >= retries) reject(new Error('Backend not ready'))
        else setTimeout(check, delay)
      })
    }
    check()
  })
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1629,
    height: 1011,
    minWidth: 1629,
    minHeight: 1011,
    backgroundColor: '#0A0804',
    titleBarStyle: 'hiddenInset',
    backgroundMaterial: 'mica',
    show: false,
    icon: path.join(__dirname, '..', 'resource', 'icon', 'app.ico'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
    autoHideMenuBar: true,
  })

  win.once('ready-to-show', () => {
    win.show()
  })

  const isDev = !app.isPackaged
  if (isDev) {
    win.loadURL('http://localhost:5173')
  } else {
    win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))
  }
}

app.whenReady().then(async () => {
  startBackend()
  try {
    await waitForBackendReady()
    createWindow()
  } catch (err) {
    console.error('后端启动失败:', err)
    const errorWin = new BrowserWindow({ width: 600, height: 300 })
    errorWin.loadURL(`data:text/html;charset=utf-8,
<!DOCTYPE html>
<html>
  <head><meta charset="UTF-8"></head>
  <body>
    <h2 style="font-family:sans-serif">后端启动失败</h2>
    <p>请检查后端程序并重启应用</p>
  </body>
</html>`)
  }
})

function killBackend() {
  if (!backendProcess || !backendProcess.pid) return
  const pid = backendProcess.pid
  if (process.platform === 'win32') {
    exec(`taskkill /PID ${pid} /T /F`, (err) => {
      if (err) console.warn('taskkill 失败：', err.message)
    })
  } else {
    try {
      process.kill(pid, 'SIGTERM')
      setTimeout(() => {
        try { process.kill(-pid, 'SIGKILL') } catch { }
        try { process.kill(pid, 'SIGKILL') } catch { }
      }, 800)
    } catch { }
  }
}

function shutdown() {
  killBackend()
  cleanupResidualFiles()
}
app.on('before-quit', shutdown)
app.on('will-quit', shutdown)
app.on('quit', shutdown)

app.on('window-all-closed', () => {
  shutdown()
  if (process.platform !== 'darwin') app.quit()
})

process.on('SIGINT', shutdown)
process.on('SIGTERM', shutdown)
process.on('exit', shutdown)

// ── IPC Handlers ──

ipcMain.handle('dialog:pick-directory', async (event, options) => {
  const { title } = options || {}
  const result = await dialog.showOpenDialog({
    title: title || '选择目录',
    properties: ['openDirectory', 'createDirectory']
  })
  if (result.canceled || !result.filePaths || !result.filePaths.length) return null
  return result.filePaths[0]
})

ipcMain.handle('dialog:open-folder', async (event, folderPath) => {
  if (!folderPath) return
  try {
    await shell.openPath(folderPath)
    return true
  } catch (e) {
    console.error('打开文件夹失败', e)
    return false
  }
})

ipcMain.handle('dialog:pick-file', async (event, options) => {
  const { title, filters } = options || {}
  const result = await dialog.showOpenDialog({
    title: title || '选择文件',
    properties: ['openFile'],
    filters: filters || [{ name: '所有文件', extensions: ['*'] }]
  })
  if (result.canceled || !result.filePaths || !result.filePaths.length) return null
  return result.filePaths[0]
})
