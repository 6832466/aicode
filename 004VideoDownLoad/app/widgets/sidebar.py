"""自定义侧边栏 - 固定展开 + 折叠式分组（卷帘式）"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont, QMouseEvent


class SidebarGroup(QWidget):
    """可折叠的侧边栏分组"""
    item_clicked = Signal(str)  # item_key

    def __init__(self, title: str, icon: str, items: list[dict], expanded: bool = True, parent=None):
        super().__init__(parent)
        self._title = title
        self._items = items
        self._expanded = expanded
        self._item_buttons: list[QPushButton] = []
        self._current_key: str = None
        self._setup_ui()

    def _setup_ui(self):
        self.setObjectName('SidebarGroup')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 分组标题 - 用 QFrame 代替 QPushButton 避免主题样式冲突
        self._header = QFrame()
        self._header.setObjectName('SidebarHeader')
        self._header.setCursor(Qt.PointingHandCursor)
        self._header.setFixedHeight(34)
        self._header.mousePressEvent = self._on_header_click
        self._header.setStyleSheet("""
            QFrame#SidebarHeader {
                background: transparent;
                border: none;
                border-radius: 6px;
            }
            QFrame#SidebarHeader:hover {
                background: #E8ECF0;
            }
        """)

        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(12, 6, 8, 6)
        header_layout.setSpacing(6)

        self._arrow_label = QLabel('▼' if self._expanded else '▶')
        self._arrow_label.setFixedWidth(14)
        self._arrow_label.setStyleSheet(
            'color: #555555; font-size: 11px; background: transparent; border: none;'
        )
        header_layout.addWidget(self._arrow_label)

        title_lbl = QLabel(self._title)
        title_lbl.setStyleSheet(
            'color: #333333; font-size: 12px; font-weight: bold; background: transparent; border: none;'
        )
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        layout.addWidget(self._header)

        # 子项容器
        self._content = QWidget()
        self._content.setObjectName('SidebarContent')
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 2, 0, 2)
        self._content_layout.setSpacing(0)

        for item in self._items:
            btn = self._make_item(item)
            self._content_layout.addWidget(btn)
            self._item_buttons.append(btn)

        self._content.setVisible(self._expanded)
        layout.addWidget(self._content)

    def _on_header_click(self, event: QMouseEvent):
        self._toggle()

    def _make_item(self, item: dict) -> QPushButton:
        key = item['key']
        text = item['text']
        icon_text = item.get('icon', '')

        btn = QPushButton(f'  {icon_text}  {text}')
        btn.setObjectName(f'SidebarItem_{key}')
        btn.setCursor(Qt.PointingHandCursor)
        btn.setProperty('selected', 'false')
        btn.clicked.connect(lambda checked=False, k=key: self._on_item_click(k))
        btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 6px;
                text-align: left;
                padding: 8px 12px 8px 32px;
                font-size: 13px;
                color: #555555;
                min-height: 20px;
            }
            QPushButton:hover {
                background: #E8F0FE;
                color: #0078D4;
            }
            QPushButton[selected="true"] {
                background: #D3E5FA;
                color: #0078D4;
                font-weight: bold;
            }
        """)
        return btn

    def _on_item_click(self, key: str):
        self.set_current(key)
        self.item_clicked.emit(key)

    def set_current(self, key: str):
        self._current_key = key
        for btn in self._item_buttons:
            should = f'SidebarItem_{key}' == btn.objectName()
            btn.setProperty('selected', 'true' if should else 'false')
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _toggle(self):
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self._arrow_label.setText('▼' if self._expanded else '▶')


class CustomSidebar(QFrame):
    """完整的自定义侧边栏"""
    page_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('CustomSidebar')
        self.setFixedWidth(220)
        self._groups: list[SidebarGroup] = []
        self._settings_btn: QPushButton = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 16, 8, 16)
        layout.setSpacing(4)

        # 品牌标题
        brand = QLabel('  乐乐短视频下载器')
        brand.setFont(QFont('Microsoft YaHei', 13, QFont.Bold))
        brand.setStyleSheet('color: #1A1A1A; padding: 8px 8px 16px 8px; border: none; background: transparent;')
        layout.addWidget(brand)

        # 下载管理分组
        self._download_group = SidebarGroup('下载管理', '', [
            {'key': 'download_queue', 'text': '下载队列', 'icon': '⬇'},
            {'key': 'completed', 'text': '已完成', 'icon': '✓'},
            {'key': 'logs', 'text': '日志', 'icon': '📋'},
        ], expanded=True)
        self._download_group.item_clicked.connect(self._on_item_click)
        layout.addWidget(self._download_group)
        self._groups.append(self._download_group)

        # 分割线
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet('border: none; background: #E0E0E0; max-height: 1px; margin: 6px 8px;')
        layout.addWidget(sep)

        # 设置（独立按钮）
        self._settings_btn = QPushButton('  ⚙  设置')
        self._settings_btn.setObjectName('SidebarSettingsBtn')
        self._settings_btn.setCursor(Qt.PointingHandCursor)
        self._settings_btn.setProperty('selected', 'false')
        self._settings_btn.setMinimumHeight(36)
        self._settings_btn.clicked.connect(lambda: self._on_item_click('settings'))
        self._settings_btn.setStyleSheet("""
            QPushButton#SidebarSettingsBtn {
                background: transparent;
                border: none;
                border-radius: 6px;
                text-align: left;
                padding: 10px 12px;
                font-size: 13px;
                color: #555555;
                margin: 2px 0;
            }
            QPushButton#SidebarSettingsBtn:hover {
                background: #E8F0FE;
                color: #0078D4;
            }
            QPushButton#SidebarSettingsBtn[selected="true"] {
                background: #D3E5FA;
                color: #0078D4;
                font-weight: bold;
            }
        """)
        layout.addWidget(self._settings_btn)

        layout.addStretch()

        version = QLabel('  v1.0.0')
        version.setStyleSheet('color: #AAAAAA; font-size: 11px; padding: 4px 8px; border: none; background: transparent;')
        layout.addWidget(version)

        self.setStyleSheet("""
            #CustomSidebar {
                background: #F8F9FB;
                border-right: 1px solid #E5E5E5;
            }
        """)

    def _on_item_click(self, key: str):
        self._download_group.set_current(key)
        self._settings_btn.setProperty('selected', 'true' if key == 'settings' else 'false')
        self._settings_btn.style().unpolish(self._settings_btn)
        self._settings_btn.style().polish(self._settings_btn)
        self.page_changed.emit(key)

    def set_current(self, key: str):
        self._on_item_click(key)
