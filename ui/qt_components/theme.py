"""
IBM Carbon (Gray 100 dark theme) tokens for the Garden Bot UI.

Every color, font and spacing value the Qt UI uses lives here. Regions are
separated by layer tone and 1px rules, corners are square (the toggle switch
is the only rounded thing), numbers are set in the mono face.
"""

import re
from typing import Optional

from PyQt6.QtGui import QColor, QFont, QFontDatabase


class Carbon:
    """Carbon g100 tokens"""

    # Layers
    BACKGROUND = "#161616"
    LAYER_01 = "#262626"
    LAYER_02 = "#393939"
    BORDER_SUBTLE = "#393939"
    LAYER_HOVER_01 = "#333333"
    LAYER_HOVER_02 = "#474747"
    FIELD_BORDER = "#8D8D8D"

    # Text
    TEXT_PRIMARY = "#F4F4F4"
    TEXT_SECONDARY = "#C6C6C6"
    TEXT_HELPER = "#8D8D8D"
    TEXT_PLACEHOLDER = "#6F6F6F"
    TEXT_ON_COLOR = "#FFFFFF"

    # Interaction
    INTERACTIVE = "#0F62FE"
    INTERACTIVE_HOVER = "#0050E6"
    FOCUS = "#FFFFFF"

    # Support
    SUCCESS = "#42BE65"
    TOGGLE_ON = "#24A148"
    TOGGLE_OFF = "#6F6F6F"
    WARNING = "#F1C21B"
    ERROR = "#FA4D56"
    INFO = "#4589FF"
    RAINBOW = "#BE95FF"
    MONEY = "#F1C21B"

    # Notification row tints (warning/error rows in "Needs attention")
    WARNING_ROW = "#2A2618"
    ERROR_ROW = "#2C1A1C"

    # Garden cells
    CELL_STAMPED = "#F1C21B"
    CELL_HELD = "#FF832B"
    CELL_RIPE = "#4589FF"
    CELL_GROWING = "#393939"
    CELL_EGG = "#A56EFF"
    CELL_FOOD = "#42BE65"
    CELL_EMPTY = "#1C1C1C"
    CELL_BOARDWALK = "#262626"
    CELL_PLAYER = "#FFFFFF"

    # Spacing scale
    S1, S2, S3, S4, S5 = 4, 8, 16, 24, 32

    @staticmethod
    def qcolor(hex_color: str) -> QColor:
        return QColor(hex_color)


_FAMILIES = None


def font_families():
    """(sans, mono) families: IBM Plex when installed, else Segoe UI and
    Cascadia Mono / Consolas. Needs a QApplication."""
    global _FAMILIES
    if _FAMILIES is None:
        have = set(QFontDatabase.families())

        def pick(*names):
            for n in names:
                if n in have:
                    return n
            return names[-1]

        _FAMILIES = (
            pick("IBM Plex Sans", "Segoe UI"),
            pick("IBM Plex Mono", "Cascadia Mono", "Consolas"),
        )
    return _FAMILIES


def font(px: int = 14, weight: str = "regular", mono: bool = False, spacing: float = 0.0) -> QFont:
    """A QFont at a pixel size. weight: light | regular | semibold"""
    sans, mono_family = font_families()
    f = QFont(mono_family if mono else sans)
    f.setPixelSize(px)
    f.setWeight({
        "light": QFont.Weight.Light,
        "regular": QFont.Weight.Normal,
        "semibold": QFont.Weight.DemiBold,
    }.get(weight, QFont.Weight.Normal))
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


def body_font() -> QFont:
    return font(14)


def label_font() -> QFont:
    """12px/16px labels, letter-spacing .32px"""
    return font(12, spacing=0.32)


def heading_font() -> QFont:
    return font(14, "semibold")


def title_font() -> QFont:
    return font(20, "light")


def mono_font(px: int = 14) -> QFont:
    return font(px, mono=True)


def stylesheet() -> str:
    """App-wide QSS: colors and borders only. Fonts are set with setFont so
    per-widget sizes are never overridden by the sheet."""
    c = Carbon
    return f"""
        QMainWindow, QWidget#page, QStackedWidget {{ background: {c.BACKGROUND}; }}
        QWidget {{ color: {c.TEXT_PRIMARY}; }}
        QLabel {{ background: transparent; }}
        QToolTip {{
            background: {c.LAYER_02}; color: {c.TEXT_PRIMARY};
            border: 0; padding: 8px 16px;
        }}
        QScrollArea {{ background: transparent; border: 0; }}
        QScrollArea > QWidget > QWidget {{ background: transparent; }}
        QScrollBar:vertical {{ background: {c.BACKGROUND}; width: 8px; margin: 0; border: 0; }}
        QScrollBar::handle:vertical {{ background: {c.LAYER_02}; min-height: 24px; }}
        QScrollBar::handle:vertical:hover {{ background: {c.TEXT_PLACEHOLDER}; }}
        QScrollBar:horizontal {{ background: {c.BACKGROUND}; height: 8px; margin: 0; border: 0; }}
        QScrollBar::handle:horizontal {{ background: {c.LAYER_02}; min-width: 24px; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
        QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

        QTableWidget {{
            background: transparent; border: 0; outline: 0;
            gridline-color: transparent; color: {c.TEXT_PRIMARY};
            selection-background-color: {c.LAYER_02}; selection-color: {c.TEXT_PRIMARY};
        }}
        QTableWidget[rowbg="layer"]::item {{
            background: {c.LAYER_01}; border: 0; border-bottom: 1px solid {c.BORDER_SUBTLE};
            padding: 0;
        }}
        QTableWidget[rowbg="none"]::item {{
            background: transparent; border: 0; border-bottom: 1px solid {c.BORDER_SUBTLE};
            padding: 0;
        }}
        QTableWidget::item:selected {{ background: {c.LAYER_02}; }}
        QTableWidget[selectable="true"]::item:hover {{ background: {c.LAYER_HOVER_01}; }}
        QTableWidget[selectable="true"]::item:selected {{ background: {c.LAYER_02}; }}
        QHeaderView {{ background: transparent; border: 0; }}
        QHeaderView::section {{
            background: {c.LAYER_02}; color: {c.TEXT_PRIMARY};
            border: 0; padding: 0 16px;
        }}
        QTableCornerButton::section {{ background: {c.LAYER_02}; border: 0; }}

        QLineEdit {{
            background: transparent; border: 0; color: {c.TEXT_PRIMARY};
            padding: 0 16px; selection-background-color: {c.INTERACTIVE};
        }}
        QLineEdit:focus {{ border: 2px solid {c.FOCUS}; padding: 0 14px; }}

        QFrame#rule {{ background: {c.BORDER_SUBTLE}; border: 0; }}
        QFrame#header {{ background: {c.BACKGROUND}; border: 0; border-bottom: 1px solid {c.BORDER_SUBTLE}; }}
        QFrame#footer {{ background: {c.LAYER_01}; border: 0; border-top: 1px solid {c.BORDER_SUBTLE}; }}
        QFrame#footer QLabel {{ color: {c.TEXT_SECONDARY}; padding: 0 16px; }}
        QFrame#footer QLabel[sep="true"] {{ border-left: 1px solid {c.BORDER_SUBTLE}; }}
        QFrame#settingRow {{ border: 0; border-bottom: 1px solid {c.BORDER_SUBTLE}; }}
        QWidget#gapGrid {{ background: {c.BORDER_SUBTLE}; }}
        QWidget#tile {{ background: {c.LAYER_01}; }}
        QFrame#stepper {{ background: {c.LAYER_01}; border: 0; border-bottom: 1px solid {c.FIELD_BORDER}; }}
    """


# ----------------------------------------------------------------- formatting

def short_number(value, signed: bool = False) -> str:
    """132120000000 -> '132.12B', 412000 -> '412K', 2708 -> '2,708'."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "-"
    sign = "-" if n < 0 else ("+" if signed and n > 0 else "")
    n = abs(n)
    if n < 10_000:
        return f"{sign}{n:,.0f}"
    for limit, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= limit:
            text = f"{n / limit:.2f}".rstrip("0").rstrip(".")
            return f"{sign}{text}{suffix}"
    return f"{sign}{n:,.0f}"


def compact_number(value) -> str:
    """Settings values: 100000 -> '100K', 1500000 -> '1.5M', 20 -> '20'."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "-"
    for limit, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(n) >= limit:
            return f"{n / limit:.2f}".rstrip("0").rstrip(".") + suffix
    return f"{n:.2f}".rstrip("0").rstrip(".")


def parse_number(text: str) -> Optional[float]:
    """'100K' -> 100000, '1.5m' -> 1500000, '25%' -> 25, '10x' -> 10."""
    t = (text or "").strip().replace(",", "").replace("×", "").rstrip("%xX").strip()
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*([kKmMbBtT]?)", t)
    if not m:
        return None
    mult = {"": 1, "k": 1e3, "m": 1e6, "b": 1e9, "t": 1e12}[m.group(2).lower()]
    return float(m.group(1)) * mult


def full_number(value) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "-"


def duration(seconds) -> str:
    """45 -> '45s', 250 -> '4m', 40000 -> '11h', 200000 -> '2d'"""
    try:
        s = max(0, int(seconds))
    except (TypeError, ValueError):
        return "-"
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m"
    if s < 86400:
        return f"{s // 3600}h"
    return f"{s // 86400}d"


def clock(seconds) -> str:
    """161 -> '2:41', 3725 -> '1:02:05'"""
    try:
        s = max(0, int(seconds))
    except (TypeError, ValueError):
        return "-"
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def spaced(name) -> str:
    """'CommonEgg' -> 'Common Egg', 'SellBoostIII' -> 'Sell Boost III'"""
    s = str(name or "")
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)
    return re.sub(r"(?<=[a-zA-Z])(?=\d)", " ", s).replace("_", " ")
