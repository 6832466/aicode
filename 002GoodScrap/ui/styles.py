"""Seven premium text-color themes for Gold Monitor.

Design principles:
- Card stays dark — text carries the personality.
- Luxury brands avoid pure #FFF / #000 — use nuanced off-whites and charcoals.
- Gold/Platinum accents used sparingly for a premium, not gaudy, feel.
- Each theme targets a different desktop-background colour family.
- WCAG AA: large price text (28px bold) needs ≥ 3:1; labels (11–13px) need ≥ 4.5:1.

Sources: haute-finance palettes, Midnight Neon UI Kit, Plascon 2025 Dark Family,
         luxury brand colour systems (Rolex, Chanel, Apple Pro, Aesop).
"""

FONT_FAMILY = "Segoe UI, Microsoft YaHei UI, sans-serif"

# ── Shared dark card base ────────────────────────────────────
CARD_BG = "rgba(22, 23, 28, 0.96)"
SURFACE_BG = "rgba(34, 35, 41, 0.97)"
BORDER = "rgba(255, 255, 255, 0.06)"
MENU_BG = "rgba(34, 35, 41, 0.97)"
INPUT_BG = "rgba(255, 255, 255, 0.04)"
INPUT_BORDER = "rgba(255, 255, 255, 0.07)"
GROUP_BORDER = "rgba(255, 255, 255, 0.07)"
CHECKBOX_BORDER = "rgba(255, 255, 255, 0.22)"

# ═══════════════════════════════════════════════════════════════
#  THEMES  —  text colour only
# ═══════════════════════════════════════════════════════════════

THEMES = {

    # ── 01 鎏金 · warm gold + amber, luxury bullion, for neutral/warm desktops ──
    "鎏金": {
        "title":    "#E2C45A",   # muted 24K headline
        "au_price": "#F0D48A",   # soft pale gold
        "xau_price":"#E8B960",   # warm amber
        "label":    "#A09878",   # warm stone
        "up":       "#F07070",   # muted coral (not screaming red)
        "down":     "#5EC892",   # sage mint
        "time":     "#7A7258",   # bronze
        "separator":"rgba(210, 185, 120, 0.15)",
        "accent":   "#D4AF37",   # metallic gold CTAs
        "arrow_up":   "#F07070",
        "arrow_down": "#5EC892",
        "arrow_neutral": "#7A7258",
    },

    # ── 02 铂金 · platinum silver, cool precision, for white/light desktops ──
    "铂金": {
        "title":    "#D5D8DE",
        "au_price": "#F2F4F8",
        "xau_price":"#C4C9D2",
        "label":    "#9098A4",
        "up":       "#E88080",
        "down":     "#68C888",
        "time":     "#788290",
        "separator":"rgba(200, 205, 215, 0.12)",
        "accent":   "#A0AAB6",
        "arrow_up":   "#E88080",
        "arrow_down": "#68C888",
        "arrow_neutral": "#788290",
    },

    # ── 03 藏蓝 · deep navy + champagne, old-money prestige, for blue desktops ──
    "藏蓝": {
        "title":    "#8AB4E0",
        "au_price": "#EAF0F8",
        "xau_price":"#C8D8F0",
        "label":    "#7A94B0",
        "up":       "#F09090",
        "down":     "#60D098",
        "time":     "#6A8098",
        "separator":"rgba(140, 180, 225, 0.13)",
        "accent":   "#7AB8E0",
        "arrow_up":   "#F09090",
        "arrow_down": "#60D098",
        "arrow_neutral": "#6A8098",
    },

    # ── 04 霓虹 · cyan + violet, cyberpunk electric, for black/pure-dark desktops ──
    "霓虹": {
        "title":    "#00DFFF",
        "au_price": "#F0FAFF",
        "xau_price":"#C070F8",
        "label":    "#7088A0",
        "up":       "#FF5080",
        "down":     "#18E8A0",
        "time":     "#587080",
        "separator":"rgba(0, 224, 255, 0.13)",
        "accent":   "#00DFFF",
        "arrow_up":   "#FF5080",
        "arrow_down": "#18E8A0",
        "arrow_neutral": "#587080",
    },

    # ── 05 绯月 · aubergine + rose gold, sultry elegance, for purple/magenta desktops ──
    "绯月": {
        "title":    "#E8A0C0",
        "au_price": "#FFF0F5",
        "xau_price":"#F0B8C8",
        "label":    "#B090A0",
        "up":       "#F08898",
        "down":     "#70D8A8",
        "time":     "#988090",
        "separator":"rgba(230, 150, 185, 0.14)",
        "accent":   "#E0A0B8",
        "arrow_up":   "#F08898",
        "arrow_down": "#70D8A8",
        "arrow_neutral": "#988090",
    },

    # ── 06 松石 · teal + warm coral, refined wellness, for green/teal desktops ──
    "松石": {
        "title":    "#60D0B8",
        "au_price": "#E8F8F2",
        "xau_price":"#88D8C0",
        "label":    "#7AA898",
        "up":       "#F0A080",
        "down":     "#50D0A0",
        "time":     "#6A9084",
        "separator":"rgba(96, 208, 184, 0.14)",
        "accent":   "#60D0B8",
        "arrow_up":   "#F0A080",
        "arrow_down": "#50D0A0",
        "arrow_neutral": "#6A9084",
    },

    # ── 07 墨韵 · warm ink + parchment, zen minimalism, universal / mixed desktops ──
    "墨韵": {
        "title":    "#C8C0B0",
        "au_price": "#F5F0E8",
        "xau_price":"#D8D0C0",
        "label":    "#989080",
        "up":       "#E89880",
        "down":     "#68B898",
        "time":     "#888070",
        "separator":"rgba(200, 192, 176, 0.13)",
        "accent":   "#C0B898",
        "arrow_up":   "#E89880",
        "arrow_down": "#68B898",
        "arrow_neutral": "#888070",
    },
}

CURRENT = "鎏金"


# ── helpers ──────────────────────────────────────────────────

def _t() -> dict:
    return THEMES[CURRENT]


def set_theme(name: str) -> None:
    global CURRENT
    if name in THEMES:
        CURRENT = name


def get_theme_names() -> list[str]:
    return list(THEMES.keys())


def get_color(key: str) -> str:
    return _t().get(key, "#FFFFFF")


# ── QSS builders ────────────────────────────────────────────

def window_qss() -> str:
    return f"""
    #floatingCard {{
        background: {CARD_BG};
        border: 1px solid {BORDER};
        border-radius: 12px;
    }}
    """


def content_qss() -> str:
    t = _t()
    return f"""
    * {{
        font-family: "{FONT_FAMILY}";
        background: transparent;
    }}
    #titleLabel {{
        color: {t['title']};
        font-size: 11px;
        font-weight: 500;
        letter-spacing: 2px;
    }}
    #priceLabelAU {{
        color: {t['au_price']};
        font-size: 28px;
        font-weight: 700;
    }}
    #priceLabelXAU {{
        color: {t['xau_price']};
        font-size: 28px;
        font-weight: 700;
    }}
    #nameLabel {{
        color: {t['label']};
        font-size: 11px;
        font-weight: 400;
        letter-spacing: 1px;
    }}
    #更新时间 {{
        color: {t['time']};
        font-size: 10px;
    }}
    #separator {{
        background: {t['separator']};
        min-height: 1px;
        max-height: 1px;
    }}
    """


def dialog_qss() -> str:
    t = _t()
    return f"""
    QDialog {{
        background: {SURFACE_BG};
        border: 1px solid {BORDER};
        border-radius: 12px;
    }}
    QLabel {{
        color: {t['label']};
        font-family: "{FONT_FAMILY}";
    }}
    QLabel#sectionTitle {{
        font-size: 13px;
        font-weight: 600;
        color: {t['accent']};
        margin-top: 8px;
    }}
    QLineEdit, QDoubleSpinBox, QSpinBox {{
        background: {INPUT_BG};
        border: 1px solid {INPUT_BORDER};
        border-radius: 6px;
        padding: 6px 10px;
        color: {t['au_price']};
        font-family: "{FONT_FAMILY}";
        font-size: 13px;
        min-height: 20px;
    }}
    QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus {{
        border-color: {t['accent']};
    }}
    QSlider::groove:horizontal {{
        background: rgba(255,255,255,0.07);
        height: 4px;
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        background: {t['accent']};
        width: 16px;
        height: 16px;
        margin: -6px 0;
        border-radius: 8px;
    }}
    QSlider::sub-page:horizontal {{
        background: {t['accent']};
        border-radius: 2px;
    }}
    QPushButton {{
        background: {t['accent']};
        color: #1A1B1F;
        border: none;
        border-radius: 6px;
        padding: 8px 24px;
        font-family: "{FONT_FAMILY}";
        font-size: 13px;
        font-weight: 600;
        min-width: 80px;
    }}
    QPushButton#cancelBtn {{
        background: rgba(255,255,255,0.05);
        color: {t['label']};
    }}
    QPushButton#cancelBtn:hover {{
        background: rgba(255,255,255,0.10);
    }}
    QCheckBox {{
        color: {t['label']};
        font-family: "{FONT_FAMILY}";
        spacing: 8px;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 4px;
        border: 2px solid {CHECKBOX_BORDER};
        background: transparent;
    }}
    QCheckBox::indicator:checked {{
        background: {t['accent']};
        border-color: {t['accent']};
    }}
    QToolTip {{
        background: {SURFACE_BG};
        color: {t['au_price']};
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 6px 10px;
        font-family: "{FONT_FAMILY}";
        font-size: 12px;
    }}
    QGroupBox {{
        color: {t['label']};
        border: 1px solid {GROUP_BORDER};
        border-radius: 8px;
        margin-top: 12px;
        padding: 14px 12px 8px 12px;
        font-size: 12px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
    }}
    """


def menu_qss() -> str:
    return f"""
    QMenu {{
        background: {MENU_BG};
        border: 1px solid {BORDER};
        border-radius: 8px;
        padding: 6px;
        font-family: "{FONT_FAMILY}";
        font-size: 13px;
        color: #CCD0D8;
    }}
    QMenu::item {{
        padding: 8px 28px;
        border-radius: 4px;
    }}
    QMenu::item:selected {{
        background: rgba(255,255,255,0.07);
    }}
    QMenu::separator {{
        height: 1px;
        background: {BORDER};
        margin: 4px 8px;
    }}
    """


def flash_card_qss_color(color: str) -> str:
    return f"background: {CARD_BG}; border: 2px solid {color}; border-radius: 12px;"


def normal_card_qss() -> str:
    return f"background: {CARD_BG}; border: 1px solid {BORDER}; border-radius: 12px;"
