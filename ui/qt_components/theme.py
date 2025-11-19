"""
VS Code Dark+ inspired theme for Magic Garden Bot

Color palette based on Visual Studio Code's Dark+ theme.
"""

from PyQt6.QtGui import QColor


class VSCodeTheme:
    """VS Code Dark+ color theme"""

    # Base colors
    BG_EDITOR = "#1e1e1e"           # Main editor background
    BG_SIDEBAR = "#252526"          # Sidebar background
    BG_PANEL = "#1e1e1e"            # Panel background
    BG_ACTIVITY_BAR = "#333333"     # Activity bar
    BG_INPUT = "#3c3c3c"            # Input fields
    BG_HOVER = "#2a2d2e"            # Hover state

    # Borders
    BORDER = "#3e3e42"              # Standard border
    BORDER_ACTIVE = "#007acc"       # Active/focused border

    # Text colors
    TEXT_PRIMARY = "#d4d4d4"        # Main text
    TEXT_SECONDARY = "#858585"      # Secondary/muted text
    TEXT_DISABLED = "#656565"       # Disabled text

    # Accent colors
    ACCENT_BLUE = "#007acc"         # Primary accent (blue)
    ACCENT_TEAL = "#4ec9b0"         # Secondary accent (teal)
    ACCENT_ORANGE = "#ce9178"       # Tertiary accent (orange/salmon)

    # Status colors
    SUCCESS = "#89d185"             # Green - success/ready
    WARNING = "#dcdcaa"             # Yellow - warning
    ERROR = "#f48771"               # Red/salmon - error
    INFO = "#9cdcfe"                # Light blue - info

    # Garden-specific colors
    GARDEN_BG = "#1a1a1a"           # Garden canvas background
    GARDEN_BOARDWALK = "#4a4a4a"    # Boardwalk color
    GARDEN_BOARDWALK_BORDER = "#5a5a5a"
    GARDEN_EMPTY = "#2d2d30"        # Empty tile
    GARDEN_EMPTY_BORDER = "#3e3e42"
    GARDEN_READY = "#89d185"        # Ready to harvest (green)
    GARDEN_READY_BORDER = "#a0e0a0"
    GARDEN_GROWN = "#ce9178"        # Grown but not ready (orange)
    GARDEN_GROWN_BORDER = "#e0a890"
    GARDEN_GROWING = "#dcdcaa"      # Growing (yellow)
    GARDEN_GROWING_BORDER = "#f0e8b8"
    GARDEN_EGG_READY = "#4ec9b0"    # Ready egg (teal)
    GARDEN_EGG_READY_BORDER = "#60d5c0"
    GARDEN_EGG_GROWING = "#c586c0"  # Growing egg (purple)
    GARDEN_EGG_GROWING_BORDER = "#d5a0d0"
    GARDEN_PET = "#c586c0"          # Pet (purple)
    GARDEN_PET_BORDER = "#d5a0d0"
    GARDEN_PLAYER = "#007acc"       # Player (blue)
    GARDEN_PLAYER_BORDER = "#4da6e0"

    # Mutation indicator colors (bright/vibrant)
    MUTATION_RAINBOW = ["#ff0000", "#ff7f00", "#ffff00", "#00ff00", "#0000ff", "#8b00ff"]
    MUTATION_GOLD = "#ffd700"
    MUTATION_GOLD_BORDER = "#ffe55c"
    MUTATION_FROZEN = "#c7e6f5"     # Light blue
    MUTATION_CHILLED = "#6db3d8"    # Medium blue
    MUTATION_WET = "#4a90e2"        # Darker blue
    MUTATION_AMBERSHINE = "#ffb347" # Orange
    MUTATION_DAWNLIT = "#ff6b9d"    # Pink

    @classmethod
    def get_stylesheet(cls):
        """Generate the complete QSS stylesheet"""
        return f"""
            /* Main Window */
            QMainWindow {{
                background-color: {cls.BG_EDITOR};
                color: {cls.TEXT_PRIMARY};
            }}

            /* Widgets */
            QWidget {{
                background-color: {cls.BG_EDITOR};
                color: {cls.TEXT_PRIMARY};
                font-family: 'Segoe UI', 'Consolas', Arial, sans-serif;
                font-size: 10pt;
            }}

            /* Labels */
            QLabel {{
                color: {cls.TEXT_PRIMARY};
                background-color: transparent;
            }}

            /* Group Boxes */
            QGroupBox {{
                background-color: {cls.BG_SIDEBAR};
                border: 1px solid {cls.BORDER};
                border-radius: 4px;
                margin-top: 0.5em;
                padding-top: 0.75em;
                font-weight: bold;
                color: {cls.TEXT_PRIMARY};
            }}

            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                color: {cls.ACCENT_BLUE};
                background-color: {cls.BG_SIDEBAR};
                left: 10px;
            }}

            /* Text Edit / Console */
            QTextEdit {{
                background-color: {cls.BG_PANEL};
                color: {cls.TEXT_PRIMARY};
                border: 1px solid {cls.BORDER};
                border-radius: 3px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 9pt;
                selection-background-color: {cls.ACCENT_BLUE};
                selection-color: {cls.TEXT_PRIMARY};
            }}

            QTextEdit:focus {{
                border: 1px solid {cls.BORDER_ACTIVE};
            }}

            /* Scroll Bars */
            QScrollBar:vertical {{
                background-color: {cls.BG_SIDEBAR};
                width: 12px;
                border: none;
            }}

            QScrollBar::handle:vertical {{
                background-color: {cls.BG_ACTIVITY_BAR};
                min-height: 20px;
                border-radius: 2px;
            }}

            QScrollBar::handle:vertical:hover {{
                background-color: {cls.BG_HOVER};
            }}

            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}

            QScrollBar:horizontal {{
                background-color: {cls.BG_SIDEBAR};
                height: 12px;
                border: none;
            }}

            QScrollBar::handle:horizontal {{
                background-color: {cls.BG_ACTIVITY_BAR};
                min-width: 20px;
                border-radius: 2px;
            }}

            QScrollBar::handle:horizontal:hover {{
                background-color: {cls.BG_HOVER};
            }}

            /* Splitter */
            QSplitter::handle {{
                background-color: {cls.BORDER};
                width: 1px;
                height: 1px;
            }}

            QSplitter::handle:hover {{
                background-color: {cls.ACCENT_BLUE};
            }}

            /* Tabs */
            QTabWidget::pane {{
                border: 1px solid {cls.BORDER};
                background-color: {cls.BG_SIDEBAR};
                border-top: none;
            }}

            QTabBar::tab {{
                background-color: {cls.BG_SIDEBAR};
                color: {cls.TEXT_SECONDARY};
                padding: 6px 16px;
                margin-right: 2px;
                border: 1px solid {cls.BORDER};
                border-bottom: none;
                border-top-left-radius: 3px;
                border-top-right-radius: 3px;
            }}

            QTabBar::tab:selected {{
                background-color: {cls.BG_PANEL};
                color: {cls.TEXT_PRIMARY};
                border-bottom: 2px solid {cls.ACCENT_BLUE};
            }}

            QTabBar::tab:hover:!selected {{
                background-color: {cls.BG_HOVER};
                color: {cls.TEXT_PRIMARY};
            }}

            /* Status Bar */
            QStatusBar {{
                background-color: {cls.ACCENT_BLUE};
                color: white;
                border: none;
                padding: 2px;
            }}

            QStatusBar::item {{
                border: none;
            }}

            /* Buttons */
            QPushButton {{
                background-color: {cls.BG_INPUT};
                color: {cls.TEXT_PRIMARY};
                border: 1px solid {cls.BORDER};
                padding: 6px 16px;
                border-radius: 3px;
                font-weight: normal;
            }}

            QPushButton:hover {{
                background-color: {cls.BG_HOVER};
                border: 1px solid {cls.ACCENT_BLUE};
            }}

            QPushButton:pressed {{
                background-color: {cls.ACCENT_BLUE};
                color: white;
            }}

            /* Combo Box */
            QComboBox {{
                background-color: {cls.BG_INPUT};
                color: {cls.TEXT_PRIMARY};
                border: 1px solid {cls.BORDER};
                padding: 4px 8px;
                border-radius: 3px;
            }}

            QComboBox:hover {{
                border: 1px solid {cls.ACCENT_BLUE};
            }}

            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}

            QComboBox QAbstractItemView {{
                background-color: {cls.BG_INPUT};
                color: {cls.TEXT_PRIMARY};
                selection-background-color: {cls.ACCENT_BLUE};
                border: 1px solid {cls.BORDER};
            }}

            /* Frame */
            QFrame {{
                border: none;
            }}
        """

    @classmethod
    def get_qcolor(cls, color_hex: str) -> QColor:
        """Convert hex color to QColor"""
        return QColor(color_hex)
