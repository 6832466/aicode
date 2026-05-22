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
    QSpinBox,
    QVBoxLayout,
)

from qfluentwidgets import BodyLabel, StrongBodyLabel

from app.utils import proxy_type_label


class BatchProxyDialog(QDialog):
    """批量修改代理配置对话框"""

    def __init__(self, count: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("批量修改代理")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 标题
        title = StrongBodyLabel(f"已选 {count} 个浏览器")
        layout.addWidget(title)

        # 表单
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)

        self.combo_method = QComboBox()
        self.combo_method.addItem("自定义代理", 2)
        self.combo_method.addItem("提取 IP", 3)
        self.combo_method.currentIndexChanged.connect(self._on_method_change)
        form.addRow("代理方式", self.combo_method)

        self.combo_type = QComboBox()
        for t in ["noproxy", "http", "https", "socks5"]:
            self.combo_type.addItem(proxy_type_label(t), t)
        form.addRow("代理类型", self.combo_type)

        self.edit_host = QLineEdit()
        self.edit_host.setPlaceholderText("代理主机地址")
        form.addRow("主机", self.edit_host)

        self.spin_port = QSpinBox()
        self.spin_port.setRange(0, 65535)
        form.addRow("端口", self.spin_port)

        self.edit_user = QLineEdit()
        form.addRow("用户名", self.edit_user)

        self.edit_pass = QLineEdit()
        form.addRow("密码", self.edit_pass)

        # 提取 IP
        self.edit_dynamic_url = QLineEdit()
        self.edit_dynamic_url.setPlaceholderText("代理提取链接")
        form.addRow("提取链接", self.edit_dynamic_url)

        self.combo_channel = QComboBox()
        for ch in ["rola", "doveip", "cloudam", "ipidea", "common"]:
            self.combo_channel.addItem(ch, ch)
        form.addRow("提取渠道", self.combo_channel)

        self.chk_change_ip = QCheckBox("每次打开更换 IP")
        form.addRow("", self.chk_change_ip)

        self.chk_is_ipv6 = QCheckBox("IPv6 协议")
        form.addRow("", self.chk_is_ipv6)

        layout.addLayout(form)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.ok_btn = QPushButton("确定")
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

        self._on_method_change(0)

    def _on_method_change(self, idx: int):
        is_extract = idx == 1
        self.edit_host.setEnabled(not is_extract)
        self.spin_port.setEnabled(not is_extract)
        self.edit_user.setEnabled(not is_extract)
        self.edit_pass.setEnabled(not is_extract)
        self.edit_dynamic_url.setEnabled(is_extract)
        self.combo_channel.setEnabled(is_extract)
        self.chk_change_ip.setEnabled(is_extract)

    def get_data(self) -> dict:
        """返回可传给 /browser/proxy/update 的参数字典（不含 ids）"""
        d: dict[str, Any] = {
            "proxyMethod": self.combo_method.currentData(),
            "proxyType": self.combo_type.currentData(),
        }
        if d["proxyMethod"] == 2:
            # 自定义代理
            d["host"] = self.edit_host.text().strip()
            d["port"] = self.spin_port.value()
            d["proxyUserName"] = self.edit_user.text().strip()
            d["proxyPassword"] = self.edit_pass.text().strip()
        else:
            # 提取 IP
            d["dynamicIpUrl"] = self.edit_dynamic_url.text().strip()
            d["dynamicIpChannel"] = self.combo_channel.currentData()
            d["isDynamicIpChangeIp"] = self.chk_change_ip.isChecked()
        d["isIpv6"] = self.chk_is_ipv6.isChecked()
        return d
