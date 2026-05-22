"""
RunwayML 批量视频生成自动化脚本
通过 Chrome DevTools Protocol (CDP) 注入 JS 到浏览器中执行

用法:
  1. 以调试模式启动 Chrome:
     chrome.exe --remote-debugging-port=9222
  2. 在 Chrome 中登录 https://app.runwayml.com
     打开目标页面 (Seedance 2.0 视频生成页)
  3. 编辑 prompts.json 填入你的提示词列表
  4. 运行: python runwayChrome.py --dry-run   (预览模式，不实际提交)
     python runwayChrome.py                  (正式运行)
  5. 断点续传: python runwayChrome.py --start=50
  6. 查看进度: python runwayChrome.py --check
  7. 强制停止: python runwayChrome.py --stop
"""

import json
import time
import sys
import websocket
import requests
from pathlib import Path

# ========== 配置 ==========
CDP_HOST = "127.0.0.1"
CDP_PORT = 9222
RUNWAY_URL = (
    "https://app.runwayml.com/video-tools/teams/LeleRpa/ai-tools/generate"
    "?tool=video&mode=tools"
)
PROMPTS_FILE = Path(__file__).parent / "prompts.json"
GENERATION_WAIT = 8000   # 每次点生成后等待毫秒
BETWEEN_DELAY = 2000     # 任务间隔毫秒


# ========== CDP 客户端 ==========
class CDPClient:
    def __init__(self, host=CDP_HOST, port=CDP_PORT):
        self.host = host
        self.port = port
        self.ws = None
        self.msg_id = 0

    def connect(self):
        """连接到 Chrome 并找到 RunwayML 页面"""
        resp = requests.get(f"http://{self.host}:{self.port}/json", timeout=5)
        pages = resp.json()

        target = None
        for p in pages:
            if "runwayml.com" in p.get("url", ""):
                target = p
                break
        if not target:
            target = pages[0]
            print(f"[WARN] 未找到 RunwayML 页面，使用: {target['url']}")

        ws_url = target["webSocketDebuggerUrl"]
        self.ws = websocket.create_connection(ws_url)
        print(f"[OK] 已连接到: {target['url']}")
        return target

    def send(self, method, params=None):
        self.msg_id += 1
        msg = {"id": self.msg_id, "method": method, "params": params or {}}
        self.ws.send(json.dumps(msg))
        while True:
            resp = json.loads(self.ws.recv())
            if resp.get("id") == self.msg_id:
                if "error" in resp:
                    raise Exception(f"CDP Error: {resp['error']}")
                return resp.get("result", {})

    def evaluate(self, expression, await_promise=True):
        return self.send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": await_promise,
        })

    def close(self):
        if self.ws:
            self.ws.close()


# ========== 自动化 JavaScript ==========
def build_script(prompts, start_index=0, dry_run=False):
    """生成注入浏览器的自动化 JS"""
    prompts_json = json.dumps(prompts[start_index:], ensure_ascii=False)

    return f"""
(async () => {{
    if (window.__rwa && window.__rwa.running) {{
        return {{ error: '自动化已在运行', progress: window.__rwa.current }};
    }}

    const PROMPTS = {prompts_json};
    const DRY_RUN = {str(dry_run).lower()};
    const GEN_WAIT = {GENERATION_WAIT};
    const BETWEEN = {BETWEEN_DELAY};
    const START = {start_index};

    window.__rwa = {{
        running: true, startIndex: START, total: PROMPTS.length,
        current: 0, success: 0, failed: 0, results: [], log: []
    }};

    const log = msg => {{
        const line = `[${{new Date().toISOString()}}] ${{msg}}`;
        console.log('[RunwayAuto]', line);
        window.__rwa.log.push(line);
        if (window.__rwa.log.length > 500) window.__rwa.log.shift();
    }};

    const sleep = ms => new Promise(r => setTimeout(r, ms));

    // ===== 核心操作函数 =====

    async function openRefsPanel() {{
        const btn = [...document.querySelectorAll('button')].find(
            b => b.textContent.trim() === 'References' && b.offsetParent !== null
        );
        if (!btn) {{ log('ERROR: 找不到 References 按钮'); return false; }}
        btn.click();
        await sleep(800);
        return true;
    }}

    async function selectRef(name) {{
        const grid = document.querySelector('[role="grid"]');
        if (!grid) {{ log('ERROR: 找不到 References 面板'); return false; }}
        const items = grid.querySelectorAll('[class*="gridListItem"]');
        for (const item of items) {{
            if (item.textContent.trim().includes(name)) {{
                item.click();
                await sleep(400);
                log(`已选引用: ${{name}}`);
                return true;
            }}
        }}
        log(`ERROR: 找不到引用 "${{name}}"`);
        return false;
    }}

    async function selectAllRefs(refNames) {{
        const ok = [];
        for (const name of refNames) {{
            const found = await selectRef(name);
            ok.push(found);
        }}
        return ok.filter(Boolean).length;
    }}

    async function selectDropdown(buttonLabelPattern, optionText) {{
        // buttonLabelPattern: regex string to match button text (e.g. "\\\\d+s" for duration, ":" for ratio)
        const btn = [...document.querySelectorAll('button')].find(
            b => new RegExp(buttonLabelPattern).test(b.textContent.trim())
                && b.getAttribute('aria-haspopup') === 'listbox'
                && b.offsetParent !== null
        );
        if (!btn) {{ log(`ERROR: 找不到下拉按钮 (pattern=${{buttonLabelPattern}})`); return false; }}

        btn.click();
        await sleep(400);

        const listboxes = document.querySelectorAll('[role="listbox"]');
        let targetListbox = null;
        for (const lb of listboxes) {{
            if (lb.offsetParent !== null) {{ targetListbox = lb; break; }}
        }}
        if (!targetListbox) {{ log('ERROR: 找不到展开的 listbox'); return false; }}

        const options = targetListbox.querySelectorAll('[role="option"]');
        for (const opt of options) {{
            if (opt.textContent.trim() === optionText) {{
                opt.click();
                await sleep(300);
                log(`已选择: ${{optionText}}`);
                return true;
            }}
        }}
        log(`ERROR: 找不到选项 "${{optionText}}"，可用: ${{[...options].map(o=>o.textContent.trim()).join(', ')}}`);
        // 点击空白关闭
        document.body.click();
        await sleep(200);
        return false;
    }}

    async function selectDuration(seconds) {{
        const optionText = seconds + ' seconds';
        return await selectDropdown('\\\\d+s', optionText);
    }}

    async function selectRatio(ratio) {{
        return await selectDropdown(':', ratio);
    }}

    async function fillPrompt(text, refNames) {{
        const el = document.querySelector('[role="textbox"][contenteditable="true"]');
        if (!el) {{ log('ERROR: 找不到 Prompt 输入框'); return false; }}

        el.focus();
        await sleep(100);
        document.execCommand('selectAll', false);
        await sleep(50);
        document.execCommand('insertText', false, text);
        await sleep(200);
        const ok = el.textContent === text;
        if (!ok) log(`WARN: Prompt 不匹配. 期望=${{text.length}}字 实际=${{el.textContent.length}}字`);
        else log(`已填 Prompt: "${{text.substring(0, 60)}}${{text.length > 60 ? '...' : ''}}"`);
        return ok;
    }}

    async function clickGen() {{
        const btn = [...document.querySelectorAll('button')].find(
            b => b.textContent.trim() === 'Generate' && b.offsetParent !== null && !b.disabled
        );
        if (!btn) {{ log('ERROR: 找不到可用的 Generate 按钮'); return false; }}
        btn.click();
        log('已点击 Generate');
        await sleep(1000);
        return true;
    }}

    async function waitGenReady() {{
        let waited = 0;
        const max = 300000; // 5 分钟超时
        while (waited < max) {{
            const btn = [...document.querySelectorAll('button')].find(
                b => b.textContent.trim() === 'Generate' && !b.disabled && b.offsetParent !== null
            );
            if (btn) {{ log(`生成完成 (等待 ${{waited/1000}}s)`); return true; }}
            await sleep(3000);
            waited += 3000;
        }}
        log('WARN: 等待生成超时');
        return false;
    }}

    // ===== 主循环 =====
    log(`===== 开始批量自动化: ${{PROMPTS.length}} 个任务 =====`);
    if (DRY_RUN) log('*** DRY RUN 模式 ***');

    for (let i = 0; i < PROMPTS.length; i++) {{
        if (!window.__rwa.running) {{ log('用户手动停止'); break; }}

        const item = PROMPTS[i];
        const references = item.references || [];
        const prompt = item.prompt || '';
        const duration = item.duration || 8;
        const ratio = item.ratio || '16:9';
        const idx = START + i;
        const refStr = references.join(', ') || '(none)';
        log(`\\n--- #${{idx+1}} [${{refStr}}] dur=${{duration}}s ratio=${{ratio}} ---`);
        log(`Prompt: ${{prompt.substring(0, 80)}}...`);
        window.__rwa.current = i + 1;

        try {{
            // 1. 选择引用
            await openRefsPanel();
            const selected = await selectAllRefs(references);
            log(`选中引用: ${{selected}}/${{references.length}}`);

            // 2. 选择时长
            await selectDuration(duration);

            // 3. 选择比例
            await selectRatio(ratio);

            // 4. 填写提示词
            await fillPrompt(prompt, references);

            if (!DRY_RUN) {{
                await clickGen();
                log('等待生成...');
                await waitGenReady();
            }} else {{
                log('[DRY-RUN] 跳过提交');
            }}

            window.__rwa.success++;
            window.__rwa.results.push({{
                index: idx, references, prompt: prompt.substring(0, 80),
                duration, ratio, status: 'ok', time: new Date().toISOString()
            }});
        }} catch (e) {{
            window.__rwa.failed++;
            log(`FAILED: ${{e.message}}`);
            window.__rwa.results.push({{
                index: idx, references, prompt: prompt.substring(0, 80),
                duration, ratio, status: 'failed', error: e.message, time: new Date().toISOString()
            }});
        }}

        log(`进度: ${{i+1}}/${{PROMPTS.length}} | OK:${{window.__rwa.success}} FAIL:${{window.__rwa.failed}}`);

        if (i < PROMPTS.length - 1 && window.__rwa.running) {{
            await sleep(BETWEEN);
        }}
    }}

    window.__rwa.running = false;
    log(`\\n===== 完成: OK=${{window.__rwa.success}} FAIL=${{window.__rwa.failed}} =====`);

    return {{
        status: 'completed',
        total: PROMPTS.length,
        success: window.__rwa.success,
        failed: window.__rwa.failed,
        results: window.__rwa.results
    }};
}})();
"""


# ========== 主程序 ==========
def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    check_only = "--check" in args
    stop = "--stop" in args
    start_index = 0
    for a in args:
        if a.startswith("--start="):
            start_index = int(a.split("=")[1])

    # 加载提示词
    if not PROMPTS_FILE.exists():
        print(f"[ERROR] 找不到配置文件: {PROMPTS_FILE}")
        sys.exit(1)

    prompts = json.loads(PROMPTS_FILE.read_text(encoding="utf-8"))
    print(f"加载了 {len(prompts)} 条提示词 | start={start_index} | dry_run={dry_run}")

    # 连接 Chrome
    client = CDPClient()
    try:
        target = client.connect()
    except Exception as e:
        print(f"\n[ERROR] 无法连接到 Chrome ({e})")
        print("请先以调试模式启动 Chrome:")
        print('  chrome.exe --remote-debugging-port=9222')
        sys.exit(1)

    # 检查登录
    result = client.evaluate("window.location.href")
    url = result.get("result", {}).get("value", "")
    if "login" in url.lower() or "sign-in" in url.lower():
        print("[ERROR] 未登录，请在 Chrome 中登录后重试")
        client.close()
        sys.exit(1)

    # --stop
    if stop:
        print("停止中...")
        r = client.evaluate("(() => { if(window.__rwa) window.__rwa.running=false; return 'stopped'; })()", False)
        print(r.get("result", {}).get("value", "done"))
        client.close()
        return

    # --check
    if check_only:
        r = client.evaluate("""(() => {
            const a = window.__rwa;
            if (!a) return {status:'not_started'};
            return {status:a.running?'running':'stopped', current:a.current, total:a.total,
                    success:a.success, failed:a.failed, logs:(a.log||[]).slice(-8)};
        })()""", False)
        print(json.dumps(r.get("result", {}).get("value", {}), indent=2, ensure_ascii=False))
        client.close()
        return

    # 执行
    remaining = len(prompts) - start_index
    print(f"处理 {remaining} 个任务 | 生成等待 {GENERATION_WAIT/1000}s | 间隔 {BETWEEN_DELAY/1000}s")

    if not dry_run:
        print("\n*** 3 秒后开始实际提交，Ctrl+C 取消 ***")
        for i in range(3, 0, -1):
            print(f"  {i}...")
            time.sleep(1)

    script = build_script(prompts, start_index, dry_run)
    print("注入脚本中...")
    result = client.evaluate(script, await_promise=True)
    value = result.get("result", {}).get("value", {})
    print(json.dumps(value, indent=2, ensure_ascii=False))

    # 保存结果
    if value.get("results"):
        out = Path(__file__).parent / "batch_result.json"
        out.write_text(json.dumps(value["results"], indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"结果已保存: {out}")

    client.close()


if __name__ == "__main__":
    main()
