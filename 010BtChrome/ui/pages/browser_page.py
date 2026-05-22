from __future__ import annotations

import logging

from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QPainter, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QStyle,
    QStyleOptionButton,
    QStyleOptionHeader,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    ComboBox,
    Dialog,
    FluentIcon,
    InfoBar,
    LineEdit,
    MessageBox,
    PrimaryPushButton,
    PushButton,
    TableView,
    TitleLabel,
)

from app.api_client import BitBrowserAPI
from app.config import PAGE_SIZE
from app.models import BrowserItem, GroupItem
from app.utils import extract_rows, extract_total, proxy_type_label, short_str
from ui.widgets.api_worker import ApiCaller
from ui.widgets.batch_proxy_dialog import BatchProxyDialog
from ui.widgets.browser_edit_dialog import BrowserEditDialog
from ui.widgets.layout_dialog import LayoutDialog
from ui.widgets.status_indicator import STATUS_CLOSED, STATUS_OPEN, STATUS_UNKNOWN, StatusDelegate

logger = logging.getLogger(__name__)

COL_SELECT = 0
COL_SEQ = 1
COL_NAME = 2
COL_GROUP = 3
COL_PLATFORM = 4
COL_REMARK = 5
COL_PROXY = 6
COL_STATUS = 7
COL_COUNT = 8

HEADERS = ["", "序号", "名称", "分组", "平台", "备注", "代理", "状态"]


class CheckboxHeader(QHeaderView):
    """支持全选 checkbox 的表头"""

    selectAllToggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self._checked = False
        self.setSectionsClickable(True)

    def set_checked(self, checked: bool):
        self._checked = checked
        self.updateSection(COL_SELECT)

    def paintSection(self, painter: QPainter, rect: QRect, logicalIndex: int):
        if logicalIndex != COL_SELECT:
            super().paintSection(painter, rect, logicalIndex)
            return

        # 先画背景
        opt = self._section_style_option(rect, logicalIndex)
        self.style().drawControl(QStyle.CE_Header, opt, painter, self)

        # 在中间画 checkbox
        cb_opt = QStyleOptionButton()
        cb_opt.rect = self._checkbox_rect(rect)
        cb_opt.state = QStyle.State_Enabled | QStyle.State_Active
        if self._checked:
            cb_opt.state |= QStyle.State_On
        else:
            cb_opt.state |= QStyle.State_Off
        self.style().drawControl(QStyle.CE_CheckBox, cb_opt, painter, self)

    def _section_style_option(self, rect: QRect, logicalIndex: int):
        opt = QStyleOptionHeader()
        opt.rect = rect
        opt.section = logicalIndex
        opt.state = QStyle.State_Enabled | QStyle.State_Active
        if self.isSortIndicatorShown() and logicalIndex == self.sortIndicatorSection():
            opt.sortIndicator = (
                QStyleOptionHeader.SortUp
                if self.sortIndicatorOrder() == Qt.AscendingOrder
                else QStyleOptionHeader.SortDown
            )
        return opt

    @staticmethod
    def _checkbox_rect(header_rect: QRect) -> QRect:
        size = 18
        x = header_rect.center().x() - size // 2
        y = header_rect.center().y() - size // 2
        return QRect(x, y, size, size)

    def mousePressEvent(self, event):
        if self.logicalIndexAt(event.pos()) == COL_SELECT:
            self._checked = not self._checked
            self.selectAllToggled.emit(self._checked)
            self.updateSection(COL_SELECT)
            event.accept()
            return
        super().mousePressEvent(event)


class BrowserPage(QWidget):
    def __init__(self, api: BitBrowserAPI, parent=None):
        super().__init__(parent)
        self.api = api
        self._browsers: list[BrowserItem] = []
        self._groups: list[GroupItem] = []
        self._current_page = 0
        self._total_count = 0
        self._total_pages = 1
        self._open_pending: list[str] = []
        self._close_pending: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(12)

        # 标题
        title = TitleLabel("浏览器管理")
        layout.addWidget(title)

        # 工具栏
        layout.addLayout(self._build_toolbar())

        # 表格
        self._setup_table()
        layout.addWidget(self.table, 1)

        # 分页
        layout.addLayout(self._build_pagination())

    # ---- Toolbar ----

    def _build_toolbar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(6)

        self.btn_new = PrimaryPushButton(FluentIcon.ADD, "新建")
        self.btn_new.clicked.connect(self._add_browser)
        bar.addWidget(self.btn_new)

        self.btn_open = PushButton(FluentIcon.PLAY, "打开")
        self.btn_open.clicked.connect(self._open_browser)
        bar.addWidget(self.btn_open)

        self.btn_close = PushButton(FluentIcon.CANCEL, "关闭")
        self.btn_close.clicked.connect(self._close_browser)
        bar.addWidget(self.btn_close)

        self.btn_delete = PushButton(FluentIcon.DELETE, "删除")
        self.btn_delete.clicked.connect(self._delete_browser)
        bar.addWidget(self.btn_delete)

        sep = QLabel(" | ")
        sep.setStyleSheet("color: #94a3b8;")
        bar.addWidget(sep)

        self.btn_batch_group = PushButton("批量改分组")
        self.btn_batch_group.clicked.connect(self._batch_change_group)
        bar.addWidget(self.btn_batch_group)

        self.btn_batch_proxy = PushButton("批量改代理")
        self.btn_batch_proxy.clicked.connect(self._batch_proxy)
        bar.addWidget(self.btn_batch_proxy)

        self.btn_batch_remark = PushButton("批量改备注")
        self.btn_batch_remark.clicked.connect(self._batch_remark)
        bar.addWidget(self.btn_batch_remark)

        self.btn_layout = PushButton(FluentIcon.TILES, "排列窗口")
        self.btn_layout.clicked.connect(self._arrange_windows)
        bar.addWidget(self.btn_layout)

        bar.addStretch()

        self.search_input = LineEdit()
        self.search_input.setPlaceholderText("搜索名称…")
        self.search_input.setMaximumWidth(200)
        self.search_input.returnPressed.connect(self._search)
        bar.addWidget(self.search_input)

        self.btn_refresh = PushButton(FluentIcon.SYNC, "刷新")
        self.btn_refresh.clicked.connect(self.refresh_data)
        bar.addWidget(self.btn_refresh)

        return bar

    # ---- Table ----

    def _setup_table(self):
        self.table = TableView(self)
        self.table.setBorderVisible(True)
        self.table.setBorderRadius(8)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)

        self._model = QStandardItemModel(0, COL_COUNT, self)
        self._model.setHorizontalHeaderLabels(HEADERS)
        self.table.setModel(self._model)

        # 自定义表头（全选 checkbox）
        self._header = CheckboxHeader(self.table)
        self._header.selectAllToggled.connect(self._on_select_all)
        self.table.setHorizontalHeader(self._header)

        # 列宽
        hdr = self._header
        hdr.setSectionResizeMode(COL_SELECT, QHeaderView.Fixed)
        hdr.resizeSection(COL_SELECT, 40)
        hdr.setSectionResizeMode(COL_SEQ, QHeaderView.Fixed)
        hdr.resizeSection(COL_SEQ, 60)
        hdr.setSectionResizeMode(COL_STATUS, QHeaderView.Fixed)
        hdr.resizeSection(COL_STATUS, 60)
        hdr.setSectionResizeMode(COL_NAME, QHeaderView.Stretch)
        hdr.setSectionResizeMode(COL_GROUP, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(COL_PLATFORM, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(COL_REMARK, QHeaderView.Stretch)
        hdr.setSectionResizeMode(COL_PROXY, QHeaderView.ResizeToContents)

        # 状态列使用自定义委托绘制圆点
        self.table.setItemDelegateForColumn(COL_STATUS, StatusDelegate(self.table))

    def _on_select_all(self, checked: bool):
        for row in range(self._model.rowCount()):
            item = self._model.item(row, COL_SELECT)
            if item:
                item.setCheckState(Qt.Checked if checked else Qt.Unchecked)

    def _context_menu(self, pos):
        idx = self.table.indexAt(pos)
        if not idx or not idx.isValid():
            return
        menu = QMenu(self.table)

        act_open = QAction(FluentIcon.PLAY, "打开", self)
        act_open.triggered.connect(self._open_browser)
        menu.addAction(act_open)

        act_close = QAction(FluentIcon.CANCEL, "关闭", self)
        act_close.triggered.connect(self._close_browser)
        menu.addAction(act_close)

        menu.addSeparator()

        act_edit = QAction(FluentIcon.EDIT, "编辑", self)
        act_edit.triggered.connect(self._edit_browser)
        menu.addAction(act_edit)

        act_delete = QAction(FluentIcon.DELETE, "删除", self)
        act_delete.triggered.connect(self._delete_browser)
        menu.addAction(act_delete)

        menu.addSeparator()

        act_copy_ws = QAction("复制 WS 地址", self)
        act_copy_ws.triggered.connect(self._copy_ws_url)
        menu.addAction(act_copy_ws)

        act_copy_driver = QAction("复制 chromedriver 路径", self)
        act_copy_driver.triggered.connect(self._copy_driver_path)
        menu.addAction(act_copy_driver)

        act_copy_http = QAction("复制 HTTP 地址", self)
        act_copy_http.triggered.connect(self._copy_http_url)
        menu.addAction(act_copy_http)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ---- Pagination ----

    def _build_pagination(self) -> QHBoxLayout:
        pbar = QHBoxLayout()
        self.pag_label = QLabel("第 0 页  共 0 条")
        self.pag_label.setStyleSheet("color: #64748b;")

        self.btn_prev = PushButton("< 上一页")
        self.btn_prev.setFixedWidth(100)
        self.btn_prev.clicked.connect(self._prev_page)

        self.btn_next = PushButton("下一页 >")
        self.btn_next.setFixedWidth(100)
        self.btn_next.clicked.connect(self._next_page)

        pbar.addStretch()
        pbar.addWidget(self.btn_prev)
        pbar.addWidget(self.pag_label)
        pbar.addWidget(self.btn_next)
        pbar.addStretch()
        return pbar

    # ---- Data Loading ----

    def refresh_data(self):
        if not self.api.base_url:
            return
        self._load_page(self._current_page)
        self._load_groups()

    def showEvent(self, event):
        super().showEvent(event)
        if self.api.base_url:
            self._load_page(self._current_page)
            self._load_groups()

    def _load_page(self, page: int):
        name = self.search_input.text().strip()
        c = ApiCaller()
        c.finished.connect(self._on_list_result)
        c.error.connect(lambda e: InfoBar.error("获取浏览器列表失败", e, parent=self))
        c.run(self.api.browser_list, page, PAGE_SIZE, None, name or None)

    def _load_groups(self):
        c = ApiCaller()
        c.finished.connect(self._on_groups_result)
        c.error.connect(lambda e: logger.warning("获取分组失败: %s", e))
        c.run(self.api.group_list, 0, 200)

    def _on_list_result(self, data: dict):
        rows = extract_rows(data)
        self._total_count = extract_total(data, len(rows))
        self._browsers = [BrowserItem.from_api_dict(r) for r in rows]

        self._update_table()
        self._update_pagination()

    def _on_groups_result(self, data: dict):
        rows = extract_rows(data) if isinstance(data, dict) else []
        self._groups = [
            GroupItem(id=g["id"], name=g["groupName"], sort=g.get("sortNum", 0))
            for g in rows
        ]

    def _update_table(self):
        self._model.removeRows(0, self._model.rowCount())
        self._header.set_checked(False)
        for b in self._browsers:
            items = [
                QStandardItem(),
                QStandardItem(str(b.seq)),
                QStandardItem(b.name),
                QStandardItem(b.group_name),
                QStandardItem(short_str(b.platform, 30)),
                QStandardItem(short_str(b.remark, 40)),
                QStandardItem(proxy_type_label(b.proxy_type)),
                QStandardItem("●"),
            ]
            items[COL_SELECT].setCheckable(True)
            items[COL_SELECT].setCheckState(Qt.Unchecked)
            items[COL_NAME].setData(b.id, Qt.UserRole)
            for item in items:
                item.setEditable(False)
            items[COL_STATUS].setData(b.status, Qt.UserRole)

            self._model.appendRow(items)

    def _update_pagination(self):
        total_pages = max(1, (self._total_count + PAGE_SIZE - 1) // PAGE_SIZE)
        self._total_pages = total_pages
        self.pag_label.setText(
            f"第 {self._current_page + 1}/{total_pages} 页  共 {self._total_count} 条"
        )
        self.btn_prev.setEnabled(self._current_page > 0)
        self.btn_next.setEnabled(self._current_page + 1 < total_pages)

    # ---- Selection Helpers ----

    def _selected_ids(self) -> list[str]:
        ids = []
        for row in range(self._model.rowCount()):
            item = self._model.item(row, COL_SELECT)
            if item and item.checkState() == Qt.Checked:
                bid = self._model.item(row, COL_NAME).data(Qt.UserRole)
                if bid:
                    ids.append(bid)
        return ids

    def _selected_browser(self) -> BrowserItem | None:
        # 优先使用当前选中行
        idx = self.table.currentIndex()
        if idx.isValid() and 0 <= idx.row() < len(self._browsers):
            return self._browsers[idx.row()]
        # 如果只勾了一行 checkbox，用那个
        ids = self._selected_ids()
        if len(ids) == 1:
            for b in self._browsers:
                if b.id == ids[0]:
                    return b
        return None

    # ---- Actions ----

    def _add_browser(self):
        dlg = BrowserEditDialog(self.api, self, groups=self._groups)
        if dlg.exec():
            data = dlg.get_data()
            if not data.get("name"):
                InfoBar.warning("提示", "名称不能为空", parent=self)
                return
            c = ApiCaller()
            c.finished.connect(lambda _: self.refresh_data())
            c.error.connect(lambda e: InfoBar.error("创建失败", e, parent=self))
            c.run(self.api.browser_update, data)

    def _edit_browser(self):
        browser = self._selected_browser()
        if not browser:
            InfoBar.warning("提示", "请先选择一个浏览器", parent=self)
            return
        # Load full detail
        c = ApiCaller()
        c.finished.connect(self._on_detail_for_edit)
        c.error.connect(lambda e: InfoBar.error("获取详情失败", e, parent=self))
        c.run(self.api.browser_detail, browser.id)

    def _on_detail_for_edit(self, data: dict):
        dlg = BrowserEditDialog(self.api, self, browser_data=data, groups=self._groups)
        if dlg.exec():
            edit_data = dlg.get_data()
            edit_data["id"] = data.get("id", "")
            c = ApiCaller()
            c.finished.connect(lambda _: self.refresh_data())
            c.error.connect(lambda e: InfoBar.error("保存失败", e, parent=self))
            c.run(self.api.browser_update, edit_data)

    def _open_browser(self):
        ids = self._selected_ids()
        if not ids:
            browser = self._selected_browser()
            if browser:
                ids = [browser.id]
        if not ids:
            InfoBar.warning("提示", "请先选择至少一个浏览器", parent=self)
            return
        self.btn_open.setEnabled(False)
        self._open_pending = list(ids)
        self._open_next()

    def _open_next(self):
        if not self._open_pending:
            self.btn_open.setEnabled(True)
            self.refresh_data()
            return
        bid = self._open_pending.pop(0)
        c = ApiCaller()
        c.finished.connect(lambda data, bid=bid: self._on_open_result(data, bid))
        c.error.connect(self._on_open_error)
        c.run(self.api.browser_open, bid)

    def _on_open_error(self, msg: str):
        if "管理员" in msg:
            self._offer_admin_restart()
            self._open_pending.clear()
            QTimer.singleShot(5000, lambda: self.btn_open.setEnabled(True))
        else:
            InfoBar.error("打开失败", msg, parent=self)
            self._open_next()

    def _offer_admin_restart(self):
        InfoBar.warning(
            "需要管理员权限",
            "右键比特浏览器图标 → 以管理员身份运行，然后重试打开",
            duration=10000,
            parent=self,
        )

    def _on_open_result(self, data: dict, bid: str):
        if not isinstance(data, dict):
            data = {}
        for b in self._browsers:
            if b.id == bid:
                b.status = STATUS_OPEN
                b.ws_url = data.get("ws", "")
                b.http_url = data.get("http", "")
                b.driver_path = data.get("driver", "")
                break
        ws = data.get("ws", "")
        if ws:
            QApplication.clipboard().setText(ws)
        # 继续打开队列中的下一个
        self._open_next()

    def _close_browser(self):
        ids = self._selected_ids()
        if not ids:
            browser = self._selected_browser()
            if browser:
                ids = [browser.id]
        if not ids:
            InfoBar.warning("提示", "请先选择至少一个浏览器", parent=self)
            return
        self.btn_close.setEnabled(False)
        self._close_pending = list(ids)
        self._close_next()

    def _close_next(self):
        if not self._close_pending:
            self.btn_close.setEnabled(True)
            self.refresh_data()
            return
        bid = self._close_pending.pop(0)
        c = ApiCaller()
        c.finished.connect(lambda _, bid=bid: self._on_close_result(bid))
        c.error.connect(self._on_close_error)
        c.run(self.api.browser_close, bid)

    def _on_close_error(self, msg: str):
        InfoBar.error("关闭失败", msg, parent=self)
        self._close_next()

    def _on_close_result(self, bid: str):
        for b in self._browsers:
            if b.id == bid:
                b.status = STATUS_CLOSED
                break
        InfoBar.success("浏览器已关闭", "", parent=self)
        self._close_next()

    def _delete_browser(self):
        ids = self._selected_ids()
        if not ids:
            browser = self._selected_browser()
            if browser:
                ids = [browser.id]
        if not ids:
            InfoBar.warning("提示", "请先选择要删除的浏览器", parent=self)
            return

        msg = MessageBox(
            "确认删除",
            f"确定要删除选中的 {len(ids)} 个浏览器窗口吗？\n此操作不可恢复。",
            self,
        )
        if msg.exec():
            if len(ids) > 1:
                c = ApiCaller()
                c.finished.connect(lambda _: self.refresh_data())
                c.error.connect(lambda e: InfoBar.error("删除失败", e, parent=self))
                c.run(self.api.browser_delete_ids, ids)
            else:
                c = ApiCaller()
                c.finished.connect(lambda _: self.refresh_data())
                c.error.connect(lambda e: InfoBar.error("删除失败", e, parent=self))
                c.run(self.api.browser_delete, ids[0])

    # ---- Batch ----

    def _batch_change_group(self):
        ids = self._selected_ids()
        if not ids:
            InfoBar.warning("提示", "请先勾选要操作的浏览器", parent=self)
            return
        if not self._groups:
            InfoBar.warning("提示", "暂无分组数据，请先在分组页创建", parent=self)
            return

        dlg = Dialog("批量改分组", f"已选 {len(ids)} 个浏览器，请选择目标分组：", self)
        combo = ComboBox(dlg)
        for g in self._groups:
            combo.addItem(g.name, g.id)
        dlg.yesButton.setText("确定")
        dlg.cancelButton.setText("取消")
        dlg.vBoxLayout.insertWidget(2, combo)

        if dlg.exec():
            gid = combo.currentData()
            if not gid:
                InfoBar.warning("提示", "请选择分组", parent=self)
                return
            c = ApiCaller()
            c.finished.connect(lambda _: self.refresh_data())
            c.error.connect(lambda e: InfoBar.error("操作失败", e, parent=self))
            c.run(self.api.browser_batch_group, gid, ids)

    def _batch_proxy(self):
        ids = self._selected_ids()
        if not ids:
            InfoBar.warning("提示", "请先勾选要操作的浏览器", parent=self)
            return

        dlg = BatchProxyDialog(len(ids), self)
        if dlg.exec():
            proxy = dlg.get_data()
            c = ApiCaller()
            c.finished.connect(lambda _: self.refresh_data())
            c.error.connect(lambda e: InfoBar.error("修改代理失败", e, parent=self))
            c.run(self.api.browser_batch_proxy, ids, proxy)

    def _batch_remark(self):
        ids = self._selected_ids()
        if not ids:
            InfoBar.warning("提示", "请先勾选要操作的浏览器", parent=self)
            return

        dlg = Dialog("批量改备注", f"已选 {len(ids)} 个浏览器，输入新备注：", self)
        remark_input = LineEdit(dlg)
        remark_input.setPlaceholderText("备注内容")
        dlg.vBoxLayout.insertWidget(2, remark_input)
        dlg.yesButton.setText("确定")
        dlg.cancelButton.setText("取消")

        if dlg.exec():
            remark = remark_input.text().strip()
            if not remark:
                InfoBar.warning("提示", "备注不能为空", parent=self)
                return
            c = ApiCaller()
            c.finished.connect(lambda _: self.refresh_data())
            c.error.connect(lambda e: InfoBar.error("修改备注失败", e, parent=self))
            c.run(self.api.browser_batch_remark, ids, remark)

    def _arrange_windows(self):
        ids = self._selected_ids()
        if not ids:
            InfoBar.warning("提示", "请先勾选要排列的浏览器", parent=self)
            return
        dlg = LayoutDialog(self, selected_ids=ids or None)
        if dlg.exec():
            layout_data = dlg.get_data()
            c = ApiCaller()
            c.finished.connect(lambda _: InfoBar.success("已应用", "窗口排列已应用", parent=self))
            c.error.connect(lambda e: InfoBar.error("排列失败", e, parent=self))
            c.run(self.api.window_bounds, layout_data)

    # ---- Context Menu Copy ----

    def _copy_ws_url(self):
        browser = self._selected_browser()
        if not browser or not browser.ws_url:
            InfoBar.warning("提示", "浏览器未打开或无 WS 地址", parent=self)
            return
        QApplication.clipboard().setText(browser.ws_url)
        InfoBar.success("已复制", "WS 地址已复制到剪贴板", parent=self)

    def _copy_driver_path(self):
        browser = self._selected_browser()
        if not browser or not browser.driver_path:
            InfoBar.warning("提示", "浏览器未打开或无 chromedriver 路径", parent=self)
            return
        QApplication.clipboard().setText(browser.driver_path)
        InfoBar.success("已复制", "chromedriver 路径已复制到剪贴板", parent=self)

    def _copy_http_url(self):
        browser = self._selected_browser()
        if not browser or not browser.http_url:
            InfoBar.warning("提示", "浏览器未打开或无 HTTP 地址", parent=self)
            return
        QApplication.clipboard().setText(browser.http_url)
        InfoBar.success("已复制", "HTTP 地址已复制到剪贴板", parent=self)

    # ---- Navigation ----

    def _search(self):
        self._current_page = 0
        self._load_page(0)

    def _prev_page(self):
        if self._current_page > 0:
            self._current_page -= 1
            self._load_page(self._current_page)

    def _next_page(self):
        if self._current_page + 1 < self._total_pages:
            self._current_page += 1
            self._load_page(self._current_page)

    # ---- Status Monitor Integration ----

    def update_alive_status(self, alive_ids: set[str]):
        """由 StatusMonitor 调用，更新浏览器在线状态"""
        for row, b in enumerate(self._browsers):
            new_status = STATUS_OPEN if b.id in alive_ids else STATUS_CLOSED
            if b.status != new_status:
                b.status = new_status
                status_item = self._model.item(row, COL_STATUS)
                if status_item:
                    status_item.setData(b.status, Qt.UserRole)
