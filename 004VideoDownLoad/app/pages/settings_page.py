"""设置页面 - 重新设计"""
import os
import shutil
import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog,
    QFrame, QCheckBox, QScrollArea,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from qfluentwidgets import (
    LineEdit, PushButton, ComboBox,
    SpinBox, FluentIcon as FIF,
)


class SettingsPage(QWidget):
    """设置页面"""

    def __init__(self, settings_manager=None, parent=None):
        super().__init__(parent)
        self._settings = settings_manager
        self.setStyleSheet('background: #FFFFFF;')
        self._setup_ui()

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet('QScrollArea { border: none; background: #FFFFFF; }')

        content = QWidget()
        content.setStyleSheet('background: #FFFFFF;')
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        title = QLabel('设置')
        title.setFont(QFont('Microsoft YaHei', 18, QFont.Bold))
        title.setStyleSheet('color: #1a1a1a; border: none;')
        layout.addWidget(title)

        layout.addWidget(self._section('下载设置', self._download_settings()))
        layout.addWidget(self._section('文件命名', self._naming_settings()))
        layout.addWidget(self._section('其他设置', self._other_settings()))
        layout.addWidget(self._section('网络设置', self._network_settings()))
        layout.addWidget(self._section('下载统计', self._stats_settings()))
        layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _section(self, title: str, body: QWidget) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            'QFrame { background: #FAFBFC; border: 1px solid #E8ECF0; border-radius: 10px; }'
        )
        cl = QVBoxLayout(card)
        cl.setContentsMargins(20, 16, 20, 16)
        cl.setSpacing(10)

        header = QLabel(title)
        header.setFont(QFont('Microsoft YaHei', 13, QFont.Bold))
        header.setStyleSheet('border: none; background: transparent;')
        cl.addWidget(header)
        cl.addWidget(body)
        return card

    def _row(self, label_text: str, *widgets) -> QWidget:
        w = QWidget()
        w.setStyleSheet('border: none; background: transparent;')
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        lbl = QLabel(label_text)
        lbl.setStyleSheet('color: #444; font-size: 13px; border: none; min-width: 100px;')
        lbl.setFixedHeight(32)
        row.addWidget(lbl)
        for wgt in widgets:
            row.addWidget(wgt)
        row.addStretch()
        return w

    def _download_settings(self):
        w = QWidget()
        w.setStyleSheet('border: none; background: transparent;')
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 保存路径
        self.path_input = LineEdit()
        self.path_input.setReadOnly(True)
        self.path_input.setMinimumHeight(34)
        self.path_input.setMaximumHeight(34)
        browse_btn = PushButton('浏览')
        browse_btn.setMinimumHeight(34)
        browse_btn.clicked.connect(self._browse_path)
        path_row = QWidget()
        path_row.setStyleSheet('border: none; background: transparent;')
        pr = QHBoxLayout(path_row)
        pr.setContentsMargins(0, 0, 0, 0)
        pr.setSpacing(8)
        pr.addWidget(self.path_input, stretch=1)
        pr.addWidget(browse_btn)
        layout.addWidget(self._row('保存路径', path_row))

        # 并发
        self.concurrent_spin = SpinBox()
        self.concurrent_spin.setRange(1, 5)
        self.concurrent_spin.setValue(3)
        self.concurrent_spin.valueChanged.connect(lambda v: self._settings.set('download.max_concurrent', v))
        layout.addWidget(self._row('同时下载', self.concurrent_spin))

        # 限速
        self.speed_combo = ComboBox()
        self.speed_combo.addItems(['不限', '1 MB/s', '2 MB/s', '5 MB/s'])
        self.speed_combo.currentTextChanged.connect(self._on_speed)
        layout.addWidget(self._row('下载限速', self.speed_combo))

        # 自动重试
        self.auto_retry_cb = QCheckBox('失败自动重试')
        self.auto_retry_cb.toggled.connect(lambda v: self._settings.set('download.auto_retry', v))
        self.retry_spin = SpinBox()
        self.retry_spin.setRange(1, 10)
        self.retry_spin.setValue(3)
        self.retry_spin.valueChanged.connect(lambda v: self._settings.set('download.retry_count', v))
        retry_lbl = QLabel('重试次数:')
        retry_lbl.setStyleSheet('color: #444; font-size: 13px; border: none;')
        layout.addWidget(self._row('', self.auto_retry_cb, retry_lbl, self.retry_spin))

        return w

    def _naming_settings(self):
        w = QWidget()
        w.setStyleSheet('border: none; background: transparent;')
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.template_input = LineEdit()
        self.template_input.setPlaceholderText('{platform}_{title}_{date}')
        self.template_input.setMinimumHeight(36)
        self.template_input.setMaximumHeight(36)
        self.template_input.textChanged.connect(self._on_template)
        layout.addWidget(self._row('命名模板', self.template_input))

        # 变量说明区域
        vars_frame = QFrame()
        vars_frame.setStyleSheet('QFrame { background: #F5F7FA; border: 1px solid #E8ECF0; border-radius: 8px; }')
        vars_layout = QVBoxLayout(vars_frame)
        vars_layout.setContentsMargins(14, 10, 14, 10)
        vars_layout.setSpacing(6)

        vars_title = QLabel('可用变量（在模板中使用花括号包裹，如 {title}）：')
        vars_title.setStyleSheet('color: #555; font-size: 12px; font-weight: bold; border: none;')
        vars_layout.addWidget(vars_title)

        variables = [
            ('{title}', '视频标题，由解析结果决定'),
            ('{platform}', '平台名称（douyin / kuaishou / bilibili / youtube 等）'),
            ('{format}', '视频格式（mp4 / mov / flv 等）'),
            ('{id}', '平台视频ID（链接解析后获得）'),
            ('{date}', '下载日期，如 20260509'),
            ('{time}', '下载时间，如 143025'),
        ]

        vars_grid = QVBoxLayout()
        vars_grid.setSpacing(3)
        for var, desc in variables:
            row = QHBoxLayout()
            row.setSpacing(8)
            var_lbl = QLabel(var)
            var_lbl.setStyleSheet(
                'color: #0078D4; font-size: 12px; font-weight: bold;'
                'background: #E8F4FD; border-radius: 3px; padding: 1px 6px; border: none;'
            )
            var_lbl.setFixedWidth(85)
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet('color: #666; font-size: 12px; border: none;')
            row.addWidget(var_lbl)
            row.addWidget(desc_lbl)
            row.addStretch()
            vars_grid.addLayout(row)

        vars_layout.addLayout(vars_grid)
        layout.addWidget(vars_frame)

        # 实时预览
        preview_frame = QFrame()
        preview_frame.setStyleSheet('QFrame { background: #F0F7FF; border: 1px solid #B8D8F0; border-radius: 8px; }')
        preview_layout = QHBoxLayout(preview_frame)
        preview_layout.setContentsMargins(14, 10, 14, 10)
        preview_layout.setSpacing(6)

        preview_hint = QLabel('实时预览：')
        preview_hint.setStyleSheet('color: #555; font-size: 13px; border: none;')
        preview_layout.addWidget(preview_hint)

        self.naming_preview = QLabel()
        self.naming_preview.setStyleSheet('color: #0078D4; font-size: 13px; font-weight: bold; border: none;')
        preview_layout.addWidget(self.naming_preview)
        preview_layout.addStretch()
        layout.addWidget(preview_frame)

        self.sub_platform_cb = QCheckBox('按平台创建子文件夹（抖音视频/快手视频）')
        self.sub_platform_cb.toggled.connect(lambda v: self._settings.set('naming.sub_by_platform', v))
        layout.addWidget(self.sub_platform_cb)

        self.sub_date_cb = QCheckBox('按日期创建子文件夹（YYYY-MM-DD）')
        self.sub_date_cb.toggled.connect(lambda v: self._settings.set('naming.sub_by_date', v))
        layout.addWidget(self.sub_date_cb)

        return w

    def _other_settings(self):
        w = QWidget()
        w.setStyleSheet('border: none; background: transparent;')
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.notify_cb = QCheckBox('下载完成后系统通知')
        self.notify_cb.toggled.connect(lambda v: self._settings.set('download.notify_complete', v))
        layout.addWidget(self.notify_cb)

        self.open_folder_cb = QCheckBox('下载完成后自动打开文件夹')
        self.open_folder_cb.toggled.connect(lambda v: self._settings.set('download.open_folder_after_done', v))
        layout.addWidget(self.open_folder_cb)

        self.min_tray_cb = QCheckBox('关闭窗口最小化到系统托盘')
        self.min_tray_cb.setChecked(True)
        self.min_tray_cb.toggled.connect(lambda v: self._settings.set('general.minimize_to_tray', v))
        layout.addWidget(self.min_tray_cb)

        return w

    def _network_settings(self):
        w = QWidget()
        w.setStyleSheet('border: none; background: transparent;')
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.proxy_combo = ComboBox()
        self.proxy_combo.addItems(['系统代理', '无代理', '自定义'])
        self.proxy_combo.setCurrentText(
            {'system': '系统代理', 'none': '无代理', 'custom': '自定义'}.get(
                self._settings.get('network.proxy_mode', 'system'), '系统代理'))
        self.proxy_combo.currentTextChanged.connect(self._on_proxy_mode)
        layout.addWidget(self._row('代理模式', self.proxy_combo))

        self.proxy_input = LineEdit()
        self.proxy_input.setPlaceholderText('http://127.0.0.1:7890')
        self.proxy_input.setMinimumHeight(34)
        self.proxy_input.setMaximumHeight(34)
        self.proxy_input.setText(self._settings.get('network.proxy_url', ''))
        self.proxy_input.textChanged.connect(self._on_proxy_url)
        self._proxy_row = self._row('代理地址', self.proxy_input)
        layout.addWidget(self._proxy_row)

        is_custom = self._settings.get('network.proxy_mode', 'system') == 'custom'
        self._proxy_row.setVisible(is_custom)

        return w

    def _on_proxy_mode(self, text):
        mode_map = {'系统代理': 'system', '无代理': 'none', '自定义': 'custom'}
        mode = mode_map.get(text, 'system')
        self._settings.set('network.proxy_mode', mode)
        is_custom = mode == 'custom'
        if hasattr(self, '_proxy_row'):
            self._proxy_row.setVisible(is_custom)
        self._notify_proxy_change()

    def _on_proxy_url(self, url):
        self._settings.set('network.proxy_url', url)
        self._notify_proxy_change()

    def _notify_proxy_change(self):
        try:
            win = self.window()
            if win and hasattr(win, 'task_mgr'):
                win.task_mgr.update_proxy()
        except Exception:
            pass

    def _stats_settings(self):
        w = QWidget()
        w.setStyleSheet('border: none; background: transparent;')
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.stats_label = QLabel()
        self.stats_label.setStyleSheet('color: #444; font-size: 13px; border: none;')
        self.stats_label.setMinimumHeight(20)
        layout.addWidget(self.stats_label)

        self.disk_label = QLabel()
        self.disk_label.setStyleSheet('color: #888; font-size: 13px; border: none;')
        self.disk_label.setMinimumHeight(20)
        layout.addWidget(self.disk_label)

        return w

    # ── 事件 ──

    def _browse_path(self):
        path = QFileDialog.getExistingDirectory(self, '选择保存路径', self.path_input.text())
        if path:
            self.path_input.setText(path)
            self._settings.set('download.save_path', path)

    def _on_speed(self, text):
        m = {'不限': 0, '1 MB/s': 1024, '2 MB/s': 2048, '5 MB/s': 5120}
        self._settings.set('download.speed_limit', m.get(text, 0))

    def _on_template(self, text):
        if self._settings:
            self._settings.set('naming.template', text)
        self._update_preview()

    def _update_preview(self):
        tmpl = self.template_input.text() or '{platform}_{title}_{date}'
        now = datetime.datetime.now()
        prev = tmpl
        prev = prev.replace('{title}', '视频标题')
        prev = prev.replace('{platform}', 'douyin')
        prev = prev.replace('{format}', 'mp4')
        prev = prev.replace('{date}', now.strftime('%Y%m%d'))
        prev = prev.replace('{time}', now.strftime('%H%M%S'))
        prev = prev.replace('{id}', '7345129876')
        if hasattr(self, 'naming_preview'):
            self.naming_preview.setText(f'{prev}.mp4')

    def _update_stats(self):
        if not self._settings:
            return
        stats = self._settings.get('stats', {})
        total = stats.get('total_count', 0)
        today = stats.get('today_count', 0)
        ts = self._fmt(stats.get('total_size', 0))
        tds = self._fmt(stats.get('today_size', 0))
        self.stats_label.setText(f'今日下载: {today} 个 ({tds})  |  总计: {total} 个 ({ts})')
        try:
            usage = shutil.disk_usage(self._settings.save_path)
            free_gb = usage.free / (1024**3)
            self.disk_label.setText(f'磁盘剩余空间: {free_gb:.1f} GB')
        except Exception:
            self.disk_label.setText('磁盘剩余空间: 无法获取')

    def _fmt(self, b: int) -> str:
        if not b:
            return '0 B'
        if b < 1024 * 1024:
            return f'{b/1024:.0f} KB'
        elif b < 1024 * 1024 * 1024:
            return f'{b/(1024*1024):.1f} MB'
        return f'{b/(1024*1024*1024):.2f} GB'

    def refresh(self):
        if not self._settings:
            return
        self.path_input.setText(self._settings.save_path)
        self.concurrent_spin.setValue(self._settings.max_concurrent)
        spd = self._settings.get('download.speed_limit', 0)
        self.speed_combo.setCurrentText({0: '不限', 1024: '1 MB/s', 2048: '2 MB/s', 5120: '5 MB/s'}.get(spd, '不限'))
        self.template_input.setText(self._settings.naming_template)
        self.sub_platform_cb.setChecked(self._settings.sub_by_platform)
        self.sub_date_cb.setChecked(self._settings.sub_by_date)
        self.auto_retry_cb.setChecked(self._settings.get('download.auto_retry', True))
        self.retry_spin.setValue(self._settings.get('download.retry_count', 3))
        self.notify_cb.setChecked(self._settings.get('download.notify_complete', True))
        self.open_folder_cb.setChecked(self._settings.get('download.open_folder_after_done', False))
        self.min_tray_cb.setChecked(self._settings.get('general.minimize_to_tray', True))
        # 代理
        self.proxy_combo.setCurrentText(
            {'system': '系统代理', 'none': '无代理', 'custom': '自定义'}.get(
                self._settings.get('network.proxy_mode', 'system'), '系统代理'))
        self.proxy_input.setText(self._settings.get('network.proxy_url', ''))
        is_custom = self._settings.get('network.proxy_mode', 'system') == 'custom'
        if hasattr(self, '_proxy_row'):
            self._proxy_row.setVisible(is_custom)
        self._update_preview()
        self._update_stats()
