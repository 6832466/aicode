import { app, BrowserWindow, ipcMain, dialog } from 'electron'
import { autoUpdater } from 'electron-updater'
import { join } from 'path'
import { readFileSync, writeFileSync, existsSync, mkdirSync, readdirSync, unlinkSync, rmdirSync } from 'fs'
import { execSync } from 'child_process'
import { homedir } from 'os'
import { electronApp, optimizer, is } from '@electron-toolkit/utils'
import {
  loadAccounts, saveAccounts, createAccount, deleteAccount,
  updateAccount, updateAccountLoginInfo, getAccountById, getDataDir
} from './accounts'
import {
  loadSubmissions, addSubmission, updateSubmission, deleteSubmission, getSubmission
} from './submissions'

// 单实例锁：只允许运行一个客户端
const gotLock = app.requestSingleInstanceLock()
if (!gotLock) {
  app.quit()
  process.exit(0)
}
app.on('second-instance', () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.focus()
  }
})

let mainWindow: BrowserWindow | null = null
const openBrowserContexts: Set<any> = new Set()       // 所有打开的 Playwright 上下文（用于退出清理）
const accountBrowserMap = new Map<string, any>()      // 每账号一个浏览器，防重复创建

function sendLog(level: string, message: string) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('log:push', {
      time: new Date().toLocaleTimeString(),
      level,
      message
    })
  }
}

// ===== CloakBrowser 启动（替代 Playwright chromium） =====

// 启动前清理 Chrome 锁文件（仅清理纯锁文件，不碰 Cookie/数据）
function cleanupChromeProfile(profileDir: string): void {
  try {
    for (const name of ['SingletonLock', 'SingletonSocket', 'lockfile']) {
      const p = join(profileDir, name)
      if (existsSync(p)) {
        unlinkSync(p)
        console.log(`[cleanup] 删除锁文件 ${name}`)
      }
    }
  } catch {}
}

// 强制终止所有使用指定 profile 的 Chrome/CloakBrowser 进程
function killChromeProcessesForProfile(profileDir: string): void {
  try {
    const escaped = profileDir.replace(/'/g, "''")
    const cmd = `wmic process where "name='chrome.exe' and commandline like '%${escaped}%'" get ProcessId /format:csv`
    const output = execSync(cmd, { encoding: 'utf8', timeout: 8000, stdio: ['ignore', 'pipe', 'ignore'] })
    const pids = output.split(/\r?\n/).filter(line => /^\d+$/.test(line.trim()))
    for (const pid of pids) {
      try {
        execSync(`taskkill /F /PID ${pid.trim()}`, { timeout: 3000, stdio: 'ignore' })
      } catch {}
    }
  } catch {}
}

// 安全关闭某个账户的浏览器，确保 Chrome 进程退出后再继续
async function closeBrowserForAccount(accountId: string): Promise<void> {
  const account = getAccountById(accountId)
  const ctx = accountBrowserMap.get(accountId)
  if (ctx) {
    try {
      await ctx.close()
    } catch {
      console.log(`[closeBrowser] context.close() 失败，将强制结束进程`)
    }
    accountBrowserMap.delete(accountId)
    openBrowserContexts.delete(ctx)
  }
  // 确保所有关联的 Chrome 进程已终止
  if (account) {
    try { killChromeProcessesForProfile(account.userDataDir) } catch {}
    cleanupChromeProfile(account.userDataDir)
    await new Promise(r => setTimeout(r, 1500))
  }
}

// 打开或复用浏览器（同一账号不会重复创建）
async function openOrFocusBrowser(account: any): Promise<{ page: any; isNew: boolean }> {
  const existing = accountBrowserMap.get(account.id)
  if (existing) {
    try {
      const pages = existing.pages()
      if (pages.length > 0) {
        await pages[0].evaluate(() => window.focus())
        return { page: pages[0], isNew: false }
      }
    } catch {}
    // 有 context 但无页面 → Chrome 后台进程残留，关闭后再新建
    await closeBrowserForAccount(account.id)
  } else {
    // 无 context → 仍可能有游离 Chrome 进程，杀之
    try { killChromeProcessesForProfile(account.userDataDir) } catch {}
    cleanupChromeProfile(account.userDataDir)
  }
  // 没有或已关闭 → 创建新的
  const { launchPersistentContext } = await import('cloakbrowser')
  sendLog('info', `🖥️ 正在启动 CloakBrowser [${account.name}]...`)
  sendLog('info', `  用户数据目录: ${account.userDataDir}`)
  sendLog('info', `  Binary 路径: ${process.env.CLOAKBROWSER_BINARY_PATH}`)
  let context: any
  // 启动 CloakBrowser，失败时清理锁文件重试一次
  for (let attempt = 1; attempt <= 2; attempt++) {
    try {
      context = await launchPersistentContext({
        userDataDir: account.userDataDir,
        headless: false,
        stealthArgs: false,
        viewport: null,
        launchOptions: { ignoreDefaultArgs: ['--enable-automation', '--enable-unsafe-swiftshader'] },
      })
      break // 成功则跳出
    } catch (launchErr: any) {
      if (attempt === 1) {
        sendLog('warn', `⚠️ CloakBrowser 启动失败(第1次)，清理锁文件后重试...`)
        cleanupChromeProfile(account.userDataDir)
        continue
      }
      sendLog('error', `❌ CloakBrowser 启动失败(已重试): ${launchErr.message}`)
      if (launchErr.stack) sendLog('error', `  堆栈: ${launchErr.stack.slice(0, 500)}`)
      throw launchErr
    }
  }
  sendLog('success', `✅ CloakBrowser 启动成功 [${account.name}]`)
  openBrowserContexts.add(context)
  accountBrowserMap.set(account.id, context)
  context.on('close', () => {
    openBrowserContexts.delete(context)
    accountBrowserMap.delete(account.id)
  })
  const page = context.pages()[0] || await context.newPage()
  return { page, isNew: true }
}

// 浏览器页面注入提醒浮层（玻璃透明效果，居中大字，5秒自动消失）
async function injectLoginReminder(page: any) {
  await page.waitForTimeout(2000) // 等页面加载
  try {
    await page.evaluate(() => {
      // 遮罩层 + 倒计时
      const overlay = document.createElement('div')
      overlay.id = '__seedance_reminder__'
      overlay.innerHTML = `
        <div style="
          position: fixed; top: 0; left: 0; width: 100%; height: 100%;
          display: flex; align-items: center; justify-content: center;
          z-index: 99999; pointer-events: none;
        ">
          <div id="__seedance_card__" style="
            position: relative;
            background: rgba(30, 30, 30, 0.75);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 16px;
            padding: 32px 48px;
            color: #fff;
            font-size: 22px;
            font-weight: 600;
            text-align: center;
            line-height: 1.6;
            letter-spacing: 1px;
            box-shadow: 0 8px 40px rgba(0, 0, 0, 0.4);
            animation: seedanceFadeIn 0.5s ease;
          ">
            <span id="__seedance_countdown__" style="
              position: absolute; top: 10px; right: 14px;
              font-size: 14px; font-weight: 400; color: rgba(255,255,255,0.5);
            ">5s</span>
            🔐 乐乐登录提醒<br>
            <span style="font-size: 24px; font-weight: 700; color: #f44336; margin-top: 12px; display: block;">
              登录完成后请关闭浏览器<br>再回到软件中点击「刷新」更新状态
            </span>
          </div>
        </div>
        <style>
          @keyframes seedanceFadeIn { from { opacity: 0; transform: scale(0.9); } to { opacity: 1; transform: scale(1); } }
        </style>
      `
      document.body.appendChild(overlay)
      // 倒计时
      let sec = 5
      const countdownEl = document.getElementById('__seedance_countdown__')
      const timer = setInterval(() => {
        sec--
        if (countdownEl) countdownEl.textContent = sec + 's'
        if (sec <= 0) {
          clearInterval(timer)
          const el = document.getElementById('__seedance_reminder__')
          if (el) {
            el.style.transition = 'opacity 0.8s ease'
            el.style.opacity = '0'
            setTimeout(() => el.remove(), 800)
          }
        }
      }, 1000)
    })
  } catch {}
}

// 共享：检测豆包页面登录状态和剩余额度
async function checkLoginState(page: any, accountName: string, accountId?: string): Promise<{ loggedIn: boolean; remaining: number }> {
  // 方式1：从浏览器 Cookie 中检测豆包 session（最可靠）
  let loggedIn = false
  try {
    const cookies = await page.context().cookies()
    const hasSession = cookies.some(c =>
      c.name.toLowerCase().includes('session') && !!c.value ||
      c.name === 'samantha_session' ||
      c.name === 'sessionid'
    )
    if (hasSession) {
      loggedIn = true
      sendLog('info', `[${accountName}] Cookie 有效 (${cookies.filter(c => c.name.toLowerCase().includes('session') || c.name === 'samantha_session' || c.name === 'sessionid').length} 个 session cookie)`)
    }
  } catch {}

  // 方式2：检测页面上是否有可见的"登录"按钮（兜底）
  if (!loggedIn) {
    try {
      const loginBtn = page.locator('text="登录"').first()
      await loginBtn.waitFor({ state: 'visible', timeout: 3000 })
      loggedIn = false
    } catch {
      loggedIn = true
    }
  }

  let remaining = -1
  if (loggedIn) {
    try {
      const quotaText = await page.evaluate(() => {
        const t = (document.body as HTMLElement).innerText || ''
        const m = t.match(/今日剩余\s*(\d+)\s*个(视频生成额度|视频额度|额度)/)
        return m ? parseInt(m[1], 10) : null
      })
      remaining = quotaText ?? -1
      if (remaining >= 0) sendLog('info', `[${accountName}] 剩余额度: ${remaining}`)
    } catch {}
  }

  // 没从页面取到新值：
  //   - 今天已查过 → 保留原值（当天从页面获取的真实额度）
  //   - 未查过（新的一天）→ 写 10（默认初始额度，否则没法提交）
  if (remaining < 0) {
    if (accountId) {
      const existing = getAccountById(accountId)
      if (existing && existing.quotaRemaining >= 0 && existing.lastQuotaCheck) {
        const lastDate = new Date(existing.lastQuotaCheck).toDateString()
        const today = new Date().toDateString()
        remaining = lastDate === today ? existing.quotaRemaining : 10
      } else {
        remaining = 10
      }
    } else {
      remaining = 10
    }
  }

  return { loggedIn, remaining }
}

function createWindow(): void {
  // 从配置文件读取上次保存的窗口尺寸
  const configPath = join(getDataDir(), 'config.json')
  let savedWidth = 1252, savedHeight = 720
  try {
    if (existsSync(configPath)) {
      const cfg = JSON.parse(readFileSync(configPath, 'utf-8'))
      if (cfg.winWidth) savedWidth = cfg.winWidth
      if (cfg.winHeight) savedHeight = cfg.winHeight
    }
  } catch {}

  mainWindow = new BrowserWindow({
    title: '豆包Seedance批量生视频工具         微信：rpalele',
    icon: join(__dirname, '../../build/icon.ico'),
    width: savedWidth,
    height: savedHeight,
    minWidth: 900,
    minHeight: 600,
    show: false,
    autoHideMenuBar: true,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: false,
    },
  })

  // 窗口大小变化时保存到配置文件
  mainWindow.on('resize', () => {
    if (!mainWindow) return
    const [w, h] = mainWindow.getSize()
    try {
      let cfg: any = {}
      if (existsSync(configPath)) cfg = JSON.parse(readFileSync(configPath, 'utf-8'))
      cfg.winWidth = w
      cfg.winHeight = h
      writeFileSync(configPath, JSON.stringify(cfg, null, 2))
    } catch (e: any) { sendLog('warn', `保存窗口尺寸失败: ${e.message}`) }
  })

  // 强制设置窗口标题
  const WIN_TITLE = '豆包Seedance批量生视频工具         微信：rpalele'
  mainWindow.setTitle(WIN_TITLE)
  mainWindow.on('page-title-updated', (e) => e.preventDefault())
  mainWindow.on('ready-to-show', () => { mainWindow!.setTitle(WIN_TITLE); mainWindow!.show() })
  setTimeout(() => { if (mainWindow && !mainWindow.isVisible()) mainWindow!.show() }, 5000)
  mainWindow.on('closed', () => { mainWindow = null })

  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

// ===== IPC: 配置 =====
ipcMain.handle('config:get', () => {
  const configPath = join(getDataDir(), 'config.json')
  const desktopDir = join(app.getPath('home'), 'Desktop')
  try {
    if (existsSync(configPath)) {
      const config = JSON.parse(readFileSync(configPath, 'utf-8'))
      // 跨机器拷贝后旧路径可能不存在，或路径为空，自动回退到桌面
      if (!config.downloadDir || !existsSync(config.downloadDir)) {
        config.downloadDir = desktopDir
        writeFileSync(configPath, JSON.stringify(config, null, 2))
      }
      return config
    }
  } catch (e: any) {
    sendLog('error', `读取配置失败: ${e.message}`)
  }
  return { downloadDir: desktopDir, headless: false }
})

ipcMain.handle('config:set-download-dir', (_event, dir: string) => {
  const configPath = join(getDataDir(), 'config.json')
  let config: any = {}
  try { if (existsSync(configPath)) config = JSON.parse(readFileSync(configPath, 'utf-8')) } catch {}
  config.downloadDir = dir
  writeFileSync(configPath, JSON.stringify(config, null, 2))
  return dir
})

ipcMain.handle('config:set', (_event, key: string, value: any) => {
  const configPath = join(getDataDir(), 'config.json')
  let config: any = {}
  try { if (existsSync(configPath)) config = JSON.parse(readFileSync(configPath, 'utf-8')) } catch {}
  config[key] = value
  writeFileSync(configPath, JSON.stringify(config, null, 2))
  return true
})

ipcMain.handle('dialog:select-directory', async () => {
  if (!mainWindow) return ''
  const result = await dialog.showOpenDialog(mainWindow, { properties: ['openDirectory'] })
  return result.canceled ? '' : result.filePaths[0]
})

ipcMain.handle('file:read-data-url', async (_event, filePath: string) => {
  try {
    const { readFileSync } = await import('fs')
    const buffer = readFileSync(filePath)
    const ext = filePath.split('.').pop()?.toLowerCase() || 'png'
    const mime = { jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', webp: 'image/webp', bmp: 'image/bmp', gif: 'image/gif' }[ext] || 'image/png'
    return 'data:' + mime + ';base64,' + buffer.toString('base64')
  } catch {
    return ''
  }
})

ipcMain.handle('dialog:select-images', async () => {
  if (!mainWindow) return []
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile', 'multiSelections'],
    filters: [{ name: '图片', extensions: ['png', 'jpg', 'jpeg', 'webp', 'bmp'] }],
  })
  return result.canceled ? [] : result.filePaths
})

// ===== IPC: 账户管理 =====
ipcMain.handle('accounts:list', async () => {
  return loadAccounts()
})

ipcMain.handle('accounts:create', async (_event, name: string) => {
  const existing = loadAccounts().find(a => a.name === name)
  if (existing) {
    sendLog('warn', `账户名称 [${name}] 已存在，请使用其他名称`)
    return loadAccounts()
  }
  const acct = createAccount(name)
  sendLog('success', `账户 [${name}] 已创建`)
  return loadAccounts()
})

ipcMain.handle('accounts:delete', async (_event, id: string) => {
  const acct = getAccountById(id)
  deleteAccount(id)
  sendLog('info', `账户 [${acct?.name || id}] 已删除`)
  return loadAccounts()
})

ipcMain.handle('accounts:rename', async (_event, id: string, newName: string, currentName?: string) => {
  const trimmed = newName.trim()
  if (!trimmed) return { success: false, error: '名称不能为空' }
  const all = loadAccounts()
  if (all.some(a => a.id !== id && a.name === trimmed)) {
    return { success: false, error: `名称 [${trimmed}] 已存在` }
  }
  let acct = all.find(a => a.id === id) || (currentName ? all.find(a => a.name === currentName) : null)
  if (!acct) return { success: false, error: '账户不存在' }
  updateAccount(acct.id, { name: trimmed })
  sendLog('info', `账户 [${acct.name}] 已重命名为 [${trimmed}]`)
  return { success: true }
})

ipcMain.handle('accounts:relogin', async (_event, id: string) => {
  try {
    const account = getAccountById(id)
    if (!account) return { success: false, error: '账户不存在' }

    const { rmSync, existsSync } = await import('fs')
    const paths = [
      join(account.userDataDir, 'Default', 'Cookies'),
      join(account.userDataDir, 'Default', 'Cookies-journal'),
      join(account.userDataDir, 'Default', 'Local Storage'),
      join(account.userDataDir, 'Default', 'Session Storage'),
    ]
    for (const p of paths) {
      try { if (existsSync(p)) rmSync(p, { recursive: true, force: true }) } catch {}
    }

    updateAccountLoginInfo(id, { loginStatus: 'not_logged_in', quotaRemaining: 0 })
    sendLog('info', `[${account.name}] Cookie 已清除, 请重新登录`)

    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('accounts:updated', loadAccounts())
    }

    const { page, isNew } = await openOrFocusBrowser(account)
    if (!isNew) {
      sendLog('info', `[${account.name}] 浏览器已打开，请使用已有窗口登录`)
      return { success: true }
    }
    await page.goto('https://www.doubao.com/chat/', { waitUntil: 'domcontentloaded', timeout: 60000 })
    injectLoginReminder(page)
    sendLog('info', `[${account.name}] 已打开浏览器, 请扫码登录新账号。登录完成后请关闭浏览器窗口`)
    sendLog('warn', `⚠️ 登录完成后请关闭浏览器再操作本软件`)
    return { success: true }
  } catch (err: any) {
    sendLog('error', `重新登录失败: ${err.message}`)
    return { success: false, error: err.message }
  }
})

ipcMain.handle('accounts:open-browser', async (_event, id: string) => {
  try {
    const account = getAccountById(id)
    if (!account) return { success: false, error: '账户不存在' }

    const { page, isNew } = await openOrFocusBrowser(account)
    if (!isNew) {
      sendLog('info', `[${account.name}] 浏览器已打开，请使用已有窗口`)
      return { success: true, userDataDir: account.userDataDir }
    }
    await page.goto('https://www.doubao.com/chat/', { waitUntil: 'domcontentloaded', timeout: 60000 })
    injectLoginReminder(page)

    try {
      await page.evaluate((name: string) => {
        document.title = `[${name}] 豆包 - 登录中...`
      }, account.name)
    } catch {}

    sendLog('info', `已为账户 [${account.name}] 打开独立浏览器窗口。登录完成后请关闭浏览器再操作本软件`)
    return { success: true, userDataDir: account.userDataDir }
  } catch (err: any) {
    sendLog('error', `打开浏览器失败: ${err.message}`)
    return { success: false, error: err.message }
  }
})

ipcMain.handle('accounts:refresh-status', async (_event, id: string) => {
  const account = getAccountById(id)
  if (!account) return { success: false, error: '账户不存在' }

  sendLog('info', `🔍 [${account.name}] 检测 Cookie 有效性...`)

  let context: any = null
  let shouldCloseContext = false

  // 如果已有可见浏览器在用同一账户，直接复用页面检测，不再开 headless
  const existingContext = accountBrowserMap.get(account.id)
  if (existingContext) {
    try {
      const pages = existingContext.pages()
      if (pages.length > 0) {
        const page = pages[0]
        await page.goto('https://www.doubao.com/chat/', { waitUntil: 'domcontentloaded', timeout: 20000 }).catch(() => {})
        await page.waitForTimeout(3000).catch(() => {})

        const { loggedIn, remaining } = await checkLoginState(page, account.name, account.id)
        const updates: any = { loginStatus: loggedIn ? 'logged_in' : 'not_logged_in' }
        if (remaining >= 0) { updates.quotaRemaining = remaining; updates.lastQuotaCheck = new Date().toISOString() }
        updateAccountLoginInfo(id, updates)

        sendLog(loggedIn ? 'success' : 'warn', `[${account.name}] ${loggedIn ? `已登录 ✅ (额度: ${remaining >= 0 ? remaining : '?'})` : '未登录 ❌'}`)
        return { success: true, loggedIn }
      }
    } catch {}
  }

  // 关闭任何残留浏览器进程，防止两个 Chrome 同时操作同一 profile
  await closeBrowserForAccount(account.id)

  // 启动 headless CloakBrowser，带清理重试
  for (let attempt = 1; attempt <= 2; attempt++) {
    try {
      const { launchPersistentContext } = await import('cloakbrowser')
      context = await launchPersistentContext({
        userDataDir: account.userDataDir,
        headless: true,
        viewport: { width: 1280, height: 900 },
      })
      shouldCloseContext = true
      break
    } catch (launchErr: any) {
      if (attempt === 1) {
        sendLog('warn', `⚠️ headless 启动失败(第1次)，清理锁文件后重试...`)
        cleanupChromeProfile(account.userDataDir)
        continue
      }
      sendLog('error', `❌ CloakBrowser headless 启动失败(已重试): ${launchErr.message}`)
      return { success: false, error: launchErr.message }
    }
  }

  try {
    const page = context.pages()[0] || await context.newPage()
    await page.goto('https://www.doubao.com/chat/', { waitUntil: 'domcontentloaded', timeout: 20000 }).catch(() => {})
    await page.waitForTimeout(3000).catch(() => {})

    const { loggedIn, remaining } = await checkLoginState(page, account.name, account.id)
    const updates: any = { loginStatus: loggedIn ? 'logged_in' : 'not_logged_in' }
    if (remaining >= 0) { updates.quotaRemaining = remaining; updates.lastQuotaCheck = new Date().toISOString() }
    updateAccountLoginInfo(id, updates)

    sendLog(loggedIn ? 'success' : 'warn', `[${account.name}] ${loggedIn ? `已登录 ✅ (额度: ${remaining >= 0 ? remaining : '?'})` : '未登录 ❌'}`)
    return { success: true, loggedIn }
  } catch (err: any) {
    sendLog('error', `[${account.name}] 检测失败: ${err.message}`)
    return { success: false, error: err.message }
  } finally {
    if (shouldCloseContext && context) await context.close().catch(() => {})
  }
})

ipcMain.handle('accounts:refresh-all', async () => {
  const accounts = loadAccounts()
  const today = new Date().toDateString()

  sendLog('info', `🔄 开始刷新全部 ${accounts.length} 个账户...`)

  for (const account of accounts) {
    const lastCheckDate = account.lastQuotaCheck ? new Date(account.lastQuotaCheck).toDateString() : ''
    if (lastCheckDate === today && account.loginStatus === 'logged_in') {
      sendLog('info', `[${account.name}] 今天已检测, 跳过`)
      continue
    }

    sendLog('info', `🔍 [${account.name}] 检测 Cookie...`)

    let context: any = null
    let shouldCloseContext = false

    // 已有可见浏览器 → 复用页面检测
    const existingContext = accountBrowserMap.get(account.id)
    if (existingContext) {
      try {
        const pages = existingContext.pages()
        if (pages.length > 0) {
          const page = pages[0]
          await page.goto('https://www.doubao.com/chat/', { waitUntil: 'domcontentloaded', timeout: 20000 }).catch(() => {})
          await page.waitForTimeout(4000).catch(() => {})

          const { loggedIn, remaining } = await checkLoginState(page, account.name, account.id)
          const updates: any = { loginStatus: loggedIn ? 'logged_in' : 'not_logged_in' }
          if (remaining >= 0) { updates.quotaRemaining = remaining; updates.lastQuotaCheck = new Date().toISOString() }
          updateAccountLoginInfo(account.id, updates)

          sendLog(loggedIn ? 'success' : 'warn', `[${account.name}] ${loggedIn ? `已登录 ✅ (额度: ${remaining >= 0 ? remaining : '?'})` : '未登录 ❌'}`)
          await new Promise(r => setTimeout(r, 1500))
          continue
        }
      } catch {}
    }

    // 关闭任何残留浏览器进程
    await closeBrowserForAccount(account.id)

    // 启动 headless CloakBrowser，带清理重试
    for (let attempt = 1; attempt <= 2; attempt++) {
      try {
        const { launchPersistentContext } = await import('cloakbrowser')
        context = await launchPersistentContext({
          userDataDir: account.userDataDir,
          headless: true,
          viewport: { width: 1280, height: 900 },
        })
        shouldCloseContext = true
        break
      } catch (launchErr: any) {
        if (attempt === 1) {
          sendLog('warn', `⚠️ [${account.name}] headless 启动失败(第1次)，清理锁文件后重试...`)
          cleanupChromeProfile(account.userDataDir)
          continue
        }
        sendLog('error', `❌ [${account.name}] headless 启动失败(已重试): ${launchErr.message}`)
        shouldCloseContext = false
        context = null
        break
      }
    }
    if (!context) continue

    try {
      const page = context.pages()[0] || await context.newPage()
      await page.goto('https://www.doubao.com/chat/', { waitUntil: 'domcontentloaded', timeout: 20000 }).catch(() => {})
      await page.waitForTimeout(4000).catch(() => {})

      const { loggedIn, remaining } = await checkLoginState(page, account.name, account.id)
      const updates2: any = { loginStatus: loggedIn ? 'logged_in' : 'not_logged_in' }
      if (remaining >= 0) { updates2.quotaRemaining = remaining; updates2.lastQuotaCheck = new Date().toISOString() }
      updateAccountLoginInfo(account.id, updates2)

      sendLog(loggedIn ? 'success' : 'warn', `[${account.name}] ${loggedIn ? `已登录 ✅ (额度: ${remaining >= 0 ? remaining : '?'})` : '未登录 ❌'}`)
    } catch (err: any) {
      sendLog('error', `[${account.name}] 检测失败: ${err.message}`)
    } finally {
      await new Promise(r => setTimeout(r, 1500))
      if (shouldCloseContext && context) await context.close().catch(() => {})
    }
  }

  sendLog('success', '全部账户刷新完成')
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('accounts:updated', loadAccounts())
  }
  return loadAccounts()
})

// ===== IPC: 提交记录 =====
ipcMain.handle('submissions:list', async () => {
  return loadSubmissions()
})

ipcMain.handle('submissions:create', async (_event, params: any) => {
  const sub = addSubmission({
    images: params.images || [],
    description: params.description || '',
    prefix: params.prefix || '',
    suffix: params.suffix || '',
    ratio: params.ratio || '9:16',
    duration: params.duration || 10,
    status: 'submitted',
  })
  // 通知渲染器刷新
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('submissions:updated', loadSubmissions())
  }
  return sub
})

ipcMain.handle('submissions:delete', async (_event, id: string) => {
  deleteSubmission(id)
  sendLog('info', '提交记录已删除')
  return loadSubmissions()
})

ipcMain.handle('submissions:clear-all', async () => {
  const subs = loadSubmissions()
  for (const s of subs) {
    deleteSubmission(s.id)
  }
  sendLog('info', `已清空全部 ${subs.length} 条提交记录`)
  return []
})

ipcMain.handle('submissions:update-desc', async (_event, id: string, description: string) => {
  const sub = getSubmission(id)
  if (!sub) return { success: false, error: '记录不存在' }
  updateSubmission(id, { description })
  sendLog('info', `已更新提交记录描述词`)
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('submissions:updated', loadSubmissions())
  }
  return { success: true }
})

// ===== IPC: 自动化 =====
ipcMain.handle('automation:start', async (_event, params: {
  images: string[]
  description: string
  prefix: string
  suffix: string
  ratio: string
  duration: number
  downloadDir: string
  headless: boolean
  submissionId?: string
}) => {
  const { runAutomation } = await import('./automation')
  const accounts = loadAccounts()
  const { writeFileSync, existsSync } = await import('fs')
  const { join } = await import('path')

  const desktopDir = join(app.getPath('home'), 'Desktop')
  const downloadDir = params.downloadDir || desktopDir

  if (!params.description?.trim()) {
    return { success: false, error: '描述词不能为空' }
  }

  // 如果图片路径不是绝对路径，补齐为桌面路径
  params.images = (params.images || []).map(p => {
    if (!p) return p
    if (p.includes(':') || p.startsWith('/')) return p  // 已是绝对路径
    return join(desktopDir, p)  // 补齐桌面路径
  })

  // 更新已有提交记录（渲染器已创建）
  let sub = params.submissionId ? getSubmission(params.submissionId) : null
  if (!sub) {
    sub = addSubmission({ images: params.images || [], description: params.description || '', prefix: params.prefix || '', suffix: params.suffix || '', ratio: params.ratio || '9:16', duration: params.duration || 10, quotaRemaining: -1, error: '' })
  }
  const subId = sub.id
  if (mainWindow) mainWindow.webContents.send('submissions:updated', loadSubmissions())

  const quotaCost = params.duration <= 10 ? 2 : 3
  for (const account of accounts) {
    if (account.loginStatus !== 'logged_in' || account.quotaRemaining < quotaCost) {
      if (account.quotaRemaining > 0 && account.quotaRemaining < quotaCost) {
        sendLog('warn', `[${account.name}] 额度不足: 需要 ${quotaCost}，当前 ${account.quotaRemaining}`)
      }
      continue
    }

    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('automation:status', `🔄 正在使用账户 [${account.name}]...`)
    }

    // 关闭已有的可见浏览器（防止 profile 锁冲突）
    sendLog('info', `[${account.name}] 关闭已有浏览器...`)
    await closeBrowserForAccount(account.id)

    // 标记为"提交中"，让前端区分排队和正在执行
    updateSubmission(sub.id, { status: 'processing', accountId: account.id, accountName: account.name })
    if (mainWindow) mainWindow.webContents.send('submissions:updated', loadSubmissions())

    const result = await runAutomation(
      account.id, account.name, account.userDataDir,
      { ...params, downloadDir },
      (msg: string) => { if (mainWindow) mainWindow.webContents.send('automation:status', msg) }
    )

    // 无论成功/失败/拒绝，只要豆包回复中有额度信息就更新账户
    if (result.quotaRemaining >= 0) {
      updateAccountLoginInfo(account.id, {
        quotaRemaining: result.quotaRemaining,
        lastQuotaCheck: new Date().toISOString()
      })
    }

    if (result.status === 'success') {
      updateSubmission(sub.id, {
        status: 'submitted',
        accountId: account.id,
        accountName: account.name,
        chatId: result.chatId,
        vid: result.vid,
        quotaRemaining: result.quotaRemaining,
        reply: result.botReply || '',
        error: '',
      })
      if (mainWindow) {
        mainWindow.webContents.send('submissions:updated', loadSubmissions())
        mainWindow.webContents.send('accounts:updated', loadAccounts())
      }
      sendLog('success', `✅ [${account.name}] 提交成功! 额度: ${result.quotaRemaining >= 0 ? result.quotaRemaining : '?'}`)
      return { success: true, submissionId: sub.id, accountName: account.name, chatId: result.chatId }
    }

    if (result.status === 'exhausted') {
      updateSubmission(sub.id, { status: 'failed', error: '额度耗尽', quotaRemaining: 0, reply: result.botReply || '' })
      if (mainWindow) { mainWindow.webContents.send('accounts:updated', loadAccounts()); mainWindow.webContents.send('submissions:updated', loadSubmissions()) }
      continue
    }

    updateSubmission(sub.id, { error: result.error, status: 'failed', quotaRemaining: 0, reply: result.botReply || '' })
    if (mainWindow) {
      mainWindow.webContents.send('accounts:updated', loadAccounts())
      mainWindow.webContents.send('submissions:updated', loadSubmissions())
    }
  }

  // 全部失败
  try {
    const d = new Date()
    const dateStr = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
    const failPath = join(downloadDir, `失败记录_${dateStr}.txt`)
    writeFileSync(failPath, `[${new Date().toLocaleTimeString()}] ${params.description || ''}\n`, { flag: 'a', encoding: 'utf-8' })
    updateSubmission(sub.id, { status: 'failed', error: 'all_failed' })
    if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('submissions:updated', loadSubmissions())
    return { success: false, error: 'all_failed', failPath }
  } catch (e: any) {
    sendLog('error', `写入失败记录出错: ${e.message}`)
    updateSubmission(sub.id, { status: 'failed', error: 'all_failed' })
    if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('submissions:updated', loadSubmissions())
    return { success: false, error: 'all_failed' }
  }
})

// ===== IPC: 批量下载 =====
ipcMain.handle('submissions:download-batch', async (_event, ids: string[]) => {
  const submissions = loadSubmissions()
  const toDownload = submissions.filter(s => ids.includes(s.id))

  if (toDownload.length === 0) {
    sendLog('warn', '没有可下载的记录')
    return { success: false, error: '没有可下载的记录' }
  }

  sendLog('info', `开始下载 ${toDownload.length} 条记录...`)

  // 异步处理，逐条推送进度
  ;(async () => {
    try {
    let downloaded = 0
    const total = toDownload.length

    for (const sub of toDownload) {
      sendLog('info', `[${sub.accountName || '未知账户'}] 处理中... (${downloaded + 1}/${total})`)

      // 跳过未就绪的记录
      if (sub.status === 'processing') {
        sendLog('warn', `⏭️ [${sub.accountName}] 跳过: 视频仍在生成中`)
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.webContents.send('submissions:download-progress', { id: sub.id, status: 'failed', accountName: sub.accountName, error: '视频未完成' })
        }
        continue
      }
      if (sub.status === 'failed') {
        sendLog('warn', `⏭️ [${sub.accountName}] 跳过: 该记录已失败`)
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.webContents.send('submissions:download-progress', { id: sub.id, status: 'failed', accountName: sub.accountName, error: '视频生成失败' })
        }
        continue
      }

      // 检查文件是否已存在
      if (sub.downloadPath && existsSync(sub.downloadPath)) {
        try {
          const stat = (await import('fs')).statSync(sub.downloadPath)
          if (stat.size > 0) {
            updateSubmission(sub.id, { status: 'downloaded' })
            sendLog('success', `⏭️ [${sub.accountName}] 跳过: 文件已存在`)
            downloaded++
            if (mainWindow && !mainWindow.isDestroyed()) {
              mainWindow.webContents.send('submissions:download-progress', { id: sub.id, status: 'downloaded', accountName: sub.accountName })
            }
            continue
          }
        } catch {}
      }

      const account = getAccountById(sub.accountId)
      if (!account) {
        sendLog('warn', `⏭️ [${sub.id}] 跳过: 关联账户不存在`)
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.webContents.send('submissions:download-progress', { id: sub.id, status: 'failed', accountName: sub.accountName || sub.id, error: '关联账户不存在' })
        }
        continue
      }

      if (!sub.chatId) {
        sendLog('warn', `⏭️ [${sub.accountName || sub.id}] 跳过: 缺少 chatId（未成功提交到豆包）`)
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.webContents.send('submissions:download-progress', { id: sub.id, status: 'failed', accountName: sub.accountName || sub.id, error: '缺少 chatId' })
        }
        continue
      }

      try {
        let downloadCtx: any = null
        let shouldCloseCtx = false
        let page: any = null

        // 如果账户已有可见浏览器，复用其 context 开新页面下载
        const existingCtx = accountBrowserMap.get(account.id)
        if (existingCtx) {
          try {
            const pages = existingCtx.pages()
            if (pages.length > 0) {
              page = await existingCtx.newPage()
              sendLog('info', `📥 复用现有浏览器下载 [${account.name}]`)
            } else {
              // 有 context 无页面，关闭残留进程后再启动 headless
              await closeBrowserForAccount(account.id)
            }
          } catch {
            await closeBrowserForAccount(account.id)
          }
        }

        if (!page) {
          // 即使没有 context 记录，也可能有游离 Chrome 进程
          try { killChromeProcessesForProfile(account.userDataDir) } catch {}
          cleanupChromeProfile(account.userDataDir)
          await new Promise(r => setTimeout(r, 1000))
          try {
            const { launchPersistentContext } = await import('cloakbrowser')
            downloadCtx = await launchPersistentContext({
              userDataDir: account.userDataDir,
              headless: true,
              stealthArgs: true,
              viewport: { width: 1280, height: 900 },
            })
            shouldCloseCtx = true
            page = downloadCtx.pages()[0] || await downloadCtx.newPage()
            sendLog('info', `📥 启动 headless 下载 [${account.name}]`)
          } catch (headlessErr: any) {
            sendLog('error', `[${sub.accountName}] headless 启动失败: ${headlessErr.message}`)
            if (mainWindow && !mainWindow.isDestroyed()) {
              mainWindow.webContents.send('submissions:download-progress', { id: sub.id, status: 'failed', accountName: sub.accountName, error: headlessErr.message })
            }
            continue
          }
        }

        try {
          await page.goto(`https://www.doubao.com/chat/${sub.chatId}`, { waitUntil: 'domcontentloaded', timeout: 60000 })
          await page.waitForTimeout(5000).catch(() => {})

          // 优先使用已存储的 vid，否则从页面提取
          let vid = sub.vid || ''
          if (!vid) {
            for (let attempt = 0; attempt < 12; attempt++) {
              await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
              await page.waitForTimeout(3000).catch(() => {})
              const vids: string[] = await page.evaluate(() => {
                const found: string[] = []
                const html = document.documentElement.innerHTML
                const patterns = [
                  /"vid"\s*:\s*"(v\d[a-z0-9]{10,50})"/g,
                  /&quot;vid&quot;\s*:&quot;(v\d[a-z0-9]{10,50})&quot/g,
                  /vid%22%3A%22(v\d[a-z0-9]{10,50})/g,
                  /data-vid\s*=\s*["'](v\d[a-z0-9]{10,50})["']/g,
                  /\/video\/(v\d[a-z0-9]{10,50})/g,
                ]
                for (const p of patterns) {
                  let m
                  while ((m = p.exec(html)) !== null) {
                    if (m[1] && !found.includes(m[1])) found.push(m[1])
                  }
                }
                if (found.length === 0) {
                  const loose = /v\d[a-z0-9]{15,60}/gi
                  let lm
                  while ((lm = loose.exec(html)) !== null) {
                    if (!found.includes(lm[0])) found.push(lm[0])
                  }
                }
                return found
              })
              if (vids.length > 0) { vid = vids[0]; break }
              sendLog('info', `  [${sub.accountName}] 等待视频... (${attempt + 1}/12)`)
            }
          }

          if (!vid) {
            sendLog('warn', `⏭️ [${sub.accountName}] 跳过: 未找到 vid（视频可能仍在生成）`)
            if (mainWindow && !mainWindow.isDestroyed()) {
              mainWindow.webContents.send('submissions:download-progress', { id: sub.id, status: 'failed', accountName: sub.accountName, error: '视频尚未生成完成' })
            }
            continue
          }

          // 获取无水印链接（重试 3 次，防网络波动）
          let info: { url: string; width: number; height: number; definition: string } | null = null
          for (let retry = 0; retry < 3; retry++) {
            info = await page.evaluate(async (v: string) => {
              const params = new URLSearchParams({
                version_code: '20800', language: 'zh-CN', device_platform: 'web',
                aid: '497858', real_aid: '497858', pkg_type: 'release_version',
                device_id: '', pc_version: '2.51.7', region: '', sys_region: '',
                samantha_web: '1', 'use-olympus-account': '1', web_tab_id: '',
              })
              const resp = await fetch(`https://www.doubao.com/samantha/media/get_play_info?${params}`, {
                method: 'POST', credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key: v }),
              })
              const data = await resp.json()
              const mu = data?.data?.original_media_info?.main_url
              if (!mu) return null
              const meta = data.data.original_media_info.meta || {}
              return { url: mu, width: meta.width || 0, height: meta.height || 0, definition: meta.definition || '' }
            }, vid)
            if (info) break
            if (retry < 2) {
              sendLog('info', `  [${sub.accountName}] 获取链接失败，重试... (${retry + 1}/3)`)
              await new Promise(r => setTimeout(r, 3000))
            }
          }

          if (!info) {
            sendLog('warn', `⏭️ [${sub.accountName}] 跳过: 视频可能还在生成中，请稍后再试`)
            if (mainWindow && !mainWindow.isDestroyed()) {
              mainWindow.webContents.send('submissions:download-progress', { id: sub.id, status: 'failed', accountName: sub.accountName, error: '视频可能还在生成中，请稍后再试' })
            }
            continue
          }

          // 下载：优先使用已保存路径，其次用配置的目录，最后回退桌面
          let downloadDir = join(app.getPath('home'), 'Desktop')
          if (sub.downloadPath) {
            downloadDir = join(sub.downloadPath, '..')
          } else {
            try {
              const cfgPath = join(getDataDir(), 'config.json')
              if (existsSync(cfgPath)) {
                const cfg = JSON.parse(readFileSync(cfgPath, 'utf-8'))
                if (cfg.downloadDir && existsSync(cfg.downloadDir)) downloadDir = cfg.downloadDir
              }
            } catch {}
          }
          // 文件名格式: 序号-描述词前20字
          const subIdx = sub.seq || (submissions.length - submissions.findIndex(s => s.id === sub.id))
          const descPart = (sub.description || '无描述').replace(/[<>:"/\\|?*\n\r\t]/g, '').slice(0, 20)
          const fname = `${subIdx}-${descPart}.mp4`
          const savePath = join(downloadDir, fname)

          const resp = await fetch(info.url)
          if (!resp.ok) throw new Error(`下载失败: HTTP ${resp.status}`)
          const buffer = Buffer.from(await resp.arrayBuffer())
          const { writeFileSync } = await import('fs')
          writeFileSync(savePath, buffer)

          updateSubmission(sub.id, {
            status: 'downloaded',
            vid,
            downloadPath: savePath,
            definition: info.definition,
            width: info.width,
            height: info.height,
            completedAt: new Date().toISOString(),
          })

          sendLog('success', `[${sub.accountName}] 下载完成 (${(buffer.length / 1024 / 1024).toFixed(1)} MB)`)
          downloaded++
          if (mainWindow && !mainWindow.isDestroyed()) {
            mainWindow.webContents.send('submissions:download-progress', { id: sub.id, status: 'downloaded', accountName: sub.accountName })
          }
        } finally {
          if (shouldCloseCtx && downloadCtx) await downloadCtx.close().catch(() => {})
        }
      } catch (err: any) {
        sendLog('error', `[${sub.accountName}] 下载失败: ${err.message}`)
        updateSubmission(sub.id, { status: 'failed', error: err.message })
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.webContents.send('submissions:download-progress', { id: sub.id, status: 'failed', accountName: sub.accountName, error: err.message })
        }
      }
    }

    // 全部完成，推送最终结果
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('submissions:updated', loadSubmissions())
      mainWindow.webContents.send('submissions:download-complete', { total, downloaded })
    }
    sendLog('success', `下载完成: ${downloaded}/${total}`)
    } catch (e: any) {
      sendLog('error', `下载任务异常终止: ${e.message}`)
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('submissions:download-complete', { total: toDownload.length, downloaded: 0 })
      }
    }
  })()

  return { success: true }  // 立即返回，下载在后台进行，进度通过事件推送
})

// ===== 自动更新（国内可用版 - raw.githubusercontent.com）=====
//
// 方案：直接访问 GitHub 仓库文件的 raw 内容，完全绕过 GitHub API 和 jsDelivr
// raw.githubusercontent.com 在国内相对稳定
//
// 仓库里需要有一个 version.json 文件（放在根目录），格式：
// {
//   "version": "3.0.1",
//   "releaseUrl": "https://github.com/6832466/022DoubaoSeedance/releases/tag/v3.0.1",
//   "portable": {
//     "name": "doubao-seedance-3.0.1-portable.exe",
//     "url": "https://github.com/6832466/022DoubaoSeedance/releases/download/v3.0.1/doubao-seedance-3.0.1-portable.exe",
//     "size": 251658240
//   }
// }
//
// 更新流程：读取 version.json → 对比版本 → 有更新则弹窗 → 用户确认 → 下载 → 安装

const GITHUB_OWNER = '6832466'
const GITHUB_REPO = '022DoubaoSeedance'
const CURRENT_VERSION = app.getVersion()

// 访问仓库里的 version.json（放在 main 分支根目录）
const VERSION_JSON_URL = `https://raw.githubusercontent.com/${GITHUB_OWNER}/${GITHUB_REPO}/main/version.json`

// 追踪状态
let pendingRelease: any = null
let isDownloading = false

function log(level: string, msg: string) {
  // 通过日志面板输出
  sendLog(level, msg)
  // 同时输出到 console（调试用）
  if (level === 'error') console.error('[update]', msg)
  else console.log('[update]', msg)
}

// 简易 semver 比较
function isNewerVersion(newVer: string, currentVer: string): boolean {
  const na = newVer.split('.').map(Number)
  const ca = currentVer.split('.').map(Number)
  for (let i = 0; i < Math.max(na.length, ca.length); i++) {
    const n = na[i] || 0, c = ca[i] || 0
    if (n > c) return true
    if (n < c) return false
  }
  return false
}

// 获取远程 version.json
async function fetchVersionInfo(): Promise<any> {
  const https = await import('https')
  return new Promise((resolve, reject) => {
    const req = https.get(VERSION_JSON_URL, {
      headers: { 'User-Agent': 'DoubaoSeedance-Updater', 'Accept': 'application/json' },
      timeout: 15000
    }, (res) => {
      if (res.statusCode === 404) { reject({ code: 'NOT_FOUND' }); return }
      if (res.statusCode !== 200) { reject({ code: 'HTTP', statusCode: res.statusCode }); return }
      let data = ''
      res.on('data', (c: Buffer) => { data += c.toString() })
      res.on('end', () => {
        try { resolve(JSON.parse(data)) } catch { reject({ code: 'PARSE_ERROR' }) }
      })
    })
    req.on('error', (e: any) => reject({ code: 'NETWORK', message: e.message }))
    req.on('timeout', () => { req.destroy(); reject({ code: 'TIMEOUT' }) })
  })
}

// 下载文件
async function downloadFile(url: string, destPath: string, onProgress?: (p: number) => void): Promise<void> {
  const https = await import('https')
  const { createWriteStream } = await import('fs')

  return new Promise((resolve, reject) => {
    const req = https.get(url, {
      headers: { 'User-Agent': 'DoubaoSeedance-Updater', 'Accept': '*/*' },
      timeout: 300000
    }, (res) => {
      if ([301, 302, 307, 308].includes(res.statusCode)) {
        const loc = res.headers.location
        if (loc) { downloadFile(loc, destPath, onProgress).then(resolve).catch(reject); return }
      }
      if (res.statusCode !== 200) { reject(new Error(`HTTP ${res.statusCode}`)); return }

      const ws = createWriteStream(destPath)
      const contentLength = parseInt(res.headers['content-length'] || '0', 10)
      let downloaded = 0

      res.on('data', (chunk: Buffer) => {
        downloaded += chunk.length
        if (onProgress && contentLength > 0) {
          onProgress(Math.round(downloaded / contentLength * 100))
        }
      })
      res.pipe(ws)
      ws.on('finish', () => resolve())
      ws.on('error', reject)
    })
    req.on('error', reject)
    req.on('timeout', () => { req.destroy(); reject(new Error('下载超时')) })
  })
}

function formatBytes(bytes: number): string {
  if (!bytes) return '未知'
  const m = Math.log(bytes) / Math.log(1024)
  return `${(bytes / Math.pow(1024, Math.floor(m))).toFixed(1)} ${['B','KB','MB','GB'][Math.floor(m)]}`
}

// 检查更新主流程
async function checkForUpdates() {
  log('info', '🔄 正在检查更新...')
  try {
    const info = await fetchVersionInfo()
    const latestVer = info.version

    if (!latestVer) { log('warn', '⚠️ 无法获取版本号'); return }

    if (!isNewerVersion(latestVer, CURRENT_VERSION)) {
      log('info', `✅ 已是最新版本 v${CURRENT_VERSION}`)
      return
    }

    // 发现新版本
    log('success', `🆕 发现新版本: v${latestVer}（当前: v${CURRENT_VERSION}）`)
    pendingRelease = { ...info, version: latestVer }

    const asset = info.portable
    if (!asset) { log('warn', `⚠️ v${latestVer} 未找到安装包信息`); return }

    // 弹窗询问
    const result = await dialog.showMessageBox(mainWindow!, {
      type: 'info',
      title: '发现新版本',
      message: `新版本 v${latestVer} 可用（当前 v${CURRENT_VERSION}）`,
      detail: `大小: ${formatBytes(asset.size)}\n点击确定下载并安装`,
      buttons: ['下载安装', '稍后']
    })

    if (result.response === 0) {
      startDownload(latestVer, asset)
    }
  } catch (err: any) {
    if (err.code === 'NOT_FOUND') {
      log('info', '✅ 已是最新版本（或暂无发布）')
    } else if (err.code === 'TIMEOUT') {
      log('warn', `⏱️ 检查更新超时，请稍后重试`)
    } else {
      log('warn', `⚠️ 检查更新失败: ${err.message || err.code}`)
    }
  }
}

// 开始下载
async function startDownload(version: string, asset: any) {
  isDownloading = true
  const { join } = await import('path')
  const { mkdirSync } = await import('fs')

  const outDir = join(app.getPath('temp'), 'doubao-updater')
  mkdirSync(outDir, { recursive: true })
  const destPath = join(outDir, asset.name)

  log('info', `📥 正在下载: ${asset.name}`)

  try {
    await downloadFile(asset.url, destPath, (percent) => {
      log('info', `📥 下载进度: ${percent}%`)
    })

    log('success', `✅ 下载完成`)
    isDownloading = false

    const result = await dialog.showMessageBox(mainWindow!, {
      type: 'info',
      title: '安装更新',
      message: `v${version} 已下载完成`,
      detail: '点击确定立即重启安装',
      buttons: ['立即重启', '稍后']
    })

    if (result.response === 0) {
      require('child_process').execFile(destPath, ['--updated'], { detached: true, stdio: 'ignore' }, () => {})
      app.quit()
    }
  } catch (err: any) {
    isDownloading = false
    log('error', `❌ 下载失败: ${err.message}`)
  }
}

// IPC：允许渲染进程手动触发检查
ipcMain.handle('app:check-update', async () => {
  await checkForUpdates()
  return { ok: true }
})

app.whenReady().then(() => {
  // CloakBrowser 二进制：打包后在 resources/，开发时在项目根目录
  if (app.isPackaged) {
    process.env.CLOAKBROWSER_BINARY_PATH = join(process.resourcesPath, 'cloakbrowser-binary', 'chrome.exe')
  } else {
    process.env.CLOAKBROWSER_BINARY_PATH = join(__dirname, '..', '..', 'cloakbrowser-binary', 'chrome.exe')
  }
  process.env.CLOAKBROWSER_SKIP_CHECKSUM = 'true'

  // 启动前检查 CloakBrowser 二进制是否存在
  if (!existsSync(process.env.CLOAKBROWSER_BINARY_PATH)) {
    const msg = `未找到 CloakBrowser (Chrome) 二进制文件，请确认已正确解压完整目录后再运行。\n\n预期路径:\n${process.env.CLOAKBROWSER_BINARY_PATH}`
    console.error(msg)
    dialog.showErrorBox('启动失败', msg)
    app.quit()
    return
  }

  electronApp.setAppUserModelId('com.doubao.seedance')
  createWindow()

  // 启动 5 秒后检查更新（不阻塞界面）
  setTimeout(() => { checkForUpdates() }, 5000)

  app.on('browser-window-created', (_, window) => {
    optimizer.watchWindowShortcuts(window)
  })

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  for (const ctx of openBrowserContexts) { try { ctx.close() } catch {} }
  openBrowserContexts.clear()
  accountBrowserMap.clear()
  if (process.platform !== 'darwin') app.quit()
})
app.on('before-quit', () => {
  for (const ctx of openBrowserContexts) { try { ctx.close() } catch {} }
  openBrowserContexts.clear()
  accountBrowserMap.clear()
  try {
    const { rmSync, existsSync } = require('fs')
    const { join } = require('path')
    const tmpDir = join(require('os').tmpdir(), 'playwright')
    if (existsSync(tmpDir)) rmSync(tmpDir, { recursive: true, force: true })
  } catch {}
})
