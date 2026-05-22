"""已完成页面"""
import os
import subprocess
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QPushButton, QCheckBox,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont
from qfluentwidgets import (
    LineEdit, PushButton, ComboBox, CardWidget,
    InfoBar, InfoBarPosition, Dialog, FluentIcon as FIF,
)


class CompletedItem(QFrame):
    """单条已完成记录"""

    re_download = Signal(str)  # url
    remove_clicked = Signal(dict)  # data

    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self._data = data
        self.setObjectName('CompletedItem')
        self.setMinimumHeight(56)
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("""
            #CompletedItem {
                background: #FFFFFF;
                border: 1px solid #E8ECF0;
                border-radius: 8px;
                margin: 1px 0px;
            }
            #CompletedItem:hover {
                border-color: #B0D0F0;
                background: #F8FAFD;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)

        # 复选框
        self.checkbox = QCheckBox()
        self.checkbox.setStyleSheet('QCheckBox { border: none; background: transparent; }')
        layout.addWidget(self.checkbox)

        # 信息区
        info = QVBoxLayout()
        info.setSpacing(3)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title = QLabel(self._data.get('title', '未知'))
        title.setFont(QFont('Microsoft YaHei', 11))
        title.setStyleSheet('color: #1a1a1a; border: none; background: transparent;')
        title_row.addWidget(title)

        platform = self._data.get('platform', '')
        if platform:
            from app.utils.link_utils import source_to_display, source_to_color
            badge = QLabel(source_to_display(platform))
            color = source_to_color(platform)
            badge.setStyleSheet(
                f'color: white; background: {color}; border-radius: 3px;'
                'padding: 1px 6px; font-size: 10px; border: none;'
            )
            title_row.addWidget(badge)

        title_row.addStretch()

        size_bytes = self._data.get('size', 0)
        size_label = QLabel(self._fmt(size_bytes))
        size_label.setStyleSheet('color: #999; font-size: 12px; border: none; background: transparent;')
        title_row.addWidget(size_label)

        info.addLayout(title_row)

        path = self._data.get('save_path', '')
        if path:
            path_label = QLabel(path)
            path_label.setStyleSheet('color: #aaa; font-size: 11px; border: none; background: transparent;')
            path_label.setToolTip(path)
            info.addWidget(path_label)

        layout.addLayout(info, stretch=1)

        # 操作按钮
        btn_style = """
            QPushButton {
                background: #F0F2F5;
                border: 1px solid #D0D7DE;
                border-radius: 4px;
                font-size: 12px;
                color: #333;
                padding: 5px 12px;
                min-height: 28px;
            }
            QPushButton:hover {
                background: #D0E4F7;
                border-color: #0078D4;
                color: #0078D4;
            }
        """

        re_btn = QPushButton('重新下载')
        re_btn.setCursor(Qt.PointingHandCursor)
        re_btn.setStyleSheet(btn_style)
        re_btn.clicked.connect(lambda: self.re_download.emit(self._data.get('url', '')))
        layout.addWidget(re_btn)

        del_btn = QPushButton('删除')
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setStyleSheet(btn_style + """
            QPushButton:hover {
                background: #FDE0E0; border-color: #E02020; color: #E02020;
            }
        """)
        del_btn.clicked.connect(lambda: self.remove_clicked.emit(self._data))
        layout.addWidget(del_btn)

        # 双击打开文件夹
        self.setCursor(Qt.PointingHandCursor)

    def mouseDoubleClickEvent(self, event):
        path = self._data.get('save_path', '')
        if path:
            if os.path.exists(path):
                subprocess.Popen(['explorer', os.path.dirname(path)])
            elif os.path.exists(os.path.dirname(path)):
                subprocess.Popen(['explorer', os.path.dirname(path)])

    @property
    def data(self) -> dict:
        return self._data

    @property
    def is_checked(self) -> bool:
        return self.checkbox.isChecked()

    def _fmt(self, b: int) -> str:
        if b <= 0:
            return ''
        if b < 1024 * 1024:
            return f'{b/1024:.0f}KB'
        elif b < 1024 * 1024 * 1024:
            return f'{b/(1024*1024):.1f}MB'
        return f'{b/(1024*1024*1024):.2f}GB'


class CompletedPage(QWidget):
    """已完成下载列表"""

    re_download_requested = Signal(str)  # url

    def __init__(self, settings_manager=None, parent=None):
        super().__init__(parent)
        self._settings = settings_manager
        self._completed = []
        self._items: list[CompletedItem] = []
        self.setStyleSheet('background: #FFFFFF;')
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # 标题
        title = QLabel('已完成下载')
        title.setFont(QFont('Microsoft YaHei', 16, QFont.Bold))
        title.setStyleSheet('color: #1a1a1a; border: none;')
        layout.addWidget(title)

        # 搜索 + 筛选栏
        search_card = CardWidget()
        search_card.setStyleSheet('CardWidget { background: #FAFBFC; border-radius: 10px; }')
        search_layout = QHBoxLayout(search_card)
        search_layout.setContentsMargins(16, 10, 16, 10)
        search_layout.setSpacing(12)

        self.search_input = LineEdit()
        self.search_input.setPlaceholderText('搜索视频标题...')
        self.search_input.setMinimumHeight(36)
        self.search_input.textChanged.connect(self._on_search)
        search_layout.addWidget(self.search_input, stretch=1)

        self.platform_filter = ComboBox()
        self.platform_filter.addItems(['全部'])
        self.platform_filter.currentTextChanged.connect(self._on_search)
        search_layout.addWidget(self.platform_filter)

        layout.addWidget(search_card)

        # 工具栏
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(4, 0, 4, 0)
        toolbar.setSpacing(8)

        self.select_all_cb = QCheckBox('全选')
        self.select_all_cb.setStyleSheet('font-size: 12px; color: #666;')
        self.select_all_cb.toggled.connect(self._on_select_all)
        toolbar.addWidget(self.select_all_cb)
        toolbar.addStretch()

        batch_del = PushButton('批量删除')
        batch_del.setIcon(FIF.DELETE)
        batch_del.clicked.connect(self._on_batch_delete)
        toolbar.addWidget(batch_del)

        layout.addLayout(toolbar)

        # 列表滚动区
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet('QScrollArea { border: none; background: transparent; }')

        self.container = QWidget()
        self.container.setStyleSheet('background: transparent;')
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(4)
        self.list_layout.addStretch()
        scroll.setWidget(self.container)
        layout.addWidget(scroll, stretch=1)

    def _add_item(self, data: dict):
        item = CompletedItem(data, self.container)
        item.re_download.connect(self._on_re_download)
        item.remove_clicked.connect(self._on_remove_one)
        pos = self.list_layout.count() - 1  # before stretch
        self.list_layout.insertWidget(max(0, pos), item)
        self._items.append(item)

    def _on_re_download(self, url: str):
        if url:
            self.re_download_requested.emit(url)
            InfoBar.success(title='已添加', content='重新加入下载队列',
                          position=InfoBarPosition.TOP, parent=self.window(), duration=2000)

    def _on_remove_one(self, data: dict):
        d = Dialog('确认删除', f'确定删除记录「{data.get("title", "")}」吗？\n此操作不会删除已下载的文件。', self.window())
        if d.exec():
            uid = data.get('uid', '')
            self._completed = [c for c in self._completed if c.get('uid') != uid]
            self._settings.set('completed_downloads', self._completed)
            self._refresh_list()

    def _on_select_all(self, checked: bool):
        for item in self._items:
            item.checkbox.setChecked(checked)

    def _on_batch_delete(self):
        checked_items = [item for item in self._items if item.is_checked]
        if not checked_items:
            InfoBar.info(title='提示', content='请先勾选要删除的记录',
                        position=InfoBarPosition.TOP, parent=self.window())
            return
        d = Dialog('批量删除', f'确定删除选中的 {len(checked_items)} 条记录吗？\n此操作不会删除已下载的文件。', self.window())
        if d.exec():
            uids = {item.data.get('uid', '') for item in checked_items}
            self._completed = [c for c in self._completed if c.get('uid') not in uids]
            self._settings.set('completed_downloads', self._completed)
            self._refresh_list()
            InfoBar.success(title='已删除', content=f'已删除 {len(checked_items)} 条记录',
                          position=InfoBarPosition.TOP, parent=self.window(), duration=2000)

    def _on_search(self):
        kw = self.search_input.text().lower()
        pf = self.platform_filter.currentText()
        self._refresh_list(filter_kw=kw, filter_pf=pf)

    def _load_data(self):
        if not self._settings:
            return
        self._completed = self._settings.get('completed_downloads', []) or []
        self._refresh_list()

    def _refresh_list(self, filter_kw: str = '', filter_pf: str = '全部'):
        # 清除所有已显示项
        for item in self._items:
            self.list_layout.removeWidget(item)
            item.deleteLater()
        self._items.clear()
        self.select_all_cb.setChecked(False)

        # 动态更新平台筛选器
        from app.utils.link_utils import source_to_display
        current = self.platform_filter.currentText()
        display_set = set()
        display_to_key = {}
        for data in self._completed:
            pf = data.get('platform', '')
            if pf:
                d = source_to_display(pf)
                display_set.add(d)
                display_to_key[d] = pf
        sorted_displays = sorted(display_set)
        self.platform_filter.blockSignals(True)
        self.platform_filter.clear()
        self.platform_filter.addItem('全部')
        for d in sorted_displays:
            self.platform_filter.addItem(d)
        # 恢复之前的选择
        idx = self.platform_filter.findText(current)
        self.platform_filter.setCurrentIndex(max(0, idx))
        self.platform_filter.blockSignals(False)

        for data in reversed(self._completed):
            title = data.get('title', '').lower()
            platform = data.get('platform', '')

            # 筛选
            if filter_kw and filter_kw not in title:
                continue
            if filter_pf != '全部' and platform != display_to_key.get(filter_pf, ''):
                continue

            self._add_item(data)

    def refresh(self):
        self._load_data()
