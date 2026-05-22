"""自定义 Widget 组件"""
import os
import re
import time
import json
import zipfile
import tempfile
import logging
from io import BytesIO
from typing import Optional, Callable

from PySide6.QtCore import (
    Qt, QTimer, QSize, QRect, Signal, QPropertyAnimation, QEasingCurve,
    QParallelAnimationGroup, QPoint, QEvent, QUrl,
)
from PySide6.QtGui import (
    QFont, QColor, QPainter, QPixmap, QIcon, QAction, QCursor,
    QDesktopServices, QFontDatabase,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit,
    QLineEdit, QComboBox, QScrollArea, QFrame, QGridLayout, QCheckBox,
    QProgressBar, QApplication, QDialog, QFileDialog, QMessageBox,
    QSizePolicy, QSpacerItem, QGroupBox, QLayout, QStyle, QStyleOption,
    QSplitter, QListWidget, QListWidgetItem, QTextBrowser, QDialogButtonBox,
    QPlainTextEdit, QMainWindow, QMenu,
)

from .style import COLORS
from .api import ApiClient, ApiError, ApiConfig, is_recaptcha_error, build_model_with_ratio, is_flow2api_style

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════════

MALE_KEYWORDS = [
    "男", "父", "老爷", "叔", "伯", "舅", "爷", "公", "哥", "弟",
    "先生", "男主", "少年", "男性", "男子", "丈夫", "儿子", "男孩",
]

API_PRESETS = {
    "localhost": {
        "apiBase": "http://localhost:8000",
        "apiKey": "han1234",
        "modelSelect": "gemini-3.1-flash-image",  # base name, ratio suffix added at call time
        "ratio": "square",
        "label": "localhost:8000",
    },
    "geeknow": {
        "apiBase": "https://api.geeknow.top",
        "apiKey": "sk-MuEiwKWLDIpAX68VCmxcZV6cwuHHQR102Qke5P6xKFgYOmRT",
        "modelSelect": "gemini-3-pro-image-preview",
        "ratio": "square",
        "label": "geeknow",
    },
}

MODEL_OPTIONS = [
    "gemini-3.1-flash-image",
    "gemini-3.0-pro-image",
    "gemini-3-pro-image-preview",
    "gemini-2.5-flash-image",
]

DEFAULT_JSON = """[
  {
    "name": "苏晚(主角)",
    "aliases": "苏小姐, 晚晚, 晚姨",
    "description": "一个28岁的职场女性，气质温婉且自带文人气息。她留着一头柔顺的黑色中长发，五官清秀且目光平和，肤色白皙，双手洁净且指甲修整得圆润自然。她身穿一件米白色垂感真丝飘带衬衫，搭配燕麦色高腰垂感西装裤，脚踩一双简约的白色平底皮鞋。整体穿搭干练而不失柔美，散发出一种从容踏实的生活质感。"
  },
  {
    "name": "沈屹(男主角)",
    "aliases": "老沈",
    "description": "一个38岁的宽厚男人，年近四十却骨架结实、极具张力，留着利落且干净的黑色寸头。他拥有健康的深小麦色皮肤，长相周正，笑起来时会露出两个深深的梨窝和整齐洁白的牙齿，眼睫毛浓密，眼尾带有自然的微扬弧度。他身穿一件深藏青色连帽卫衣搭配黑色耐磨工装裤，脚蹬一双灰黑色的机能风运动鞋。虽然常年饱经风霜，但神情温和憨厚，透着一股能撑起家庭的踏实感。"
  },
  {
    "name": "沈星辞(少年态)",
    "aliases": "星辞",
    "description": "一个15岁的青春期少年，拥有极具欺骗性的冷白皮和清冽出众的五官，长相精致如画中人。他留着略遮眼帘的黑色细碎短发，瞳孔漆黑如墨，睫毛又长又密，气质清冷而倔强。他身穿一件整洁的白色纯棉T恤搭配灰色机能风短裤，脚踩一双洁白的帆布鞋。虽然骨架略显少年人的纤细，但身姿挺拔，站立时带着一种超越年龄的成熟与克制。"
  },
  {
    "name": "沈星辞(成年态)",
    "aliases": "小星辞",
    "description": "一个22岁左右的年轻男子，身材高大挺拔，由于长期的电气工程专业学习，气质更显严谨稳重。他留着利落的短碎发，五官褪去了少年的青涩，眉眼愈发深邃冷峻。他身穿一件炭灰色高领羊绒衫，搭配黑色修身牛仔裤和深色荔枝纹牛皮靴，腕间戴着一只极简风格的机械表。整体形象清冷贵气，唯有在面对家人时，眼神中才会泛起温柔的涟漪。"
  },
  {
    "name": "表姐(配角)",
    "aliases": "媒人",
    "description": "一个30岁出头的现代女性，面相亲和且富有活力，言谈举止间带着几分职场女性的干练与热络。她留着一头栗色大波浪长卷发，妆容精致。她身穿一件勃艮第红的双排扣戗驳领西装外套，内搭米色针织衫，下身穿着利落的黑色直筒裤，佩戴一副时尚的金丝眼镜，看起来既精明能干又热衷于社交。"
  },
  {
    "name": "沈星辞外公(反派配角)",
    "aliases": "外公",
    "description": "一个50多岁的富有老者，身形略显消瘦，神情傲慢且眼神中透着商人的势利与冷酷。他留着一丝不苟的后梳白发，身穿一件深灰色的精纺羊毛呢大衣，内搭藏青色立领衬衫。他手腕上戴着昂贵的金质机械表，言语间总带着不容置疑的优越感，给人一种极强的压迫感和冷漠疏离感。"
  },
  {
    "name": "外婆(反派配角)",
    "aliases": "沈星辞的外婆",
    "description": "一个50多岁的老太太，眉目间刻着养尊处优的矜傲，眼神却透着市侩的尖酸。她留着整齐的暗紫色短卷发，耳垂上坠着两颗浑圆的珍珠。她身穿一件米灰色羊绒开衫，内搭深紫色真丝衬衫，领口别着一枚精致的翡翠胸针，下身穿着垂感极佳的黑色西装裤与平底尖头皮鞋。整体形象虽然体面，却散发着一种冷漠而刻薄的贵气。"
  },
  {
    "name": "沈星辞亲生母亲(配角)",
    "aliases": "第一任妻子",
    "description": "一个40岁左右的富家女性，皮肤保养极佳，五官与沈星辞高度相似，透着一种精致而脆弱的美感。她留着一头打理完美的黑色盘发，身穿一件莫兰迪色的丝绒改良旗袍，佩戴着价值不菲的珍珠项链和耳饰。虽然外表光鲜亮丽，但眼神中常带着躲闪与怯懦，整体形象显得自私而虚荣。"
  },
  {
    "name": "新改嫁的老板(反派配角)",
    "aliases": "沈星辞继父",
    "description": "一个50岁左右的中年商人，体态略微发福，举手投足间带着成功人士的傲慢与疏离。他梳着油亮的背头，面部轮廓圆润，眼神犀利。他身穿一套剪裁得体的午夜蓝双排扣戗驳领西装，搭配洁白的精纺棉衬衫和一条暗纹真丝领带，腕间戴着一只沉稳的金属机械表。脚踩手工定制的黑色牛皮鞋，整体形象多金而轻慢。"
  },
  {
    "name": "第一任继母(配角/反派)",
    "aliases": "暴力的女人",
    "description": "一个30多岁的成熟女性，五官凌厉，眼神中常带着不满与暴戾之气。她留着有些杂乱的棕色卷发，身穿一件色彩艳丽的修身针织裙，外罩一件黑色漆皮皮衣。她嘴唇涂得鲜红，眉宇间堆积着怨气，整体穿搭虽然追求时尚，却因为神情中的刻薄而显得极具攻击性。"
  },
  {
    "name": "第二任继母(配角/反派)",
    "aliases": "接线员",
    "description": "一个30岁左右的都市女性，有着明显的整形痕迹，妆容精致得近乎刻意。她留着波浪长发，身穿一件剪裁精良的午夜蓝丝绒吊带裙，外披一件米白色廓形大衣。她手腕上戴着醒目的金属几何饰品，脚踩尖头细高跟鞋，举手投足间充满了对奢侈消费的狂热追求，神情中透着一种暴发户式的虚荣与浮躁。"
  },
  {
    "name": "苏晚前夫(背景角色)",
    "aliases": "前夫哥",
    "description": "一个30岁左右的职场男性，五官端正但面部线条冷硬，透着一种拒人于千里之外的疏离感。他留着利落的商务短发，戴着一副细框金丝眼镜，眼神平静而冷淡。他身穿一件高级灰细格纹西装外套，内搭简约的白衬衫，下身穿着修身的藏青色西装裤。整体穿搭克制而严谨，散发着一种冷战时期特有的沉闷与压抑气息。"
  },
  {
    "name": "资深船员(群像配角)",
    "aliases": "老王",
    "description": "一个50岁左右的资深水手，由于长期海上作业，皮肤呈现粗糙的古铜色，眼角刻满了深刻的鱼尾纹。他身材魁梧，神情豁达。身穿一件做旧的机能风深绿色冲锋衣，内搭一件灰色粗麻工装背心，下身是多口袋的战术工装裤，裤脚扎进防水的皮质短靴里。他腰间挂着一个黄铜酒壶，整体形象粗犷而仗义，是典型饱经风浪的劳动者。"
  }
]"""


# ═══════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════

def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def is_male_description(text: str) -> bool:
    return any(kw in text for kw in MALE_KEYWORDS)


def safe_filename(name: str) -> str:
    return re.sub(r'[/\\:*?"<>|]', '_', str(name)).strip()


# ═══════════════════════════════════════════════════════════════════
# Toast 通知
# ═══════════════════════════════════════════════════════════════════

class Toast(QWidget):
    def __init__(self, parent, text: str, level: str = "info"):
        super().__init__(parent)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)

        label = QLabel(text, self)
        label.setStyleSheet("color: white; font-size: 13px; font-weight: 500;")

        if level == "error":
            bg = "rgba(255,59,48,0.88)"
        elif level == "success":
            bg = "rgba(52,199,89,0.9)"
        else:
            bg = "rgba(29,29,31,0.88)"

        self.setStyleSheet(f"""
            Toast {{
                background: {bg};
                border-radius: 20px;
            }}
        """)
        layout.addWidget(label)
        self.adjustSize()


class ToastManager:
    """管理 Toast 通知的显示"""
    def __init__(self, parent: QWidget):
        self.parent = parent
        self.toasts = []

    def show(self, text: str, level: str = "info"):
        toast = Toast(self.parent, text, level)
        toast.show()

        # 定位在父窗口底部中央
        pw = self.parent.width()
        ph = self.parent.height()
        tx = pw // 2 - toast.width() // 2
        ty = ph - 80 - len(self.toasts) * 50
        toast.move(tx, ty)
        toast.raise_()

        self.toasts.append(toast)

        QTimer.singleShot(2800, lambda: self._fade_out(toast))

    def _fade_out(self, toast):
        if toast in self.toasts:
            self.toasts.remove(toast)
        toast.deleteLater()


# ═══════════════════════════════════════════════════════════════════
# 日志面板
# ═══════════════════════════════════════════════════════════════════

class LogPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._collapsed = False
        self._error_count = 0
        self._setup_ui()

    def _setup_ui(self):
        self.setFixedHeight(200)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.setStyleSheet("""
            LogPanel {
                background: #ffffff;
                border-top: 1px solid #d2d2d7;
            }
        """)

        # Header
        header = QWidget()
        header.setFixedHeight(36)
        header.setCursor(Qt.PointingHandCursor)
        header.mousePressEvent = self._on_header_click
        header.setStyleSheet("""
            QWidget { background: #ffffff; border-bottom: 1px solid #d2d2d7; }
            QWidget:hover { background: #f5f5f7; }
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 16, 0)

        self._dot = QLabel()
        self._dot.setFixedSize(7, 7)
        self._dot.setStyleSheet("""
            background: #d2d2d7;
            border-radius: 3px;
        """)
        header_layout.addWidget(self._dot)

        self._title = QLabel("生成日志")
        self._title.setStyleSheet("""
            font-size: 11px; font-weight: 600; color: #6e6e73;
            letter-spacing: 0.05em; border: none; background: transparent;
        """)
        header_layout.addWidget(self._title)
        header_layout.addStretch()

        self._badge = QLabel("空")
        self._badge.setStyleSheet("""
            font-size: 10px; color: #86868b; background: #f5f5f7;
            border: none; padding: 1px 7px; border-radius: 10px;
        """)
        header_layout.addWidget(self._badge)

        clear_btn = QPushButton("清空")
        clear_btn.setStyleSheet("""
            QPushButton {
                font-size: 10px; color: #86868b; background: transparent;
                border: none; padding: 2px 6px; border-radius: 4px;
            }
            QPushButton:hover { color: #1d1d1f; }
        """)
        clear_btn.clicked.connect(self.clear_log)
        header_layout.addWidget(clear_btn)

        self._arrow = QLabel("▲")
        self._arrow.setStyleSheet("""
            font-size: 9px; color: #86868b; border: none; background: transparent;
        """)
        header_layout.addWidget(self._arrow)

        main_layout.addWidget(header)

        # Body
        self._body = QTextBrowser()
        self._body.setReadOnly(True)
        self._body.setStyleSheet("""
            QTextBrowser {
                background: #ffffff;
                border: none;
                font-family: "Cascadia Code", "Fira Code", "SF Mono", Menlo, monospace;
                font-size: 11px;
                padding: 8px 16px;
            }
        """)
        main_layout.addWidget(self._body)

    def _on_header_click(self, event):
        self._collapsed = not self._collapsed
        if self._collapsed:
            self.setFixedHeight(36)
            self._arrow.setText("▼")
        else:
            self.setFixedHeight(200)
            self._arrow.setText("▲")

    def add_log(self, msg: str, level: str = "info"):
        now = time.strftime("%H:%M:%S")
        color_map = {
            "info": "#86868b",
            "ok": "#1a8a3c",
            "warn": "#b25a00",
            "error": "#ff3b30",
            "req": "#0071e3",
            "resp": "#7c3aed",
        }
        color = color_map.get(level, "#86868b")
        weight = "font-weight:500;" if level == "error" else ""

        html = f'<div><span style="color:#86868b;">{now}</span> <span style="color:{color};{weight}">{escape_html(msg)}</span></div>'
        self._body.append(html)

        # 更新状态
        total = self._body.document().blockCount()
        if level == "error":
            self._error_count += 1
            self._badge.setStyleSheet("""
                font-size: 10px; color: #ff3b30; background: rgba(255,59,48,0.1);
                border: none; padding: 1px 7px; border-radius: 10px;
            """)
            self._badge.setText(f"{self._error_count} 个错误")
            self._dot.setStyleSheet("background: #ff3b30; border-radius: 3px;")
        elif level in ("ok", "req"):
            self._dot.setStyleSheet("background: #30d158; border-radius: 3px;")
            if self._error_count == 0:
                self._badge.setStyleSheet("""
                    font-size: 10px; color: #86868b; background: #f5f5f7;
                    border: none; padding: 1px 7px; border-radius: 10px;
                """)
                self._badge.setText(f"{total} 条")

        # 错误/警告时自动展开
        if level in ("error", "warn") and self._collapsed:
            self._on_header_click(None)

    def clear_log(self):
        self._body.clear()
        self._error_count = 0
        self._badge.setStyleSheet("""
            font-size: 10px; color: #86868b; background: #f5f5f7;
            border: none; padding: 1px 7px; border-radius: 10px;
        """)
        self._badge.setText("空")
        self._dot.setStyleSheet("background: #d2d2d7; border-radius: 3px;")

    def set_idle(self):
        if self._error_count == 0:
            self._dot.setStyleSheet("background: #d2d2d7; border-radius: 3px;")


# ═══════════════════════════════════════════════════════════════════
# 图片放大对话框
# ═══════════════════════════════════════════════════════════════════

class ImageZoomDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setStyleSheet("background: rgba(0,0,0,0.88);")
        self.setCursor(Qt.CursorShape.CrossCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignCenter)
        self._image_label.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(self._image_label)

        self.mousePressEvent = self._on_click

    def show_image(self, url: str):
        self._current_url = url
        # 下载图片并显示
        try:
            import requests
            resp = requests.get(url, timeout=30)
            if resp.ok:
                pixmap = QPixmap()
                pixmap.loadFromData(resp.content)
                if not pixmap.isNull():
                    screen = QApplication.primaryScreen().size()
                    max_w = int(screen.width() * 0.92)
                    max_h = int(screen.height() * 0.92)
                    scaled = pixmap.scaled(
                        max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation
                    )
                    self._image_label.setPixmap(scaled)
                    self.setFixedSize(scaled.size() + QSize(0, 0))
                else:
                    self._image_label.setText("图片加载失败")
                    self.setFixedSize(400, 200)
            else:
                self._image_label.setText(f"下载失败: HTTP {resp.status_code}")
                self.setFixedSize(400, 200)
        except Exception as e:
            self._image_label.setText(f"加载失败: {e}")
            self.setFixedSize(400, 200)

        # 居中显示
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            screen.center().x() - self.width() // 2,
            screen.center().y() - self.height() // 2,
        )
        self.exec()

    def _on_click(self, event):
        self.close()


# ═══════════════════════════════════════════════════════════════════
# 角色卡片 Widget
# ═══════════════════════════════════════════════════════════════════

class CardWidget(QFrame):
    """单个角色卡片"""

    # Signals
    generate_clicked = Signal(int)
    download_clicked = Signal(int)
    delete_clicked = Signal(int)
    select_toggled = Signal(int, bool)
    copy_prompt_clicked = Signal(int)
    zoom_image_clicked = Signal(str)
    retry_clicked = Signal(int)
    reload_clicked = Signal(int)

    def __init__(self, index: int, char_data: dict, ratio: str = "square", parent=None):
        super().__init__(parent)
        self._index = index
        self._char = char_data
        self._ratio = ratio
        self._selected = char_data.get("_selected", False)
        self._setup_ui()
        self._update_display()

    def _setup_ui(self):
        self.setObjectName(f"card-{self._index}")
        self.setProperty("cssClass", "char-card")
        self.setStyleSheet("""
            QFrame[cssClass="char-card"] {
                background: #ffffff;
                border: 1px solid #d2d2d7;
                border-radius: 14px;
            }
            QFrame[cssClass="char-card"]:hover {
                border-color: #b0b0b8;
            }
        """)
        self.setCursor(Qt.PointingHandCursor)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 图片区域
        self._image_wrap = QWidget()
        self._image_wrap.setFixedHeight(300)
        self._image_wrap.setStyleSheet("background: #2a2a2e; border: none;")
        self._image_wrap.setCursor(Qt.ArrowCursor)

        self._image_layout = QVBoxLayout(self._image_wrap)
        self._image_layout.setContentsMargins(0, 0, 0, 0)

        # 图片标签
        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignCenter)
        self._image_label.setScaledContents(False)
        self._image_layout.addWidget(self._image_label)

        # 选择复选框（覆盖层）
        self._checkbox = QCheckBox(self._image_wrap)
        self._checkbox.setFixedSize(22, 22)
        self._checkbox.move(8, 8)
        self._checkbox.setStyleSheet("""
            QCheckBox {
                background: rgba(0,0,0,0.2);
                border: 2px solid rgba(255,255,255,0.8);
                border-radius: 11px;
            }
            QCheckBox::indicator { width: 0; height: 0; }
            QCheckBox:checked {
                background: #0071e3;
                border-color: #0071e3;
            }
        """)
        self._checkbox.toggled.connect(lambda v: self.select_toggled.emit(self._index, v))

        # 删除按钮（覆盖层）
        self._delete_btn = QPushButton("✕", self._image_wrap)
        self._delete_btn.setFixedSize(22, 22)
        self._delete_btn.move(self._image_wrap.width() - 30, 8)
        self._delete_btn.setStyleSheet("""
            QPushButton {
                background: rgba(0,0,0,0.25);
                color: white;
                border: none;
                border-radius: 11px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: rgba(255,59,48,0.85);
            }
        """)
        self._delete_btn.clicked.connect(lambda: self.delete_clicked.emit(self._index))

        main_layout.addWidget(self._image_wrap)

        # 信息区域
        info_widget = QWidget()
        info_widget.setStyleSheet("background: transparent; border: none;")
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(14, 12, 14, 14)
        info_layout.setSpacing(4)

        # 名称行
        name_row = QHBoxLayout()
        self._name_label = QLabel()
        self._name_label.setStyleSheet("""
            font-size: 15px; font-weight: 600; color: #1d1d1f;
            border: none; background: transparent;
        """)
        self._name_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        name_row.addWidget(self._name_label, 1)

        self._copy_btn = QPushButton("  复制")
        self._copy_btn.setStyleSheet("""
            QPushButton {
                font-size: 10px; font-weight: 500; color: #6e6e73;
                background: #f5f5f7; border: 1px solid #d2d2d7;
                border-radius: 4px; padding: 2px 8px;
            }
            QPushButton:hover { border-color: #0071e3; color: #0071e3; }
        """)
        self._copy_btn.clicked.connect(lambda: self.copy_prompt_clicked.emit(self._index))
        name_row.addWidget(self._copy_btn)
        name_row.setStretch(0, 1)
        info_layout.addLayout(name_row)

        # 别名
        self._aliases_label = QLabel()
        self._aliases_label.setStyleSheet("""
            font-size: 12px; color: #86868b; border: none; background: transparent;
        """)
        self._aliases_label.setWordWrap(True)
        info_layout.addWidget(self._aliases_label)

        # 描述
        self._desc_label = QLabel()
        self._desc_label.setStyleSheet("""
            font-size: 12px; color: #6e6e73; line-height: 1.5;
            border: none; background: transparent;
        """)
        self._desc_label.setWordWrap(True)
        self._desc_label.setMaximumHeight(80)
        info_layout.addWidget(self._desc_label)

        # 操作按钮
        actions_row = QHBoxLayout()
        actions_row.setSpacing(6)

        self._gen_btn = QPushButton("生成图片")
        self._gen_btn.setProperty("cssClass", "card-action")
        self._gen_btn.setStyleSheet(self._btn_style("secondary"))
        self._gen_btn.clicked.connect(lambda: self.generate_clicked.emit(self._index))

        self._download_btn = QPushButton("⬇ 下载")
        self._download_btn.setProperty("cssClass", "card-action")
        self._download_btn.setStyleSheet(self._btn_style("download"))
        self._download_btn.clicked.connect(lambda: self.download_clicked.emit(self._index))
        self._download_btn.setVisible(False)

        actions_row.addWidget(self._gen_btn)
        actions_row.addWidget(self._download_btn)
        info_layout.addLayout(actions_row)

        main_layout.addWidget(info_widget)

    def _btn_style(self, kind: str):
        base = """
            QPushButton {
                height: 28px; padding: 0 10px; font-size: 11px;
                font-weight: 500; border-radius: 14px;
            }
        """
        if kind == "secondary":
            return base + """
                QPushButton {
                    background: #f5f5f7; color: #1d1d1f;
                    border: 1px solid #d2d2d7;
                }
                QPushButton:hover { background: #e8e8ed; }
            """
        elif kind == "download":
            return base + """
                QPushButton {
                    background: rgba(48,209,88,0.1); color: #1a8a3c;
                    border: 1px solid rgba(48,209,88,0.25);
                }
                QPushButton:hover { background: rgba(48,209,88,0.2); }
            """
        return base

    def _update_display(self):
        c = self._char
        status = c.get("status", "idle")

        self._name_label.setText(c.get("name", "未知角色"))
        self._aliases_label.setText(f"别名：{c.get('aliases', '')}" if c.get("aliases") else "")
        self._desc_label.setText(c.get("description", ""))
        self._checkbox.setChecked(self._selected)

        image_url = c.get("imageUrl")

        if status == "generating":
            poll = c.get("pollAttempt", 0)
            label = f"轮询中 ({poll}/12)…" if poll > 0 else "AI 生成中…"
            self._image_label.setText(f"⏳\n{label}")
            self._image_label.setStyleSheet("color: #0071e3; font-size: 11px; font-weight: 600;")
            self._gen_btn.setText("生成中…")
            self._gen_btn.setEnabled(False)
            self._download_btn.setVisible(False)

        elif image_url:
            self._load_image(image_url)
            self._gen_btn.setText("重新生图")
            self._gen_btn.setEnabled(True)
            self._download_btn.setVisible(True)
            # 点击图片放大
            self._image_label.mousePressEvent = lambda e: self.zoom_image_clicked.emit(image_url)
            self._image_label.setCursor(Qt.PointingHandCursor)

        elif status == "error":
            self._image_label.setText("⚠ 生成失败")
            self._image_label.setStyleSheet("color: #ff3b30; font-size: 12px; font-weight: 500;")
            self._gen_btn.setText("重试")
            self._gen_btn.setEnabled(True)
            self._download_btn.setVisible(False)

        else:
            self._image_label.setText("")
            self._image_label.setStyleSheet("")
            self._gen_btn.setText("生成图片")
            self._gen_btn.setEnabled(True)
            self._download_btn.setVisible(False)

    def _load_image(self, url: str):
        """异步加载图片"""
        try:
            import requests
            resp = requests.get(url, timeout=30)
            if resp.ok:
                pixmap = QPixmap()
                pixmap.loadFromData(resp.content)
                if not pixmap.isNull():
                    scaled = pixmap.scaled(
                        300, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation
                    )
                    self._image_label.setPixmap(scaled)
                    self._image_label.setStyleSheet("border: none; background: transparent;")
                    return
        except Exception:
            pass

        self._image_label.setText("图片加载失败")
        self._image_label.setStyleSheet("color: #ff6b62; font-size: 11px;")

    def set_selected(self, selected: bool):
        self._selected = selected
        self._checkbox.setChecked(selected)

    def update_data(self, char_data: dict):
        self._char = char_data
        self._selected = char_data.get("_selected", False)
        self._update_display()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_delete_btn'):
            self._delete_btn.move(self._image_wrap.width() - 30, 8)


# ═══════════════════════════════════════════════════════════════════
# 快速生成面板
# ═══════════════════════════════════════════════════════════════════

class QuickGeneratePanel(QWidget):
    generate_clicked = Signal(str, str)  # name, description

    def __init__(self, parent=None):
        super().__init__(parent)
        self._collapsed = False
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("""
            QuickGeneratePanel {
                background: #e8f0fe;
                border: 1px solid rgba(0,113,227,0.2);
                border-radius: 8px;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setCursor(Qt.PointingHandCursor)
        header.mousePressEvent = self._toggle
        header.setStyleSheet("background: transparent; border: none;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 9, 12, 9)

        title = QLabel("⚡ 快速生成单张角色卡")
        title.setStyleSheet("""
            font-size: 12px; font-weight: 600; color: #0071e3;
            border: none; background: transparent;
        """)
        header_layout.addWidget(title)
        header_layout.addStretch()

        self._arrow = QLabel("▼")
        self._arrow.setStyleSheet("""
            font-size: 10px; color: #0071e3; border: none; background: transparent;
        """)
        header_layout.addWidget(self._arrow)
        main_layout.addWidget(header)

        # Body
        self._body = QWidget()
        body_layout = QVBoxLayout(self._body)
        body_layout.setContentsMargins(12, 0, 12, 12)
        body_layout.setSpacing(6)

        name_row = QHBoxLayout()
        name_label = QLabel("角色名")
        name_label.setStyleSheet("font-size: 11px; color: #6e6e73; border: none; background: transparent;")
        name_row.addWidget(name_label)
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("可选，默认「自定义角色」")
        self._name_input.setFixedHeight(30)
        self._name_input.setStyleSheet("""
            QLineEdit {
                background: white; border: 1px solid #d2d2d7;
                border-radius: 6px; padding: 0 9px; font-size: 12px;
            }
            QLineEdit:focus { border-color: #0071e3; }
        """)
        name_row.addWidget(self._name_input, 1)
        body_layout.addLayout(name_row)

        self._desc_input = QPlainTextEdit()
        self._desc_input.setPlaceholderText(
            "直接输入描述词，生成时自动加上前后缀\n例：一位30岁的女性，深棕色长发，温柔眼神…"
        )
        self._desc_input.setFixedHeight(80)
        self._desc_input.setStyleSheet("""
            QPlainTextEdit {
                background: white; border: 1px solid #d2d2d7;
                border-radius: 6px; padding: 8px 10px; font-size: 12px;
            }
            QPlainTextEdit:focus { border-color: #0071e3; }
        """)
        body_layout.addWidget(self._desc_input)

        hint = QLabel("生成结果会追加到角色卡列表末尾")
        hint.setStyleSheet("""
            font-size: 11px; color: #86868b; border: none; background: transparent;
        """)
        body_layout.addWidget(hint)

        self._gen_btn = QPushButton("⚡ 立即生成")
        self._gen_btn.setFixedHeight(34)
        self._gen_btn.setStyleSheet("""
            QPushButton {
                background: #0071e3; color: white; border: none;
                border-radius: 17px; font-size: 13px; font-weight: 500;
            }
            QPushButton:hover { background: #0077ed; }
            QPushButton:disabled { opacity: 0.45; }
        """)
        self._gen_btn.clicked.connect(self._on_generate)
        body_layout.addWidget(self._gen_btn)

        main_layout.addWidget(self._body)

    def _toggle(self, event):
        self._collapsed = not self._collapsed
        self._body.setVisible(not self._collapsed)
        self._arrow.setText("▶" if self._collapsed else "▼")

    def _on_generate(self):
        desc = self._desc_input.toPlainText().strip()
        if not desc:
            return
        name = self._name_input.text().strip() or "自定义角色"
        self.generate_clicked.emit(name, desc)

    def set_generating(self, generating: bool):
        self._gen_btn.setEnabled(not generating)
        self._gen_btn.setText("⏳ 生成中…" if generating else "⚡ 立即生成")


# ═══════════════════════════════════════════════════════════════════
# 参考图片管理
# ═══════════════════════════════════════════════════════════════════

class RefImageItem(QWidget):
    removed = Signal(int)

    def __init__(self, index: int, file_name: str, data_url: str, parent=None):
        super().__init__(parent)
        self._index = index
        self._file_name = file_name
        self._data_url = data_url
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("""
            RefImageItem {
                background: white; border: 1px solid #d2d2d7;
                border-radius: 8px; padding: 8px;
            }
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        # 缩略图
        thumb = QLabel()
        thumb.setFixedSize(60, 60)
        thumb.setStyleSheet("background: #f5f5f7; border-radius: 6px; border: none;")
        thumb.setScaledContents(True)
        try:
            pixmap = QPixmap()
            pixmap.loadFromData(self._data_url.encode() if isinstance(self._data_url, str) else self._data_url)
            if not pixmap.isNull():
                thumb.setPixmap(pixmap.scaled(60, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception:
            pass
        layout.addWidget(thumb)

        # 信息
        info_layout = QVBoxLayout()
        name_label = QLabel(self._file_name or f"参考图{self._index + 1}")
        name_label.setStyleSheet("""
            font-size: 11px; font-weight: 500; color: #1d1d1f;
            border: none; background: transparent;
        """)
        info_layout.addWidget(name_label)

        self._prompt_input = QPlainTextEdit()
        self._prompt_input.setPlaceholderText("输入描述词（可选），留空则只用前后缀生成")
        self._prompt_input.setFixedHeight(40)
        self._prompt_input.setStyleSheet("""
            QPlainTextEdit {
                background: #f5f5f7; border: 1px solid #d2d2d7;
                border-radius: 4px; padding: 4px 6px; font-size: 11px;
            }
            QPlainTextEdit:focus { border-color: #0071e3; }
        """)
        info_layout.addWidget(self._prompt_input)
        layout.addLayout(info_layout, 1)

        # 删除按钮
        remove_btn = QPushButton("✕")
        remove_btn.setFixedSize(22, 22)
        remove_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #86868b;
                border: none; border-radius: 4px; font-size: 14px;
            }
            QPushButton:hover { background: #ff3b30; color: white; }
        """)
        remove_btn.clicked.connect(lambda: self.removed.emit(self._index))
        layout.addWidget(remove_btn)

    def prompt_text(self) -> str:
        return self._prompt_input.toPlainText().strip()


class RefImagesSection(QWidget):
    images_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._images = []  # list of {fileName, dataUrl}
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("""
            RefImagesSection {
                background: #f5f5f7; border: 1px dashed #d2d2d7;
                border-radius: 8px; padding: 10px;
            }
        """)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # Header
        header = QHBoxLayout()
        title = QLabel("参考图片（可选）")
        title.setStyleSheet("font-size: 11px; font-weight: 600; color: #6e6e73; border: none;")
        header.addWidget(title)
        header.addStretch()

        add_btn = QPushButton("+ 添加图片")
        add_btn.setProperty("cssClass", "inline")
        add_btn.setStyleSheet("""
            QPushButton {
                height: 24px; padding: 0 8px; font-size: 10px; font-weight: 500;
                background: #f5f5f7; color: #1d1d1f;
                border: 1px solid #d2d2d7; border-radius: 12px;
            }
            QPushButton:hover { background: #e8e8ed; }
        """)
        add_btn.clicked.connect(self._add_images)
        header.addWidget(add_btn)
        main_layout.addLayout(header)

        # Image list
        self._list_layout = QVBoxLayout()
        self._list_layout.setSpacing(8)
        main_layout.addLayout(self._list_layout)

        # Tip
        tip = QLabel("多张图片会生成多张角色卡，角色名为图片文件名")
        tip.setStyleSheet("font-size: 10px; color: #86868b; border: none;")
        main_layout.addWidget(tip)

    def _add_images(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择参考图片", "",
            "Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp)"
        )
        if not files:
            return

        import base64
        for filepath in files:
            file_name = os.path.splitext(os.path.basename(filepath))[0]
            try:
                with open(filepath, "rb") as f:
                    encoded = base64.b64encode(f.read()).decode()
                mime_map = {
                    ".png": "image/png", ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg", ".gif": "image/gif",
                    ".webp": "image/webp", ".bmp": "image/bmp",
                }
                ext = os.path.splitext(filepath)[1].lower()
                mime = mime_map.get(ext, "image/png")
                data_url = f"data:{mime};base64,{encoded}"
                self._images.append({"fileName": file_name, "dataUrl": data_url})
            except Exception:
                pass

        self._refresh_list()

    def _refresh_list(self):
        # 清空列表
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for i, img in enumerate(self._images):
            item = RefImageItem(i, img["fileName"], img["dataUrl"])
            item.removed.connect(self._remove_image)
            self._list_layout.addWidget(item)

        self._list_layout.addStretch()
        self.images_changed.emit()

    def _remove_image(self, index):
        if 0 <= index < len(self._images):
            self._images.pop(index)
            self._refresh_list()

    def get_images(self):
        return self._images

    def clear(self):
        self._images.clear()
        self._refresh_list()


# ═══════════════════════════════════════════════════════════════════
# 卡片网格
# ═══════════════════════════════════════════════════════════════════

class CardGrid(QScrollArea):
    """角色卡片网格 - 使用 QGridLayout 实现自适应列数"""

    card_generate = Signal(int)
    card_download = Signal(int)
    card_delete = Signal(int)
    card_select_toggled = Signal(int, bool)
    card_copy_prompt = Signal(int)
    card_zoom = Signal(str)
    card_retry = Signal(int)
    MIN_CARD_WIDTH = 200

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards = []
        self._characters = []
        self._setup_ui()

    def _setup_ui(self):
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("""
            QScrollArea {
                background: #f5f5f7;
                border: none;
            }
        """)

        self._container = QWidget()
        self._container.setObjectName("cardGridWidget")
        self._container.setStyleSheet("background: transparent;")
        self.setWidget(self._container)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self):
        """根据当前宽度重新计算列数并重新排列卡片"""
        # 安全移除旧布局（不移除其中的 widget）
        old = self._container.layout()
        if old:
            while old.count():
                old.takeAt(0)
            old.deleteLater()

        if not self._characters:
            empty_layout = QVBoxLayout(self._container)
            empty = QLabel("🎭\n\n尚无角色卡\n\n在左侧粘贴 JSON 角色数据，点击「生成角色卡」开始")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("""
                font-size: 14px; color: #86868b; padding: 80px;
                border: none; background: transparent;
            """)
            empty.setMinimumHeight(300)
            empty_layout.addWidget(empty)
            return

        # 使用视口宽度而非容器宽度（容器可能尚未布局）
        viewport_w = self.viewport().width()
        available = max(viewport_w, 400) - 32  # 至少按 400px 计算
        cols = max(1, available // (self.MIN_CARD_WIDTH + 8))
        card_width = (available - (cols - 1) * 8) // cols

        grid = QGridLayout(self._container)
        grid.setContentsMargins(16, 16, 16, 16)
        grid.setSpacing(8)

        for i, card in enumerate(self._cards):
            row = i // cols
            col = i % cols
            card.setMinimumWidth(card_width)
            card.setMaximumWidth(card_width + 20)
            grid.addWidget(card, row, col)

        # Make last row stretch to fill space so cards stay at top
        if self._cards:
            last_row = (len(self._cards) - 1) // cols
            grid.setRowStretch(last_row + 1, 1)

        self._container.updateGeometry()

    def set_characters(self, characters: list, ratio: str = "square"):
        self._characters = characters
        self._rebuild_cards(ratio)

    def _rebuild_cards(self, ratio: str):
        # 清除旧卡片
        for card in self._cards:
            card.deleteLater()
        self._cards.clear()

        if not self._characters:
            self._relayout()
            return

        for i, char in enumerate(self._characters):
            card = CardWidget(i, char, ratio)
            card.generate_clicked.connect(self.card_generate.emit)
            card.download_clicked.connect(self.card_download.emit)
            card.delete_clicked.connect(self.card_delete.emit)
            card.select_toggled.connect(self.card_select_toggled.emit)
            card.copy_prompt_clicked.connect(self.card_copy_prompt.emit)
            card.zoom_image_clicked.connect(self.card_zoom.emit)
            card.retry_clicked.connect(self.card_retry.emit)
            self._cards.append(card)

        self._relayout()

    def update_card(self, index: int):
        if 0 <= index < len(self._cards) and index < len(self._characters):
            self._cards[index].update_data(self._characters[index])

    def update_all(self):
        if len(self._cards) == len(self._characters):
            for i, card in enumerate(self._cards):
                card.update_data(self._characters[i])
        else:
            self._rebuild_cards("square")

    def selected_indices(self) -> list:
        return [i for i, c in enumerate(self._characters) if c.get("_selected")]

    def set_selected(self, index: int, selected: bool):
        if 0 <= index < len(self._characters):
            self._characters[index]["_selected"] = selected
        if 0 <= index < len(self._cards):
            self._cards[index].set_selected(selected)


# ═══════════════════════════════════════════════════════════════════
# 侧边栏
# ═══════════════════════════════════════════════════════════════════

class Sidebar(QScrollArea):
    """左侧设置面板"""

    generate_cards_clicked = Signal()
    generate_all_clicked = Signal()
    retry_failed_clicked = Signal()
    download_all_clicked = Signal()
    clear_all_clicked = Signal()
    quick_generate = Signal(str, str)  # name, description
    ratio_changed = Signal(str)  # square, portrait, landscape

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._load_defaults()

    def _setup_ui(self):
        self.setFixedWidth(360)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("""
            QScrollArea {
                background: #ffffff;
                border: none;
                border-right: 1px solid #d2d2d7;
            }
        """)

        self._container = QWidget()
        self._container.setStyleSheet("background: #ffffff;")
        self.setWidget(self._container)

        layout = QVBoxLayout(self._container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setStyleSheet("""
            background: #ffffff; border-bottom: 1px solid #d2d2d7;
            padding: 20px 20px 14px;
        """)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 18, 20, 12)
        title = QLabel("乐乐角色卡生成器")
        title.setStyleSheet("font-size: 17px; font-weight: 600; color: #1d1d1f; border: none;")
        subtitle = QLabel("微信：rpalele | AI 角色立绘生成工具")
        subtitle.setStyleSheet("font-size: 12px; color: #86868b; border: none;")
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        layout.addWidget(header)

        # Body (scrollable content)
        body = QWidget()
        body.setStyleSheet("background: #ffffff;")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 14, 20, 14)
        body_layout.setSpacing(10)

        # 快速生成面板
        self._quick_panel = QuickGeneratePanel()
        self._quick_panel.generate_clicked.connect(self.quick_generate.emit)
        body_layout.addWidget(self._quick_panel)

        # JSON 输入
        self._add_section_label(body_layout, "JSON 角色数据")
        self._json_input = QPlainTextEdit()
        self._json_input.setPlaceholderText(
            '[\n  {\n    "name": "角色名称",\n    "aliases": "别名1, 别名2",\n    "description": "人物描述..."\n  }\n]'
        )
        self._json_input.setFixedHeight(200)
        self._json_input.setStyleSheet(self._input_style())
        body_layout.addWidget(self._json_input)

        # 提示词前缀
        self._add_section_label(body_layout, "提示词前缀")
        self._prefix_input = QPlainTextEdit()
        self._prefix_input.setPlainText(
            "根据下面的描述生成一张比例1:1的人物图片，亚洲面孔，真人写实风格，"
        )
        self._prefix_input.setFixedHeight(72)
        self._prefix_input.setStyleSheet(self._input_style())
        body_layout.addWidget(self._prefix_input)

        # 提示词后缀
        self._add_section_label(body_layout, "提示词后缀")
        self._suffix_input = QPlainTextEdit()
        self._suffix_input.setPlainText(
            "不要加分割线，纯白色背景，左边腰部以上正面特写，右边正面全身照，站立姿势，不要文字，不要手中拿的物品，双手自然放下，8头身比，极致的身材比例（8k分辨率，极致细节，大师杰作，高品质）。"
        )
        self._suffix_input.setFixedHeight(72)
        self._suffix_input.setStyleSheet(self._input_style())
        body_layout.addWidget(self._suffix_input)

        # API 设置
        self._add_section_label(body_layout, "API 设置")
        preset_row = QHBoxLayout()
        for preset_id in ["localhost", "geeknow"]:
            btn = QPushButton(preset_id)
            btn.setProperty("cssClass", "inline")
            btn.setStyleSheet("""
                QPushButton {
                    height: 24px; padding: 0 10px; font-size: 10px; font-weight: 500;
                    background: #f5f5f7; color: #6e6e73;
                    border: 1px solid #d2d2d7; border-radius: 5px;
                }
                QPushButton:hover { border-color: #0071e3; color: #0071e3; }
            """)
            btn.clicked.connect(lambda checked, p=preset_id: self._apply_preset(p))
            preset_row.addWidget(btn)
        preset_row.addStretch()
        body_layout.addLayout(preset_row)

        # Base URL
        url_row = QHBoxLayout()
        url_label = QLabel("Base URL")
        url_label.setStyleSheet("font-size: 12px; color: #6e6e73; border: none;")
        url_row.addWidget(url_label)
        self._api_base = QLineEdit("http://localhost:8000")
        self._api_base.setFixedHeight(32)
        self._api_base.setStyleSheet(self._line_style())
        url_row.addWidget(self._api_base, 1)
        body_layout.addLayout(url_row)

        # API Key
        key_row = QHBoxLayout()
        key_label = QLabel("API Key")
        key_label.setStyleSheet("font-size: 12px; color: #6e6e73; border: none;")
        key_row.addWidget(key_label)
        self._api_key = QLineEdit("sk-MuEiwKWLDIpAX68VCmxcZV6cwuHHQR102Qke5P6xKFgYOmRT")
        self._api_key.setFixedHeight(32)
        self._api_key.setStyleSheet(self._line_style())
        key_row.addWidget(self._api_key, 1)
        body_layout.addLayout(key_row)

        # Model
        model_row = QHBoxLayout()
        model_label = QLabel("模型")
        model_label.setStyleSheet("font-size: 12px; color: #6e6e73; border: none;")
        model_row.addWidget(model_label)
        self._model_combo = QComboBox()
        self._model_combo.setEditable(True)
        self._model_combo.addItems(MODEL_OPTIONS)
        self._model_combo.setCurrentText("gemini-3-pro-image-preview")
        self._model_combo.setFixedHeight(32)
        self._model_combo.setStyleSheet(self._line_style())
        model_row.addWidget(self._model_combo, 1)
        body_layout.addLayout(model_row)

        # 比例选择
        ratio_row = QHBoxLayout()
        ratio_label = QLabel("比例")
        ratio_label.setStyleSheet("font-size: 12px; color: #6e6e73; border: none;")
        ratio_row.addWidget(ratio_label)
        self._ratio_btns = {}
        for rid, rlabel in [("square", "1:1"), ("portrait", "9:16"), ("landscape", "16:9")]:
            btn = QPushButton(rlabel)
            btn.setProperty("cssClass", "ratio")
            btn.setStyleSheet("""
                QPushButton {
                    height: 26px; padding: 0 10px; font-size: 11px; font-weight: 500;
                    background: #f5f5f7; color: #6e6e73;
                    border: 1px solid #d2d2d7; border-radius: 6px;
                }
                QPushButton:hover { border-color: #0071e3; color: #0071e3; }
            """)
            btn.clicked.connect(lambda checked, r=rid: self.set_ratio(r))
            ratio_row.addWidget(btn)
            self._ratio_btns[rid] = btn
        ratio_row.addStretch()
        body_layout.addLayout(ratio_row)

        # 参考图片
        self._ref_images = RefImagesSection()
        body_layout.addWidget(self._ref_images)

        layout.addWidget(body, 1)

        # Footer 按钮
        footer = QWidget()
        footer.setStyleSheet("""
            background: #ffffff; border-top: 1px solid #d2d2d7;
            padding: 12px 20px 16px;
        """)
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(20, 12, 20, 16)
        footer_layout.setSpacing(8)

        gen_cards_btn = QPushButton("＋ 生成角色卡")
        gen_cards_btn.setProperty("cssClass", "primary")
        gen_cards_btn.setFixedHeight(38)
        gen_cards_btn.setStyleSheet("""
            QPushButton {
                background: #0071e3; color: white; border: none;
                border-radius: 19px; font-size: 14px; font-weight: 500;
            }
            QPushButton:hover { background: #0077ed; }
        """)
        gen_cards_btn.clicked.connect(self.generate_cards_clicked.emit)
        footer_layout.addWidget(gen_cards_btn)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        for text, prop, signal in [
            ("批量生图", "secondary", self.generate_all_clicked),
            ("重试失败", "retry", self.retry_failed_clicked),
            ("打包 ZIP", "secondary", self.download_all_clicked),
        ]:
            btn = QPushButton(text)
            btn.setFixedHeight(38)
            btn.setMinimumWidth(80)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.clicked.connect(signal.emit)
            btn.setEnabled(False)
            if prop == "secondary":
                btn.setStyleSheet("""
                    QPushButton {
                        background: #f5f5f7; color: #1d1d1f;
                        border: 1px solid #d2d2d7; border-radius: 19px;
                        font-size: 12px; font-weight: 500;
                    }
                    QPushButton:hover { background: #e8e8ed; }
                    QPushButton:disabled { opacity: 0.4; }
                """)
            elif prop == "retry":
                btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(255,149,0,0.1); color: #d97706;
                        border: 1px solid rgba(255,149,0,0.3); border-radius: 19px;
                        font-size: 12px; font-weight: 500;
                    }
                    QPushButton:hover { background: rgba(255,149,0,0.2); }
                    QPushButton:disabled { opacity: 0.4; }
                """)
            btn_row.addWidget(btn)
            if text == "批量生图":
                self._btn_gen_all = btn
            elif text == "重试失败":
                self._btn_retry_failed = btn
            elif text == "打包 ZIP":
                self._btn_download_all = btn

        clear_btn = QPushButton("清空所有卡片")
        clear_btn.setFixedHeight(38)
        clear_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,59,48,0.1); color: #ff3b30;
                border: 1px solid rgba(255,59,48,0.2); border-radius: 19px;
                font-size: 13px; font-weight: 500;
            }
            QPushButton:hover { background: rgba(255,59,48,0.18); }
        """)
        clear_btn.clicked.connect(self.clear_all_clicked.emit)
        footer_layout.addWidget(clear_btn)

        layout.addWidget(footer)

        # 初始化比例按钮状态
        self.set_ratio("square")

    def _add_section_label(self, layout, text):
        label = QLabel(text)
        label.setStyleSheet("""
            font-size: 11px; font-weight: 600; color: #86868b;
            text-transform: uppercase; margin-top: 12px; margin-bottom: 4px;
            border: none; background: transparent;
        """)
        layout.addWidget(label)

    def _input_style(self):
        return """
            QPlainTextEdit {
                background: #f5f5f7; border: 1px solid #d2d2d7;
                border-radius: 8px; padding: 10px 12px; font-size: 12px;
                color: #1d1d1f;
            }
            QPlainTextEdit:focus { border-color: #0071e3; }
        """

    def _line_style(self):
        return """
            QLineEdit {
                background: #f5f5f7; border: 1px solid #d2d2d7;
                border-radius: 6px; padding: 0 10px; font-size: 12px;
                color: #1d1d1f;
            }
            QLineEdit:focus { border-color: #0071e3; }
        """

    def _load_defaults(self):
        self._json_input.setPlainText(DEFAULT_JSON)

    def _apply_preset(self, preset_id: str):
        preset = API_PRESETS.get(preset_id)
        if not preset:
            return
        self._api_base.setText(preset["apiBase"])
        self._api_key.setText(preset["apiKey"])
        # 对于 localhost，先设置基础模型名，set_ratio 会自动添加后缀
        model = preset["modelSelect"]
        if is_flow2api_style(preset["apiBase"]):
            model = build_model_with_ratio(preset["modelSelect"], preset["ratio"])
        self._model_combo.setEditText(model)
        self.set_ratio(preset["ratio"])

    def set_ratio(self, ratio: str):
        for rid, btn in self._ratio_btns.items():
            if rid == ratio:
                btn.setStyleSheet("""
                    QPushButton {
                        height: 26px; padding: 0 10px; font-size: 11px; font-weight: 600;
                        background: #0071e3; color: white;
                        border: none; border-radius: 6px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        height: 26px; padding: 0 10px; font-size: 11px; font-weight: 500;
                        background: #f5f5f7; color: #6e6e73;
                        border: 1px solid #d2d2d7; border-radius: 6px;
                    }
                    QPushButton:hover { border-color: #0071e3; color: #0071e3; }
                """)

        # 如果是 localhost/flow2api，同步更新模型名后缀
        base_url = self._api_base.text().strip()
        if is_flow2api_style(base_url):
            current_model = self._model_combo.currentText().strip()
            new_model = build_model_with_ratio(current_model, ratio)
            self._model_combo.setEditText(new_model)

        self.ratio_changed.emit(ratio)

    def get_api_config(self) -> dict:
        return {
            "base_url": self._api_base.text().strip(),
            "api_key": self._api_key.text().strip(),
            "model": self._model_combo.currentText().strip(),
            "ratio": self._get_current_ratio(),
        }

    def _get_current_ratio(self) -> str:
        for rid, btn in self._ratio_btns.items():
            if "#0071e3" in btn.styleSheet():
                return rid
        return "square"

    def get_json_text(self) -> str:
        return self._json_input.toPlainText()

    def get_prefix(self) -> str:
        return self._prefix_input.toPlainText()

    def get_suffix(self) -> str:
        return self._suffix_input.toPlainText()

    def get_ref_images(self):
        return self._ref_images.get_images()

    def set_buttons_enabled(self, has_cards: bool, has_images: bool, has_failed: bool):
        self._btn_gen_all.setEnabled(has_cards)
        self._btn_download_all.setEnabled(has_images)
        self._btn_retry_failed.setEnabled(has_failed)

    def set_quick_generating(self, generating: bool):
        self._quick_panel.set_generating(generating)
