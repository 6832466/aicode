from PySide6.QtCore import Qt, QUrl, Signal, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QMessageBox,
)
from PySide6.QtWebEngineWidgets import QWebEngineView

from qfluentwidgets import PrimaryPushButton, PushButton, BodyLabel

from app.config import app_icon_path

RUNWAY_LOGIN_URL = "https://app.runwayml.com/login"
RUNWAY_VIDEO_URL = (
    "https://app.runwayml.com/video-tools/teams/LeleRpa/ai-tools/generate"
    "?tool=video&mode=tools"
)

# ---------------------------------------------------------------------------
# JS to find and click Seedance 2.0 model selector
# ---------------------------------------------------------------------------
SWITCH_SEEDANCE_JS = r"""
(function() {
    let out = { found: [], current: null, action: 'none' };

    // ---- Strategy 1: search EVERY element with innerText ----
    let all = document.querySelectorAll('*');
    for (let el of all) {
        let txt = '';
        try { txt = el.innerText || ''; } catch(e) {}
        if (!txt || txt.length > 120) continue;
        let lower = txt.toLowerCase();
        if (lower.includes('seedance') && lower.includes('2')) {
            // If element itself is clickable
            let tag = el.tagName.toLowerCase();
            let role = el.getAttribute('role') || '';
            out.found.push({
                tag: tag,
                text: txt.slice(0, 60),
                clickable: (tag === 'button' || role === 'button' || role === 'radio' ||
                            el.onclick !== null || el.classList.contains('cursor-pointer')),
                classes: el.className?.slice?.(0, 80) || '',
            });
            // Click the clickable ancestor
            let target = el;
            while (target && target !== document.body) {
                let t = target.tagName.toLowerCase();
                let r = target.getAttribute('role') || '';
                if (t === 'button' || r === 'button' || r === 'radio' || r === 'tab' ||
                    target.classList.contains('cursor-pointer') ||
                    target.classList.contains('selectable') ||
                    target.classList.contains('selected') ||
                    target.getAttribute('data-testid') ||
                    target.getAttribute('data-value')) {
                    target.click();
                    out.action = 'clicked: ' + txt.slice(0, 40);
                    return JSON.stringify(out);
                }
                target = target.parentElement;
            }
            // Fallback: click the element directly
            el.click();
            out.action = 'clicked_direct: ' + txt.slice(0, 40);
            return JSON.stringify(out);
        }
    }

    // ---- Strategy 2: look for "Video models" expandable ----
    let btns = document.querySelectorAll('button');
    for (let b of btns) {
        let t = (b.textContent || '').trim();
        if (/video\s*model/i.test(t) || /模型/i.test(t)) {
            b.click();
            out.action = 'clicked_video_models_button';
            // After expanding, search again after delay
            setTimeout(function() {
                let inner = document.querySelectorAll('*');
                for (let el of inner) {
                    let txt = (el.innerText || '').trim();
                    if (txt.length > 80) continue;
                    if (/seedance.*2/i.test(txt)) {
                        el.click();
                    }
                }
            }, 500);
            return JSON.stringify(out);
        }
    }

    // ---- Strategy 3: try tab/list pattern (model selector as tabs) ----
    let tabs = document.querySelectorAll('[role="tab"], [role="radio"], [role="option"]');
    for (let t of tabs) {
        let txt = (t.textContent || '').trim();
        if (/seedance.*2/i.test(txt)) {
            t.click();
            out.action = 'clicked_tab: ' + txt.slice(0, 40);
            return JSON.stringify(out);
        }
    }

    // ---- Strategy 4: search by data attributes ----
    let dataEls = document.querySelectorAll('[data-value*="seedance"], [data-model*="seedance"], [data-id*="seedance"]');
    for (let el of dataEls) {
        el.click();
        out.action = 'clicked_data_attr';
        return JSON.stringify(out);
    }

    out.action = 'not_found';
    return JSON.stringify(out);
})();
"""


class TokenHelperDialog(QDialog):
    token_ready = Signal(str, str)  # token, team_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("登录 RunwayML 获取令牌")
        self.resize(1000, 700)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
        self._set_icon()

        self._token: str = ""
        self._team_id: str = ""
        self._logged_in: bool = False
        self._navigated_to_video: bool = False
        self._model_checked: bool = False
        self._setup_ui()

    def _set_icon(self):
        try:
            p = app_icon_path()
            if p.exists():
                self.setWindowIcon(QIcon(str(p)))
        except Exception:
            pass

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        hint = BodyLabel(
            "在下方浏览器中登录 RunwayML。"
            "登录后会自动跳转视频工具页并尝试切换 Seedance 2.0。"
            "如自动切换失败请手动点击页面底部的模型选择。"
        )
        layout.addWidget(hint)

        # Web view
        self._webview = QWebEngineView()
        self._webview.setUrl(QUrl(RUNWAY_LOGIN_URL))
        self._webview.loadFinished.connect(self._on_load_finished)
        layout.addWidget(self._webview, stretch=1)

        # Button row
        btn_row = QHBoxLayout()
        self._status_label = BodyLabel("请登录…")
        self._status_label.setStyleSheet("color: #888;")

        self._btn_switch_model = PushButton("强制切换 Seedance 2.0")
        self._btn_switch_model.clicked.connect(self._on_switch_model)
        self._btn_switch_model.setEnabled(False)

        self._btn_extract = PrimaryPushButton("提取令牌")
        self._btn_extract.clicked.connect(self._on_extract)
        self._btn_extract.setEnabled(False)

        self._btn_cancel = PushButton("取消")
        self._btn_cancel.clicked.connect(self.reject)

        btn_row.addWidget(self._status_label)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_switch_model)
        btn_row.addWidget(self._btn_extract)
        btn_row.addWidget(self._btn_cancel)
        layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Page navigation & model detection
    # ------------------------------------------------------------------

    def _on_load_finished(self, ok: bool):
        if not ok:
            return
        current_url = self._webview.url().toString()

        # Detect login complete
        if "app.runwayml.com" in current_url and "login" not in current_url:
            if not self._logged_in:
                self._logged_in = True
                self._status_label.setText("登录成功，跳转到视频工具页…")
                self._status_label.setStyleSheet("color: #4CAF50;")
                self._webview.setUrl(QUrl(RUNWAY_VIDEO_URL))
                return

            if not self._navigated_to_video:
                self._navigated_to_video = True
                self._status_label.setText("视频工具页已加载，检测模型中…")
                # Give page time to fully render
                QTimer.singleShot(3000, self._detect_and_switch_model)

    def _detect_and_switch_model(self):
        self._webview.page().runJavaScript(
            SWITCH_SEEDANCE_JS, self._on_model_switch_result
        )

    def _on_model_switch_result(self, raw: str):
        import json
        self._btn_extract.setEnabled(True)
        self._btn_switch_model.setEnabled(True)

        try:
            result = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            result = {"action": str(raw)[:100]}

        action = result.get("action", "unknown")
        found = result.get("found", [])

        if action and action.startswith("clicked"):
            self._status_label.setText(f"已自动切换 Seedance 2.0 ✓ ({action})")
            self._status_label.setStyleSheet("color: #4CAF50;")
        elif found:
            self._status_label.setText(f"找到 Seedance 2.0 但未点击，请手动选择")
            self._status_label.setStyleSheet("color: #FF9800;")
        else:
            self._status_label.setText(
                "未自动找到 Seedance 2.0，请在页面底部手动切换模型"
            )
            self._status_label.setStyleSheet("color: #FF9800;")

    def _on_switch_model(self):
        self._status_label.setText("正在查找并切换模型…")
        self._webview.page().runJavaScript(
            SWITCH_SEEDANCE_JS, self._on_model_switch_result
        )

    # ------------------------------------------------------------------
    # Token extraction
    # ------------------------------------------------------------------

    def _on_extract(self):
        js = r"""
(function() {
    let results = {};

    // 1. RW_USER_TOKEN
    let raw = localStorage.getItem('RW_USER_TOKEN');
    if (raw && raw.length > 20) results['RW_USER_TOKEN'] = raw;

    // 2. Auth0 SPA tokens
    for (let i = 0; i < localStorage.length; i++) {
        let key = localStorage.key(i);
        if (key && key.indexOf('@@auth0') === 0) {
            try {
                let data = JSON.parse(localStorage.getItem(key));
                let body = (data && data.body) ? data.body : {};
                if (body.id_token) results['auth0_id_token'] = body.id_token;
                if (body.access_token) results['auth0_access_token'] = body.access_token;
            } catch(e) {}
        }
    }

    // 3. Any JWT-looking value
    for (let i = 0; i < localStorage.length; i++) {
        let key = localStorage.key(i);
        let val = localStorage.getItem(key);
        if (val && typeof val === 'string' && val.indexOf('eyJ') === 0 && val.length > 50) {
            let shortKey = key.substring(0, 15).replace(/[^a-zA-Z0-9]/g, '_');
            results['scan_' + shortKey] = val;
        }
    }

    // 4. Numeric team ID from localStorage
    let teamData = localStorage.getItem('rw__lastUsedTeamId');
    if (teamData) {
        try {
            let parsed = JSON.parse(teamData);
            if (parsed.lastUsedTeamId) results['TEAM_ID'] = parsed.lastUsedTeamId;
        } catch(e) {}
    }

    // 5. All key names for debug
    let allKeys = [];
    for (let i = 0; i < localStorage.length; i++) {
        allKeys.push(localStorage.key(i));
    }
    results['_keys'] = allKeys;

    return JSON.stringify(results);
})();
"""
        self._webview.page().runJavaScript(js, self._on_token_received)

    def _on_token_received(self, raw: str):
        import json
        if not raw:
            QMessageBox.warning(self, "获取失败", "未能读取到任何 localStorage 数据。")
            return

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"raw": raw}

        all_keys = data.pop("_keys", [])
        # Extract numeric team ID from localStorage
        if data.get("TEAM_ID"):
            self._team_id = str(data["TEAM_ID"])
        token = None
        source = ""

        if data.get("RW_USER_TOKEN"):
            token = data["RW_USER_TOKEN"]
            source = "RW_USER_TOKEN"
        else:
            for k, v in data.items():
                if v and len(str(v)) > 50 and str(v).startswith("eyJ"):
                    token = str(v)
                    source = k
                    break

        if token and len(token) > 20:
            self._token = token
            # Fallback: try JWT payload if localStorage didn't have team ID
            if not self._team_id:
                self._team_id = self._decode_team_id_from_jwt(token)
            self.token_ready.emit(token, self._team_id)
            team_info = f"\n团队 ID: {self._team_id}" if self._team_id else "\n团队 ID: 未检测到，请手动填写"
            QMessageBox.information(
                self, "令牌获取成功",
                f"已提取 JWT 令牌\n来源: {source}\n长度: {len(token)} 字符{team_info}\n已自动填入设置。"
            )
            self.accept()
        else:
            keys_str = "\n".join(f"  • {k}" for k in all_keys[:15])
            if len(all_keys) > 15:
                keys_str += f"\n  … 共 {len(all_keys)} 个键"
            QMessageBox.warning(
                self, "获取失败",
                f"未找到有效的 JWT 令牌。\n\n"
                f"localStorage 中的键:\n{keys_str}\n\n"
                "请确认：\n"
                "1. 已成功登录 RunwayML\n"
                "2. 当前页面在 app.runwayml.com 域名下\n"
                "3. 页面已完全加载"
            )

    def _decode_team_id_from_jwt(self, token: str) -> str:
        """Try to extract team/workspace ID from JWT payload."""
        try:
            import base64
            import json
            # JWT format: header.payload.signature
            parts = token.split(".")
            if len(parts) >= 2:
                # Pad the payload to make it valid base64
                payload = parts[1]
                padding = 4 - len(payload) % 4
                if padding != 4:
                    payload += "=" * padding
                decoded = base64.urlsafe_b64decode(payload)
                data = json.loads(decoded)
                # Try common claim names for team/workspace
                for key in ("teamId", "team_id", "workspaceId", "workspace_id",
                            "https://runwayml.com/team_id", "https://runwayml.com/workspace"):
                    if key in data and data[key]:
                        return str(data[key])
        except Exception:
            pass
        return ""

    def get_token(self) -> str:
        return self._token
