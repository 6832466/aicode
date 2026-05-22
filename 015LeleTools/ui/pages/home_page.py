"""
首页 — 功能概览 / 快捷入口
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout,
)
from PySide6.QtCore import Qt, Signal
from qfluentwidgets import (
    CardWidget, StrongBodyLabel, CaptionLabel, BodyLabel,
)

from app.config_manager import ConfigManager


class FeatureCard(CardWidget):
    """功能快捷入口卡片"""

    clicked = Signal()

    def __init__(self, icon: str, title: str, desc: str, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(160)
        self.setCursor(Qt.PointingHandCursor)
        self.title = title

        ly = QVBoxLayout(self)
        ly.setContentsMargins(20, 16, 20, 16)
        ly.setSpacing(8)

        icon_label = QLabel(icon)
        icon_label.setStyleSheet("font-size: 36px;")
        icon_label.setAlignment(Qt.AlignLeft)
        ly.addWidget(icon_label)

        name = StrongBodyLabel(title)
        name.setStyleSheet("font-size: 16px;")
        ly.addWidget(name)

        desc_label = CaptionLabel(desc)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #888;")
        ly.addWidget(desc_label)

        ly.addStretch()

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


class HomePage(QWidget):
    navigate_to = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("home_page")
        self._parent = parent
        self.config = ConfigManager()
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 36, 36, 36)
        layout.setSpacing(20)

        # 标题
        title = StrongBodyLabel("乐乐智能工具箱")
        title.setStyleSheet("font-size: 28px; color: #1a1a1a;")
        layout.addWidget(title)

        sub = CaptionLabel("AI改文 · 多轮对话 · API配置管理    — 一站式文本处理工作台")
        sub.setStyleSheet("font-size: 14px; color: #888; margin-bottom: 8px;")
        layout.addWidget(sub)

        # 功能卡片网格
        grid = QGridLayout()
        grid.setSpacing(16)

        cards = [
            ("\U0001f4dd", "AI改文", "智能文本改写与优化\n改错别字 · 提取人名 · 分镜洗稿\n长篇精简 · 性别转换 · 人称转换"),
            ("\U0001f4ac", "AI多轮对话", "ChatGPT风格多轮对话\n多会话管理 · 流式输出\n系统提示词 · 模型切换"),
            ("⚙️", "全局设置", "API端点管理与配置\n多端点支持 · 模型切换\n系统代理 · 连接测试"),
        ]

        for i, (icon, name, desc) in enumerate(cards):
            card = FeatureCard(icon, name, desc)
            card.clicked.connect(self._make_card_handler(i))
            grid.addWidget(card, 0, i)

        layout.addLayout(grid)

        # 状态概览
        info_row = QHBoxLayout()
        info_row.setSpacing(20)

        ep = self.config.get_default_endpoint()
        api_status = f"API: {ep.name} ({ep.model})" if ep else "API: 未配置"

        stats = [
            ("端点状态", api_status),
            ("配置端点", f"{len(self.config.get_endpoints())} 个"),
            ("主题", "浅色"),
        ]
        for label, value in stats:
            card = CardWidget()
            card.setFixedHeight(60)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(16, 8, 16, 8)
            cl.addWidget(CaptionLabel(label))
            v = BodyLabel(value)
            v.setStyleSheet("color: #2ecc71; font-weight: bold;")
            cl.addWidget(v)
            info_row.addWidget(card)

        layout.addLayout(info_row)

        layout.addStretch()

    def _make_card_handler(self, index: int):
        """点击卡片跳转到对应页面"""
        def handler():
            if self._parent:
                pages = {
                    0: self._parent.text_rewrite_page,
                    1: self._parent.ai_chat_page,
                    2: self._parent.settings_page,
                }
                target = pages.get(index)
                if target:
                    self._parent.switchTo(target)
        return handler
