import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QAbstractTableModel, QModelIndex, QTimer
from PySide6.QtWidgets import QHeaderView, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QTableView, QFileDialog
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis, QDateTimeAxis
from qfluentwidgets import (
    ScrollArea, CardWidget, BodyLabel, StrongBodyLabel,
    PushButton, ProgressRing, ComboBox, SpinBox,
    InfoBar, InfoBarPosition, TogglePushButton,
)

from app.config import FREE_MODELS, MODEL_TYPE_NAMES, data_dir, settings_scope, SETTINGS_KEY_NOTIFY_THRESHOLD, short_model_name
from app.models import QuotaInfo, load_models_config
from app.modelscope_client import get_client
from ui.widgets.log_widget import LogWidget

logger = logging.getLogger(__name__)


class QuotaTableModel(QAbstractTableModel):
    HEADERS = ["模型名称", "模型类型", "总限额", "已用", "剩余", "剩余占比", "状态"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list[QuotaInfo] = []

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._data):
            return None

        quota = self._data[index.row()]
        col = index.column()

        if role == Qt.DisplayRole:
            if col == 0:
                return short_model_name(quota.model_id)
            elif col == 1:
                return quota.model_id.split("/")[0] if "/" in quota.model_id else "其他"
            elif col == 2:
                return str(quota.model_limit) if quota.model_limit > 0 else "共享"
            elif col == 3:
                return str(quota.model_used)
            elif col == 4:
                return str(quota.model_remaining)
            elif col == 5:
                return f"{quota.model_percent:.1f}%"
            elif col == 6:
                if quota.model_percent < 20:
                    return "紧张"
                elif quota.model_percent < 50:
                    return "正常"
                return "充足"

        if role == Qt.ForegroundRole and col == 6:
            if quota.model_percent < 20:
                return QColor("#FF5252")
            elif quota.model_percent < 50:
                return QColor("#FFAB40")
            return QColor("#4CAF50")

        return None

    def set_data(self, data: list[QuotaInfo]):
        self.beginResetModel()
        self._data = data
        self.endResetModel()

    def get_quota(self, row: int) -> QuotaInfo | None:
        if 0 <= row < len(self._data):
            return self._data[row]
        return None


class QuotaPage(ScrollArea):
    log_message = Signal(str, str)
    quota_updated = Signal(int, int)  # total, remaining

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("quotaPage")
        self._quota_history: list[dict] = []
        self._auto_refresh_timer = QTimer(self)
        self._auto_refresh_timer.timeout.connect(self._auto_refresh)
        self._init_ui()
        self._load_history()

    def _init_ui(self):
        container = QWidget()
        self.setWidget(container)
        self.setWidgetResizable(True)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Top controls
        control_layout = QHBoxLayout()
        control_layout.addWidget(StrongBodyLabel("额度概览"))
        control_layout.addStretch()

        # Auto refresh interval
        control_layout.addWidget(BodyLabel("自动刷新:"))
        self._refresh_interval = ComboBox()
        self._refresh_interval.addItems(["关闭", "1分钟", "5分钟", "15分钟"])
        self._refresh_interval.setFixedWidth(80)
        self._refresh_interval.setCurrentIndex(0)
        self._refresh_interval.currentIndexChanged.connect(self._on_refresh_interval_changed)
        control_layout.addWidget(self._refresh_interval)

        self._model_filter = ComboBox()
        self._model_filter.addItems(["全部模型", "大语言模型", "多模态模型", "图像模型"])
        self._model_filter.setFixedWidth(120)
        self._model_filter.currentIndexChanged.connect(self._on_filter_changed)
        control_layout.addWidget(self._model_filter)

        self._btn_export = PushButton("导出")
        self._btn_export.setFixedWidth(60)
        self._btn_export.clicked.connect(self._export_quota)
        control_layout.addWidget(self._btn_export)

        self._btn_refresh = PushButton("刷新额度")
        self._btn_refresh.setFixedWidth(100)
        self._btn_refresh.clicked.connect(self.refresh_quota)
        control_layout.addWidget(self._btn_refresh)

        layout.addLayout(control_layout)

        # Summary cards
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(16)

        self._total_card = self._create_stat_card("今日总限额", "2000")
        self._used_card = self._create_stat_card("已使用", "0")
        self._remaining_card = self._create_stat_card("剩余额度", "2000")
        self._reset_card = self._create_stat_card("重置时间", "00:00")

        cards_layout.addWidget(self._total_card)
        cards_layout.addWidget(self._used_card)
        cards_layout.addWidget(self._remaining_card)
        cards_layout.addWidget(self._reset_card)
        layout.addLayout(cards_layout)

        # Progress ring and trend chart
        ring_chart_layout = QHBoxLayout()

        # Progress ring
        ring_widget = QWidget()
        ring_layout = QVBoxLayout(ring_widget)
        ring_layout.setContentsMargins(0, 0, 0, 0)
        ring_layout.setSpacing(8)

        self._progress_ring = ProgressRing()
        self._progress_ring.setFixedSize(100, 100)
        self._progress_ring.setRange(0, 100)
        self._progress_ring.setValue(100)
        ring_layout.addWidget(self._progress_ring, alignment=Qt.AlignCenter)

        self._ring_label = BodyLabel("剩余 100%")
        self._ring_label.setAlignment(Qt.AlignCenter)
        ring_layout.addWidget(self._ring_label)

        ring_chart_layout.addWidget(ring_widget)

        # Trend chart
        trend_card = CardWidget()
        trend_layout = QVBoxLayout(trend_card)
        trend_layout.setContentsMargins(8, 8, 8, 8)

        trend_header = QHBoxLayout()
        trend_header.addWidget(BodyLabel("额度消耗趋势（近24小时）"))
        trend_header.addStretch()
        trend_layout.addLayout(trend_header)

        self._trend_chart = QChart()
        from PySide6.QtCore import QMargins
        self._trend_chart.setMargins(QMargins(0, 0, 0, 0))
        self._trend_chart.legend().setVisible(False)
        self._trend_series = QLineSeries()
        self._trend_series.setColor(QColor("#0078D4"))
        self._trend_chart.addSeries(self._trend_series)

        self._trend_axis_x = QDateTimeAxis()
        self._trend_axis_x.setFormat("HH:mm")
        self._trend_axis_x.setTitleText("时间")
        self._trend_chart.addAxis(self._trend_axis_x, Qt.AlignBottom)
        self._trend_series.attachAxis(self._trend_axis_x)

        self._trend_axis_y = QValueAxis()
        self._trend_axis_y.setRange(0, 2000)
        self._trend_axis_y.setTitleText("剩余额度")
        self._trend_chart.addAxis(self._trend_axis_y, Qt.AlignLeft)
        self._trend_series.attachAxis(self._trend_axis_y)

        self._chart_view = QChartView(self._trend_chart)
        self._chart_view.setFixedHeight(150)
        self._chart_view.setRenderHint(QPainter.Antialiasing)
        trend_layout.addWidget(self._chart_view)

        ring_chart_layout.addWidget(trend_card, 1)
        layout.addLayout(ring_chart_layout)

        # Quota table
        table_card = CardWidget()
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(8, 8, 8, 8)

        self._table = QTableView()
        self._model = QuotaTableModel()
        self._table.setModel(self._model)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(
            "QTableView { background-color: #FAFAFA; gridline-color: #E0E0E0; }"
        )
        table_layout.addWidget(self._table)

        layout.addWidget(table_card)

        # Log widget
        self._log_widget = LogWidget()
        layout.addWidget(self._log_widget)

    def _create_stat_card(self, title: str, value: str) -> CardWidget:
        card = CardWidget()
        layout = QGridLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)

        label = BodyLabel(title)
        value_label = StrongBodyLabel(value)
        value_label.setObjectName(f"{title}_value")

        layout.addWidget(label, 0, 0)
        layout.addWidget(value_label, 1, 0)

        return card

    def _on_refresh_interval_changed(self, index: int):
        intervals = [0, 60, 300, 900]  # seconds
        interval = intervals[index]
        if interval > 0:
            self._auto_refresh_timer.start(interval * 1000)
            self._log_widget.info(f"自动刷新已启用，间隔 {interval} 秒")
        else:
            self._auto_refresh_timer.stop()
            self._log_widget.info("自动刷新已关闭")

    def _auto_refresh(self):
        self.refresh_quota()

    def refresh_quota(self):
        self._btn_refresh.setEnabled(False)
        self._btn_refresh.setText("查询中...")

        async def _refresh():
            try:
                models = load_models_config()
                if not models:
                    model_ids = []
                    for model_type, ids in FREE_MODELS.items():
                        model_ids.extend(ids)
                else:
                    model_ids = [m.model_id for m in models if m.enabled]

                client = get_client()
                quotas = await client.batch_query_quota(model_ids[:10])

                quota_list = list(quotas.values())
                self._model.set_data(quota_list)

                # Update summary
                total_limit = sum(q.daily_limit for q in quota_list if q.daily_limit > 0)
                total_remaining = sum(q.daily_remaining for q in quota_list)
                if total_limit == 0:
                    total_limit = 2000

                self._update_summary(total_limit, total_remaining)
                self._save_history(total_remaining)
                self._check_warning(quota_list)
                self._log_widget.info(f"已刷新 {len(quota_list)} 个模型的额度")

                self.quota_updated.emit(total_limit, total_remaining)

            except Exception as e:
                logger.exception("刷新额度失败")
                self._log_widget.error(f"刷新额度失败: {e}")
                InfoBar.error(
                    "查询失败",
                    str(e),
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
            finally:
                self._btn_refresh.setEnabled(True)
                self._btn_refresh.setText("刷新额度")

        asyncio.ensure_future(_refresh())

    def _update_summary(self, total: int, remaining: int):
        used = total - remaining
        percent = (remaining / total * 100) if total > 0 else 0

        self._total_card.findChild(StrongBodyLabel).setText(str(total))
        self._used_card.findChild(StrongBodyLabel).setText(str(used))
        self._remaining_card.findChild(StrongBodyLabel).setText(str(remaining))

        self._progress_ring.setValue(int(percent))
        self._ring_label.setText(f"剩余 {percent:.0f}%")

        now = datetime.now()
        reset_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if reset_time < now:
            reset_time += timedelta(days=1)
        self._reset_card.findChild(StrongBodyLabel).setText(
            reset_time.strftime("%H:%M")
        )

        # Update trend chart
        self._update_trend_chart(remaining)

    def _update_trend_chart(self, current_remaining: int):
        """Update the trend chart with historical data."""
        from PySide6.QtCore import QDateTime

        self._trend_series.clear()

        # Load history
        history_file = data_dir() / "quota_history.json"
        if history_file.exists():
            try:
                history = json.loads(history_file.read_text(encoding="utf-8"))
                # Get today's data
                today = datetime.now().strftime("%Y-%m-%d")
                today_data = None
                for entry in history:
                    if entry.get("date") == today:
                        today_data = entry.get("hourly", {})
                        break

                if today_data:
                    # Add points for each hour with data
                    now = datetime.now()
                    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

                    for hour_str, remaining in sorted(today_data.items(), key=lambda x: int(x[0])):
                        hour = int(hour_str)
                        dt = start_of_day + timedelta(hours=hour)
                        timestamp = QDateTime(dt)
                        self._trend_series.append(timestamp.toMSecsSinceEpoch(), remaining)

                    # Add current point
                    self._trend_series.append(QDateTime.currentDateTime().toMSecsSinceEpoch(), current_remaining)

                    # Set axis range
                    self._trend_axis_y.setRange(0, max(2000, current_remaining + 200))
                    self._trend_axis_x.setRange(
                        QDateTime(start_of_day),
                        QDateTime(start_of_day + timedelta(hours=24))
                    )

            except Exception as e:
                logger.warning(f"Failed to update trend chart: {e}")
        else:
            # Just show current point
            self._trend_series.append(QDateTime.currentDateTime().toMSecsSinceEpoch(), current_remaining)

    def _check_warning(self, quota_list: list[QuotaInfo]):
        """Check if any model is below threshold and show notification."""
        from app.config import SETTINGS_KEY_NOTIFY_ENABLED

        s = settings_scope()
        threshold = int(s.value(SETTINGS_KEY_NOTIFY_THRESHOLD, 20))
        notify_enabled = s.value(SETTINGS_KEY_NOTIFY_ENABLED, "true").lower() != "false"

        warnings = []
        for quota in quota_list:
            if quota.model_limit > 0 and quota.model_percent < threshold:
                warnings.append(f"{short_model_name(quota.model_id)}: {quota.model_percent:.1f}%")

        if warnings:
            msg = f"以下模型额度紧张: {', '.join(warnings[:3])}"
            self._log_widget.warning(msg)
            InfoBar.warning(
                "额度预警",
                msg,
                duration=5000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            # Send desktop notification via system tray
            if notify_enabled:
                self._send_desktop_notification("额度预警", msg)

    def _send_desktop_notification(self, title: str, message: str):
        """Send desktop notification via system tray."""
        try:
            main_window = self.window()
            tray = getattr(main_window, "_tray", None)
            if tray is not None:
                from PySide6.QtWidgets import QSystemTrayIcon
                tray.showMessage(
                    title, message,
                    QSystemTrayIcon.Warning,
                    5000,
                )
        except Exception:
            pass

    def _save_history(self, remaining: int):
        """Save quota history for trend analysis."""
        history_file = data_dir() / "quota_history.json"
        try:
            if history_file.exists():
                history = json.loads(history_file.read_text(encoding="utf-8"))
            else:
                history = []

            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            hour = now.hour

            # Update or add entry
            found = False
            for entry in history:
                if entry.get("date") == today:
                    entry["hourly"][str(hour)] = remaining
                    found = True
                    break

            if not found:
                history.append({
                    "date": today,
                    "hourly": {str(hour): remaining}
                })

            # Keep only last 7 days
            if len(history) > 7:
                history = history[-7:]

            history_file.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
            self._quota_history = history

        except Exception as e:
            logger.warning(f"Failed to save quota history: {e}")

    def _load_history(self):
        """Load quota history from file."""
        history_file = data_dir() / "quota_history.json"
        if history_file.exists():
            try:
                self._quota_history = json.loads(history_file.read_text(encoding="utf-8"))
            except Exception:
                self._quota_history = []

    def _export_quota(self):
        """Export quota data to file."""
        path, _ = QFileDialog.getSaveFileName(
            self, "导出额度数据", "quota_export.json",
            "JSON Files (*.json);;CSV Files (*.csv)"
        )
        if not path:
            return

        try:
            quota_list = []
            for row in range(self._model.rowCount()):
                quota = self._model.get_quota(row)
                if quota:
                    quota_list.append(quota.to_dict())

            if path.endswith(".csv"):
                import csv
                with open(path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.DictWriter(f, fieldnames=["model_id", "daily_limit", "daily_remaining", "model_limit", "model_remaining"])
                    writer.writeheader()
                    writer.writerows(quota_list)
            else:
                Path(path).write_text(json.dumps(quota_list, ensure_ascii=False, indent=2), encoding="utf-8")

            InfoBar.success("导出成功", f"已导出到 {path}", parent=self)
            self._log_widget.info(f"额度数据已导出: {path}")

        except Exception as e:
            InfoBar.error("导出失败", str(e), parent=self)
            self._log_widget.error(f"导出失败: {e}")

    def _on_filter_changed(self, index: int):
        self.refresh_quota()