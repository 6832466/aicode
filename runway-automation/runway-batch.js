/**
 * RunwayML 批量视频生成自动化脚本
 *
 * 用法:
 *   1. 先以远程调试模式启动 Chrome（需要先关闭所有 Chrome 窗口）:
 *      "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
 *
 *   2. 在启动的 Chrome 中登录 RunwayML: https://app.runwayml.com
 *
 *   3. 运行脚本:
 *      node runway-batch.js
 *
 *   可选参数:
 *      --start=N     从第 N 个开始（断点续传）
 *      --delay=MS    每次提交间隔毫秒数（默认 5000）
 *      --dry-run     仅打印将要执行的操作，不实际提交
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

// ========== 配置 ==========
const RUNWAY_URL =
  'https://app.runwayml.com/video-tools/teams/LeleRpa/ai-tools/generate?tool=video&mode=tools';
const PROMPTS_FILE = path.join(__dirname, 'prompts.json');
const CDP_PORT = 9222;
const DEFAULT_DELAY = 5000; // 每次提交间隔 5 秒
const GENERATION_TIMEOUT = 120000; // 生成超时 2 分钟
const LOG_FILE = path.join(__dirname, 'batch-log.json');

// ========== 解析命令行参数 ==========
const args = process.argv.slice(2);
const START_INDEX = Math.max(0, parseInt(args.find((a) => a.startsWith('--start='))?.split('=')[1] || '0'));
const DELAY_MS = parseInt(args.find((a) => a.startsWith('--delay='))?.split('=')[1] || String(DEFAULT_DELAY));
const DRY_RUN = args.includes('--dry-run');

// ========== 工具函数 ==========
function log(message) {
  const ts = new Date().toISOString();
  const line = `[${ts}] ${message}`;
  console.log(line);
}

function loadLog() {
  try {
    if (fs.existsSync(LOG_FILE)) return JSON.parse(fs.readFileSync(LOG_FILE, 'utf-8'));
  } catch {}
  return { completed: [], failed: [], lastIndex: 0 };
}

function saveLog(logData) {
  fs.writeFileSync(LOG_FILE, JSON.stringify(logData, null, 2));
}

// ========== 核心自动化逻辑 ==========
async function selectReference(page, referenceName) {
  log(`选择引用: ${referenceName}`);

  // 点击 References 按钮打开面板
  const refsButton = page.locator('button', { hasText: 'References' }).last();
  await refsButton.click();
  await page.waitForTimeout(800);

  // 通过 JS 点击 gridListItem 来选中引用
  const clicked = await page.evaluate((name) => {
    const grid = document.querySelector('[role="grid"]');
    if (!grid) return false;
    const items = grid.querySelectorAll('[class*="gridListItem"]');
    for (const item of items) {
      if (item.textContent.trim().includes(name)) {
        item.click();
        return true;
      }
    }
    return false;
  }, referenceName);

  if (!clicked) {
    throw new Error(`找不到引用: ${referenceName}`);
  }

  await page.waitForTimeout(500);
  log(`已选择引用: ${referenceName}`);
}

async function fillPrompt(page, promptText) {
  log(`填写提示词: ${promptText.substring(0, 60)}...`);

  // 使用 evaluate 直接设置 prompt 内容（React 组件可能需要触发 change 事件）
  await page.evaluate((text) => {
    // 尝试多种方式找到 prompt 输入框
    const selectors = [
      'textarea[placeholder*="Prompt"]',
      '[role="textbox"][aria-multiline="true"]',
      'textarea',
    ];
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && el.closest('[class*="generate"]')) continue; // 跳过其他区域
      if (el) {
        // React 需要模拟原生输入
        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
          window.HTMLTextAreaElement.prototype, 'value'
        ).set;
        nativeInputValueSetter.call(el, text);
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
      }
    }
    return false;
  }, promptText);

  await page.waitForTimeout(300);
}

async function clickGenerate(page) {
  log('点击生成按钮...');

  // 找到 Generate 按钮（排除其他包含 Generate 文字的元素）
  const genButton = page.locator('button').filter({ hasText: /^Generate$/ }).last();
  await genButton.click();
  await page.waitForTimeout(1000);

  log('已提交生成请求');
}

async function waitForGenerationComplete(page) {
  // 检查是否出现生成进度或完成状态
  // RunwayML 可能会显示进度条或队列状态
  log('等待生成完成...');
  try {
    // 等待生成按钮重新可用（表示上一次生成完成）
    await page.waitForSelector('button:has-text("Generate")', {
      timeout: GENERATION_TIMEOUT,
    });
    await page.waitForTimeout(2000);
    log('生成似乎已完成');
  } catch {
    log('等待超时，继续下一个');
  }
}

async function processOne(page, { reference, prompt }, index) {
  log(`\n========== 处理 #${index + 1}: [${reference}] ${prompt.substring(0, 50)}... ==========`);

  try {
    // 1. 选择引用
    await selectReference(page, reference);

    // 2. 填写提示词
    await fillPrompt(page, prompt);

    if (DRY_RUN) {
      log('[DRY-RUN] 跳过实际提交');
      return { success: true };
    }

    // 3. 点击生成
    await clickGenerate(page);

    // 4. 等待完成
    await waitForGenerationComplete(page);

    return { success: true };
  } catch (err) {
    log(`错误: ${err.message}`);
    return { success: false, error: err.message };
  }
}

// ========== 主函数 ==========
async function main() {
  const prompts = JSON.parse(fs.readFileSync(PROMPTS_FILE, 'utf-8'));
  const total = prompts.length;
  log(`加载了 ${total} 条提示词`);
  log(`起始索引: ${START_INDEX}, 延迟: ${DELAY_MS}ms, Dry-run: ${DRY_RUN}`);

  const batchLog = loadLog();

  // 连接到已有的 Chrome 实例
  let browser;
  try {
    browser = await chromium.connectOverCDP(`http://localhost:${CDP_PORT}`);
    log('已连接到 Chrome');
  } catch {
    console.error('\n无法连接到 Chrome！请先启动 Chrome 远程调试模式：');
    console.error(
      '"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222',
    );
    console.error('或者:');
    console.error(
      '"C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222',
    );
    process.exit(1);
  }

  // 获取或创建 RunwayML 页面
  const contexts = browser.contexts();
  const context = contexts[0];
  let page = context.pages().find((p) => p.url().includes('runwayml.com'));

  if (!page) {
    page = await context.newPage();
    await page.goto(RUNWAY_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForTimeout(5000);
    log('已打开 RunwayML 页面');
  }

  // 检查登录状态
  const currentUrl = page.url();
  if (currentUrl.includes('login') || currentUrl.includes('sign-in')) {
    console.error('未登录 RunwayML！请在 Chrome 中手动登录后再运行此脚本。');
    process.exit(1);
  }
  log(`当前页面: ${currentUrl}`);

  // 批量处理
  let successCount = 0;
  let failCount = 0;

  for (let i = START_INDEX; i < total; i++) {
    const result = await processOne(page, prompts[i], i);

    if (result.success) {
      successCount++;
      batchLog.completed.push({ index: i, ...prompts[i], time: new Date().toISOString() });
    } else {
      failCount++;
      batchLog.failed.push({
        index: i,
        ...prompts[i],
        error: result.error,
        time: new Date().toISOString(),
      });
    }

    batchLog.lastIndex = i;
    saveLog(batchLog);

    log(`进度: ${i + 1}/${total} | 成功: ${successCount} | 失败: ${failCount}`);

    // 延迟避免限流
    if (i < total - 1) {
      log(`等待 ${DELAY_MS / 1000} 秒...`);
      await page.waitForTimeout(DELAY_MS);
    }
  }

  log(`\n========== 完成 ==========`);
  log(`总计: ${total} | 成功: ${successCount} | 失败: ${failCount}`);
  log(`日志已保存到: ${LOG_FILE}`);

  await browser.close();
}

main().catch((err) => {
  console.error('脚本运行失败:', err);
  process.exit(1);
});
