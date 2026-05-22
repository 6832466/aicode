from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.api_client import BitBrowserAPI
from app.models import GroupItem
from app.utils import extract_host, proxy_type_label


class BrowserEditDialog(QDialog):
    """创建/编辑浏览器窗口对话框（4 标签页）"""

    def __init__(
        self,
        api: BitBrowserAPI,
        parent=None,
        browser_data: dict | None = None,
        groups: list[GroupItem] | None = None,
    ):
        super().__init__(parent)
        self.api = api
        self.browser_data = browser_data or {}
        self._groups = groups or []
        self._is_edit = bool(browser_data and browser_data.get("id"))

        self.setWindowTitle("编辑浏览器" if self._is_edit else "新建浏览器")
        self.setMinimumSize(560, 520)
        self.resize(600, 560)

        layout = QVBoxLayout(self)

        # Tabs
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self._build_basic_tab()
        self.set_groups(self._groups)  # 填充分组下拉框
        self._build_login_tab()
        self._build_proxy_tab()
        self._build_fingerprint_tab()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.ok_btn = QPushButton("确定")
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

        # Populate from existing data
        if self.browser_data:
            self._populate_from_data()

    # ---- Tabs ----

    def _build_basic_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        form.setLabelAlignment(Qt.AlignRight)

        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText("浏览器窗口名称")
        form.addRow("名称 *", self.edit_name)

        self.combo_group = QComboBox()
        self.combo_group.setEditable(False)
        form.addRow("所属分组", self.combo_group)

        self.edit_platform = QLineEdit()
        self.edit_platform.setPlaceholderText("https://www.facebook.com")
        form.addRow("平台地址 *", self.edit_platform)

        self.edit_remark = QLineEdit()
        self.edit_remark.setPlaceholderText("备注信息")
        form.addRow("备注", self.edit_remark)

        self.edit_url = QLineEdit()
        self.edit_url.setPlaceholderText("打开附加 URL，多个用逗号分隔")
        form.addRow("附加 URL", self.edit_url)

        self.tabs.addTab(tab, "基本信息")

    def _build_login_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        form.setLabelAlignment(Qt.AlignRight)

        self.edit_user_name = QLineEdit()
        form.addRow("用户名", self.edit_user_name)

        self.edit_password = QLineEdit()
        self.edit_password.setEchoMode(QLineEdit.Password)
        form.addRow("密码", self.edit_password)

        self.edit_cookie = QTextEdit()
        self.edit_cookie.setPlaceholderText("Cookie JSON 数组格式")
        self.edit_cookie.setMaximumHeight(120)
        form.addRow("Cookie", self.edit_cookie)

        self.tabs.addTab(tab, "登录信息")

    def _build_proxy_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        form.setLabelAlignment(Qt.AlignRight)

        self.combo_proxy_method = QComboBox()
        self.combo_proxy_method.addItem("自定义代理", 2)
        self.combo_proxy_method.addItem("提取 IP", 3)
        self.combo_proxy_method.currentIndexChanged.connect(self._on_proxy_method_change)
        form.addRow("代理方式", self.combo_proxy_method)

        self.combo_proxy_type = QComboBox()
        for t in ["noproxy", "http", "https", "socks5"]:
            self.combo_proxy_type.addItem(proxy_type_label(t), t)
        form.addRow("代理类型", self.combo_proxy_type)

        self.edit_host = QLineEdit()
        self.edit_host.setPlaceholderText("代理主机地址")
        form.addRow("主机", self.edit_host)

        self.spin_port = QSpinBox()
        self.spin_port.setRange(0, 65535)
        self.spin_port.setValue(0)
        form.addRow("端口", self.spin_port)

        self.edit_proxy_user = QLineEdit()
        form.addRow("代理用户名", self.edit_proxy_user)

        self.edit_proxy_pass = QLineEdit()
        self.edit_proxy_pass.setEchoMode(QLineEdit.Password)
        form.addRow("代理密码", self.edit_proxy_pass)

        # 提取 IP 相关
        self.edit_dynamic_url = QLineEdit()
        self.edit_dynamic_url.setPlaceholderText("代理提取链接")
        form.addRow("提取链接", self.edit_dynamic_url)

        self.combo_dynamic_channel = QComboBox()
        for ch in ["rola", "doveip", "cloudam", "ipidea", "common"]:
            self.combo_dynamic_channel.addItem(ch, ch)
        form.addRow("提取渠道", self.combo_dynamic_channel)

        self.chk_dynamic_change_ip = QCheckBox("每次打开更换 IP")
        form.addRow("", self.chk_dynamic_change_ip)

        self.tabs.addTab(tab, "代理设置")

    def _build_fingerprint_tab(self):
        tab = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        form = QFormLayout(inner)
        form.setLabelAlignment(Qt.AlignRight)

        # 内核版本
        self.combo_core = QComboBox()
        self.combo_core.addItems(["104", "92"])
        form.addRow("内核版本", self.combo_core)

        # 操作系统
        self.combo_os = QComboBox()
        for o in ["Win32", "MacIntel", "Linux i686", "Linux armv7l"]:
            self.combo_os.addItem(o, o)
        form.addRow("操作系统", self.combo_os)

        # UA
        self.edit_ua = QLineEdit()
        self.edit_ua.setPlaceholderText("留空自动生成")
        form.addRow("User-Agent", self.edit_ua)

        # 分辨率
        self.combo_resolution = QComboBox()
        for r in ["1920 x 1080", "1366 x 768", "1440 x 900", "1536 x 864", "1280 x 720"]:
            self.combo_resolution.addItem(r, r)
        form.addRow("分辨率", self.combo_resolution)

        # 时区
        self.edit_timezone = QLineEdit()
        self.edit_timezone.setPlaceholderText("Asia/Shanghai")
        form.addRow("时区", self.edit_timezone)

        # 语言
        self.edit_languages = QLineEdit()
        self.edit_languages.setPlaceholderText("zh-CN,zh;q=0.9")
        form.addRow("语言", self.edit_languages)

        # WebRTC
        self.combo_webrtc = QComboBox()
        self.combo_webrtc.addItems(["替换", "允许", "禁用"])
        form.addRow("WebRTC", self.combo_webrtc)

        # Canvas
        self.combo_canvas = QComboBox()
        self.combo_canvas.addItems(["随机", "禁用"])
        form.addRow("Canvas", self.combo_canvas)

        # WebGL
        self.combo_webgl = QComboBox()
        self.combo_webgl.addItems(["随机", "禁用"])
        form.addRow("WebGL", self.combo_webgl)

        # 音频
        self.combo_audio = QComboBox()
        self.combo_audio.addItems(["随机", "禁用"])
        form.addRow("音频指纹", self.combo_audio)

        # CPU 并发
        self.spin_cpu = QSpinBox()
        self.spin_cpu.setRange(1, 64)
        self.spin_cpu.setValue(4)
        form.addRow("CPU 并发数", self.spin_cpu)

        # 内存
        self.combo_memory = QComboBox()
        for m in ["1", "2", "4", "8"]:
            self.combo_memory.addItem(f"{m} GB", m)
        self.combo_memory.setCurrentText("4 GB")
        form.addRow("设备内存", self.combo_memory)

        # 窗口尺寸
        self.spin_width = QSpinBox()
        self.spin_width.setRange(400, 3840)
        self.spin_width.setValue(1280)
        form.addRow("窗口宽度", self.spin_width)
        self.spin_height = QSpinBox()
        self.spin_height.setRange(200, 2160)
        self.spin_height.setValue(720)
        form.addRow("窗口高度", self.spin_height)

        scroll.setWidget(inner)
        tab_layout = QVBoxLayout(tab)
        tab_layout.addWidget(scroll)
        self.tabs.addTab(tab, "指纹设置")

    # ---- Handlers ----

    def _on_proxy_method_change(self, idx: int):
        """代理方式切换时显示/隐藏相关字段"""
        is_extract = idx == 1  # 提取 IP
        # 自定义代理字段
        for w in [self.edit_host, self.spin_port, self.edit_proxy_user, self.edit_proxy_pass]:
            w.setEnabled(not is_extract)
        # 提取 IP 字段
        self.edit_dynamic_url.setEnabled(is_extract)
        self.combo_dynamic_channel.setEnabled(is_extract)
        self.chk_dynamic_change_ip.setEnabled(is_extract)

    # ---- Data ----

    def set_groups(self, groups: list[GroupItem]):
        self._groups = groups
        self.combo_group.clear()
        self.combo_group.addItem("（无分组）", "")
        for g in groups:
            self.combo_group.addItem(g.name, g.id)

    def get_data(self) -> dict:
        """返回可直接传给 /browser/update 的参数字典"""
        d: dict[str, Any] = {}

        # Basic
        d["name"] = self.edit_name.text().strip()
        d["platform"] = self.edit_platform.text().strip()
        d["platformIcon"] = extract_host(d["platform"])
        d["remark"] = self.edit_remark.text().strip()
        d["url"] = self.edit_url.text().strip()

        group_id = self.combo_group.currentData()
        if group_id:
            d["groupId"] = group_id

        # Login
        d["userName"] = self.edit_user_name.text().strip()
        d["password"] = self.edit_password.text().strip()
        cookie = self.edit_cookie.toPlainText().strip()
        if cookie:
            d["cookie"] = cookie

        # Proxy
        d["proxyMethod"] = self.combo_proxy_method.currentData()
        d["proxyType"] = self.combo_proxy_type.currentData()
        if d["proxyMethod"] == 2:
            d["host"] = self.edit_host.text().strip()
            d["port"] = self.spin_port.value()
            d["proxyUserName"] = self.edit_proxy_user.text().strip()
            d["proxyPassword"] = self.edit_proxy_pass.text().strip()
        else:
            d["dynamicIpUrl"] = self.edit_dynamic_url.text().strip()
            d["dynamicIpChannel"] = self.combo_dynamic_channel.currentData()
            d["isDynamicIpChangeIp"] = self.chk_dynamic_change_ip.isChecked()

        # Fingerprint
        fp: dict[str, Any] = {}
        fp["coreVersion"] = self.combo_core.currentText()
        fp["os"] = self.combo_os.currentData()
        ua = self.edit_ua.text().strip()
        if ua:
            fp["userAgent"] = ua
        fp["resolution"] = self.combo_resolution.currentData()
        tz = self.edit_timezone.text().strip()
        if tz:
            fp["timeZone"] = tz
        lang = self.edit_languages.text().strip()
        if lang:
            fp["languages"] = lang

        webrtc_map = {"替换": "0", "允许": "1", "禁用": "2"}
        fp["webRTC"] = webrtc_map.get(self.combo_webrtc.currentText(), "0")

        canvas_map = {"随机": "0", "禁用": "1"}
        fp["canvas"] = canvas_map.get(self.combo_canvas.currentText(), "0")

        webgl_map = {"随机": "0", "禁用": "1"}
        fp["webGL"] = webgl_map.get(self.combo_webgl.currentText(), "0")

        audio_map = {"随机": "0", "禁用": "1"}
        fp["audioContext"] = audio_map.get(self.combo_audio.currentText(), "0")

        fp["hardwareConcurrency"] = str(self.spin_cpu.value())
        fp["deviceMemory"] = self.combo_memory.currentData()
        fp["openWidth"] = self.spin_width.value()
        fp["openHeight"] = self.spin_height.value()

        d["browserFingerPrint"] = fp

        return d

    def _populate_from_data(self):
        """编辑模式：从 browser_data 填充表单"""
        bd = self.browser_data

        self.edit_name.setText(bd.get("name", ""))
        self.edit_platform.setText(bd.get("platform", ""))
        self.edit_remark.setText(bd.get("remark", ""))
        self.edit_url.setText(bd.get("url", ""))

        # Set group
        gid = bd.get("groupId", "")
        if gid:
            idx = self.combo_group.findData(gid)
            if idx >= 0:
                self.combo_group.setCurrentIndex(idx)

        self.edit_user_name.setText(bd.get("userName", ""))
        self.edit_password.setText(bd.get("password", ""))
        cookie = bd.get("cookie", "")
        if cookie:
            self.edit_cookie.setPlainText(cookie)

        # Proxy
        pm = bd.get("proxyMethod", 2)
        self.combo_proxy_method.setCurrentIndex(0 if pm == 2 else 1)
        pt = bd.get("proxyType", "noproxy")
        idx = self.combo_proxy_type.findData(pt)
        if idx >= 0:
            self.combo_proxy_type.setCurrentIndex(idx)
        self.edit_host.setText(bd.get("host", ""))
        self.spin_port.setValue(bd.get("port", 0))
        self.edit_proxy_user.setText(bd.get("proxyUserName", ""))
        self.edit_proxy_pass.setText(bd.get("proxyPassword", ""))
        self.edit_dynamic_url.setText(bd.get("dynamicIpUrl", ""))

        # Fingerprint
        fp = bd.get("browserFingerPrint", {}) or {}
        cv = fp.get("coreVersion", "104")
        idx = self.combo_core.findText(str(cv))
        if idx >= 0:
            self.combo_core.setCurrentIndex(idx)
        self.edit_ua.setText(fp.get("userAgent", ""))
        self.edit_timezone.setText(fp.get("timeZone", ""))
        self.edit_languages.setText(fp.get("languages", ""))
        res = fp.get("resolution", "1920 x 1080")
        idx = self.combo_resolution.findText(res)
        if idx >= 0:
            self.combo_resolution.setCurrentIndex(idx)

        webrtc_rev = {"0": "替换", "1": "允许", "2": "禁用"}
        wr = webrtc_rev.get(fp.get("webRTC", "0"), "替换")
        self.combo_webrtc.setCurrentText(wr)

        canvas_rev = {"0": "随机", "1": "禁用"}
        cs = canvas_rev.get(fp.get("canvas", "0"), "随机")
        self.combo_canvas.setCurrentText(cs)

        webgl_rev = {"0": "随机", "1": "禁用"}
        wg = webgl_rev.get(fp.get("webGL", "0"), "随机")
        self.combo_webgl.setCurrentText(wg)

        audio_rev = {"0": "随机", "1": "禁用"}
        ac = audio_rev.get(fp.get("audioContext", "0"), "随机")
        self.combo_audio.setCurrentText(ac)

        hc = fp.get("hardwareConcurrency", "4")
        self.spin_cpu.setValue(int(hc))
        dm = fp.get("deviceMemory", "4")
        idx = self.combo_memory.findData(str(dm))
        if idx >= 0:
            self.combo_memory.setCurrentIndex(idx)
        self.spin_width.setValue(fp.get("openWidth", 1280))
        self.spin_height.setValue(fp.get("openHeight", 720))
