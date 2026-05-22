"""
Doubao automation engine using Playwright (CDP connection to existing Chrome).

Selectors verified against doubao.com on 2026-05-10:
  - input:    textarea.semi-input-textarea
  - send btn: #flow-end-msg-send  (stable fixed id)
  - reply:    .whitespace-pre-wrap.wrap-anywhere  (last element = latest reply)
  - mode btn: [data-slot="dropdown-menu-trigger"] containing SVG path M13.6552
"""
import asyncio
import threading
import time
import logging
from datetime import datetime
from typing import Optional, Callable

from playwright.async_api import async_playwright, Browser, Page, Playwright

from models import SendMessage, ReplyMessage, ChatMode, SendStatus, AppConfig

logger = logging.getLogger(__name__)

_REPLY_CSS = ".flow-markdown-body"
_SEND_BTN_ID = "#flow-end-msg-send"
_INPUT_CSS = "textarea.semi-input-textarea"

_MODE_NAMES = ("专家", "思考", "快速")

_MODE_MENU_TEXT = {
    ChatMode.EXPERT: "专家",
    ChatMode.THINK: "思考",
    ChatMode.FAST: "快速",
}


class DoubaoAutomation:
    def __init__(self, config: AppConfig):
        self.config = config
        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None
        self._running = False
        self._paused = False
        self._current_mode: Optional[ChatMode] = None
        self._round = 0

        # persistent event loop running in a background thread
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None

        # UI callbacks
        self.on_status_change: Optional[Callable[[int, SendStatus], None]] = None
        self.on_reply_received: Optional[Callable[[ReplyMessage], None]] = None
        self.on_mode_changed: Optional[Callable[[ChatMode], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        self.on_log: Optional[Callable[[str], None]] = None

    # ------------------------------------------------------------------ #
    #  Persistent event loop                                               #
    # ------------------------------------------------------------------ #

    def _ensure_loop(self):
        """Start a persistent background event loop if not already running."""
        if self._loop and self._loop.is_running():
            return
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._loop_thread.start()

    def _run_coro(self, coro):
        """Submit a coroutine to the persistent loop and block until done."""
        self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=300)

    # ------------------------------------------------------------------ #
    #  Browser lifecycle                                                   #
    # ------------------------------------------------------------------ #

    async def _start_async(self) -> bool:
        try:
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.connect_over_cdp("http://localhost:9222")
            contexts = self._browser.contexts
            if contexts and contexts[0].pages:
                self._page = contexts[0].pages[0]
            else:
                ctx = contexts[0] if contexts else await self._browser.new_context()
                self._page = await ctx.new_page()
            self._log("已连接到 Chrome 浏览器")
            return True
        except Exception as e:
            self._log(f"连接浏览器失败: {e}", level="error")
            return False

    def start_browser(self) -> bool:
        return self._run_coro(self._start_async())

    async def _close_async(self):
        if self._pw:
            await self._pw.stop()
        self._pw = None
        self._browser = None
        self._page = None

    def close_browser(self):
        if self._loop and self._loop.is_running():
            self._run_coro(self._close_async())
            self._loop.call_soon_threadsafe(self._loop.stop)

    def is_connected(self) -> bool:
        return self._page is not None and self._browser is not None

    # ------------------------------------------------------------------ #
    #  Mode switching                                                      #
    # ------------------------------------------------------------------ #

    def _target_mode_for_round(self, round_num: int) -> ChatMode:
        if round_num <= self.config.expert_rounds:
            return self.config.first_mode
        return self.config.second_mode

    async def _switch_mode_async(self, mode: ChatMode) -> bool:
        if mode == self._current_mode:
            return True
        try:
            # find the mode trigger button by looking for a dropdown trigger
            # containing a button whose text matches one of the known mode names
            btn_info = await self._page.evaluate(f"""() => {{
                const modeNames = {list(_MODE_NAMES)};
                const triggers = document.querySelectorAll('[data-slot="dropdown-menu-trigger"]');
                for (const t of triggers) {{
                    const inner = t.querySelector('button');
                    if (!inner) continue;
                    const text = (inner.innerText || '').trim();
                    if (modeNames.some(n => text.startsWith(n))) {{
                        const r = inner.getBoundingClientRect();
                        if (r.width > 0) {{
                            return {{x: r.x + r.width/2, y: r.y + r.height/2, found: true, text: text}};
                        }}
                    }}
                }}
                return {{found: false}};
            }}""")

            if not btn_info.get("found"):
                self._log("找不到模式切换按钮", level="error")
                return False

            # use real mouse click at the button's center coordinates
            await self._page.mouse.click(btn_info["x"], btn_info["y"])
            # wait for Radix animation to complete (menu becomes visible)
            await self._page.wait_for_timeout(500)

            # wait for menu to be visible (not invisible)
            for _ in range(10):
                menu_visible = await self._page.evaluate("""() => {
                    const menus = document.querySelectorAll('[role="menu"][data-state="open"]');
                    for (const m of menus) {
                        const style = window.getComputedStyle(m);
                        if (!m.classList.contains('invisible') && style.visibility !== 'hidden') {
                            return true;
                        }
                    }
                    return false;
                }""")
                if menu_visible:
                    break
                await self._page.wait_for_timeout(100)

            target_text = _MODE_MENU_TEXT.get(mode, "")
            # click menu item using Playwright's built-in text matching
            item_clicked = await self._page.evaluate(f"""() => {{
                const menus = document.querySelectorAll('[role="menu"]');
                for (const menu of menus) {{
                    if (menu.classList.contains('invisible')) continue;
                    const items = menu.querySelectorAll('[role="menuitem"], li, div');
                    for (const item of items) {{
                        const t = (item.innerText || '').trim();
                        if (t.startsWith('{target_text}') && t.length < 20) {{
                            const r = item.getBoundingClientRect();
                            return {{x: r.x + r.width/2, y: r.y + r.height/2, text: t, found: true}};
                        }}
                    }}
                }}
                // fallback: search all portals
                for (const portal of document.querySelectorAll('[data-radix-popper-content-wrapper]')) {{
                    const all = portal.querySelectorAll('*');
                    for (const el of all) {{
                        const t = (el.innerText || '').trim();
                        if (t.startsWith('{target_text}') && t.length < 20 && el.children.length === 0) {{
                            const r = el.getBoundingClientRect();
                            if (r.width > 0) return {{x: r.x + r.width/2, y: r.y + r.height/2, text: t, found: true}};
                        }}
                    }}
                }}
                return {{found: false}};
            }}""")

            if item_clicked and item_clicked.get("found"):
                await self._page.mouse.click(item_clicked["x"], item_clicked["y"])
                self._current_mode = mode
                self._log(f"已切换到 {mode.value}（{item_clicked.get('text', '')}）")
                if self.on_mode_changed:
                    self.on_mode_changed(mode)
                await self._page.wait_for_timeout(300)
                return True
            else:
                await self._page.keyboard.press("Escape")
                self._log(f"模式菜单中未找到 {target_text}", level="error")
                return False
        except Exception as e:
            self._log(f"模式切换异常: {e}", level="error")
            return False

    # ------------------------------------------------------------------ #
    #  Send & receive                                                      #
    # ------------------------------------------------------------------ #

    async def _send_message_async(self, msg: SendMessage) -> bool:
        try:
            textarea = self._page.locator(_INPUT_CSS)
            await textarea.click()
            await self._page.wait_for_timeout(100)
            await self._page.keyboard.press("Control+a")
            await self._page.keyboard.press("Delete")
            await self._page.keyboard.type(msg.content, delay=10)
            await self._page.wait_for_timeout(200)
            await self._page.click(_SEND_BTN_ID)
            msg.send_time = datetime.now()
            self._log(f"消息 #{msg.id} 已发送")
            return True
        except Exception as e:
            self._log(f"消息 #{msg.id} 发送失败: {e}", level="error")
            return False

    async def _get_reply_count_async(self) -> int:
        return await self._page.evaluate(f"""() => {{
            return document.querySelectorAll('{_REPLY_CSS}').length;
        }}""")

    async def _wait_for_reply_async(self, timeout: int, baseline: int = -1) -> Optional[str]:
        # Snapshot the last reply text before waiting
        last_text_before = await self._page.evaluate(f"""() => {{
            const els = document.querySelectorAll('{_REPLY_CSS}');
            return els.length > 0 ? els[els.length - 1].innerText.trim() : '__EMPTY__';
        }}""")

        # Wait up to the configured timeout for a new reply:
        # - count increases (new element appeared), OR
        # - last element's text differs from snapshot (in-place streaming update)
        t0 = time.time()
        while time.time() - t0 < timeout:
            count = await self._page.evaluate(f"""() => {{
                return document.querySelectorAll('{_REPLY_CSS}').length;
            }}""")
            last_text = await self._page.evaluate(f"""() => {{
                const els = document.querySelectorAll('{_REPLY_CSS}');
                return els.length > 0 ? els[els.length - 1].innerText.trim() : '__EMPTY__';
            }}""")
            count_ok = count > (baseline if baseline >= 0 else 0)
            text_ok = last_text and last_text != last_text_before and last_text != '__EMPTY__'
            if count_ok or text_ok:
                break
            await self._page.wait_for_timeout(1000)
        else:
            self._log(f"等待回复超时（{timeout}秒未出现新回复）", level="error")
            return None

        # Wait for content to stabilize
        prev_text = ""
        stable_count = 0
        t1 = time.time()
        while time.time() - t1 < timeout:
            current_text = await self._page.evaluate(f"""() => {{
                const els = document.querySelectorAll('{_REPLY_CSS}');
                return els.length > 0 ? els[els.length - 1].innerText.trim() : '';
            }}""")
            if current_text and current_text == prev_text:
                stable_count += 1
                if stable_count >= 5:
                    return current_text
            else:
                stable_count = 0
            prev_text = current_text
            await self._page.wait_for_timeout(1000)

        return prev_text if prev_text else None

    # ------------------------------------------------------------------ #
    #  New conversation                                                    #
    # ------------------------------------------------------------------ #

    async def _new_conversation_async(self, system_prompt: str = "") -> bool:
        try:
            await self._page.goto(self.config.doubao_url, wait_until="domcontentloaded", timeout=15000)
            await self._page.wait_for_timeout(1500)
            self._round = 0
            self._current_mode = None
            self._log("已新建对话")
            if system_prompt:
                dummy = SendMessage(id=0, content=system_prompt)
                await self._send_message_async(dummy)
                await self._wait_for_reply_async(self.config.reply_timeout)
            return True
        except Exception as e:
            self._log(f"新建对话失败: {e}", level="error")
            return False

    def new_conversation(self, system_prompt: str = "") -> bool:
        return self._run_coro(self._new_conversation_async(system_prompt))

    # ------------------------------------------------------------------ #
    #  Main execution loop (runs in background thread via QThread)         #
    # ------------------------------------------------------------------ #

    async def _run_async(self, messages: list[SendMessage], start_index: int = 0):
        self._running = True
        self._paused = False
        reply_counter = 1

        for i, msg in enumerate(messages):
            if i < start_index:
                continue
            if not self._running:
                break

            while self._paused:
                await asyncio.sleep(0.5)
                if not self._running:
                    break

            if not self._running:
                break

            self._round += 1

            # brief pause to let the page settle before interacting
            await asyncio.sleep(0.5)

            if msg.forced_mode and msg.forced_mode != ChatMode.AUTO:
                target_mode = msg.forced_mode
            else:
                target_mode = self._target_mode_for_round(self._round)
            msg.mode = target_mode

            if not await self._switch_mode_async(target_mode):
                self._log(f"消息 #{msg.id} 模式切换失败，继续发送")

            sent = False
            for attempt in range(self.config.max_retries + 1):
                # snapshot reply count before sending so we can detect the new reply
                baseline = await self._get_reply_count_async()
                if await self._send_message_async(msg):
                    sent = True
                    break
                msg.retry_count += 1
                self._log(f"消息 #{msg.id} 第 {attempt + 1} 次重试")
                await asyncio.sleep(2)

            if not sent:
                msg.status = SendStatus.FAILED
                if self.on_status_change:
                    self.on_status_change(msg.id, SendStatus.FAILED)
                continue

            msg.status = SendStatus.SENDING
            if self.on_status_change:
                self.on_status_change(msg.id, SendStatus.SENDING)

            t_start = time.time()
            reply_text = await self._wait_for_reply_async(self.config.reply_timeout, baseline)
            elapsed = int(time.time() - t_start)

            if reply_text is None:
                msg.status = SendStatus.FAILED
                if self.on_status_change:
                    self.on_status_change(msg.id, SendStatus.FAILED)
                continue

            msg.status = SendStatus.SENT
            if self.on_status_change:
                self.on_status_change(msg.id, SendStatus.SENT)

            reply = ReplyMessage(
                id=reply_counter,
                send_id=msg.id,
                content=reply_text,
                collect_time=datetime.now(),
                elapsed_seconds=elapsed,
                mode=target_mode,
            )
            msg.reply_id = reply_counter
            reply_counter += 1

            if self.on_reply_received:
                self.on_reply_received(reply)

            if i < len(messages) - 1 and self._running:
                await asyncio.sleep(self.config.send_interval)

        self._running = False
        self._log("执行完成")

    def run(self, messages: list[SendMessage], start_index: int = 0):
        """Blocking call — run this in a QThread."""
        self._run_coro(self._run_async(messages, start_index))

    def pause(self):
        self._paused = True
        self._log("已暂停")

    def resume(self):
        self._paused = False
        self._log("已继续")

    def stop(self):
        self._running = False
        self._paused = False
        self._log("已停止")

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _log(self, msg: str, level: str = "info"):
        ts = datetime.now().strftime("%H:%M:%S")
        text = f"[{ts}] {msg}"
        if level == "error":
            logger.error(text)
        else:
            logger.info(text)
        if self.on_log:
            self.on_log(text)
