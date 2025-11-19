"""
PyQt6 GUI for Magic Garden Bot

Modern, component-based UI with VS Code Dark+ theme.
"""

import sys
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStatusBar, QTabWidget, QSplitter, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor

from game_state import GameState
from config import HarvestConfig
from .qt_components import (
    VSCodeTheme,
    GardenWidget,
    ConnectionPanel,
    InventoryPanel,
    PetPanel,
    ShopPanel,
    JournalPanel,
    StatsPanel,
    ConsoleWidget,
    ConsoleRedirector
)


class MagicGardenGUI(QMainWindow):
    """Main PyQt6 GUI window for Magic Garden Bot"""

    def __init__(self, game_state: GameState, harvest_config: Optional[HarvestConfig] = None):
        super().__init__()
        self.game_state = game_state
        self.harvest_config = harvest_config
        self.theme = VSCodeTheme

        self.setWindowTitle("Magic Garden Bot")
        self.resize(1400, 900)
        self.setMinimumSize(1000, 700)  # Minimum size for usability

        # Set window icon
        self.setWindowIcon(self._create_icon())

        # Apply theme
        self.setStyleSheet(self.theme.get_stylesheet())

        # Setup UI
        self.setup_ui()

        # Redirect stdout
        sys.stdout = ConsoleRedirector(self.console_widget.get_queue(), sys.stdout)

        # Setup update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_ui)
        self.update_timer.start(500)  # Update every 500ms

    def setup_ui(self):
        """Setup the user interface"""
        # Central widget with splitter layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Create splitter for resizable panels
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # LEFT PANEL
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        # Connection panel (fixed size, doesn't expand)
        self.connection_panel = ConnectionPanel(self.game_state)
        self.connection_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        left_layout.addWidget(self.connection_panel)

        # Garden widget (priority expansion)
        self.garden_widget = GardenWidget(self.game_state, self.harvest_config)
        self.garden_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        left_layout.addWidget(self.garden_widget, stretch=3)

        # Console widget (secondary expansion)
        self.console_widget = ConsoleWidget()
        self.console_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        left_layout.addWidget(self.console_widget, stretch=1)

        splitter.addWidget(left_panel)

        # RIGHT PANEL - Tabs (fixed size, doesn't expand)
        right_panel = QTabWidget()
        right_panel.setDocumentMode(True)
        right_panel.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        right_panel.setFixedWidth(486)  # Fixed width - calculated for clean garden tile rendering

        # Tab 1: Inventory
        self.inventory_panel = InventoryPanel()
        right_panel.addTab(self.inventory_panel, "🎒 Inventory")

        # Tab 2: Pets
        self.pet_panel = PetPanel()
        right_panel.addTab(self.pet_panel, "🐾 Pets")

        # Tab 3: Shop
        self.shop_panel = ShopPanel()
        right_panel.addTab(self.shop_panel, "🛒 Shop")

        # Tab 4: Journal
        self.journal_panel = JournalPanel()
        right_panel.addTab(self.journal_panel, "📖 Journal")

        # Tab 5: Stats
        self.stats_panel = StatsPanel()
        right_panel.addTab(self.stats_panel, "📊 Stats")

        splitter.addWidget(right_panel)

        # Set splitter sizes (calculated for clean garden tile rendering at min window size)
        splitter.setSizes([914, 486])

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def extract_player_data(self):
        """Extract player data from game state"""
        return self.game_state.get_player_slot()

    def update_ui(self):
        """Update UI with current game state"""
        # Update connection panel
        self.connection_panel.update_data()

        # Extract player slot
        player_slot = self.extract_player_data()

        if not player_slot:
            # Waiting for game state
            self.garden_widget.set_player_slot(None)
            return

        # Update garden
        self.garden_widget.set_player_slot(player_slot)

        # Get slot data
        slot_data = player_slot.get("data", {})

        # Update inventory panel
        self.inventory_panel.update_data(slot_data)

        # Update pet panel
        self.pet_panel.update_data(slot_data)

        # Update shop panel with quinoa-level data (shops are shared across all players)
        full_state = self.game_state["full_state"]
        if full_state:
            child_state = full_state.get("child", {})
            quinoa_data = child_state.get("data", {})
            self.shop_panel.update_data(quinoa_data)
        else:
            self.shop_panel.update_data({})

        # Update journal panel
        self.journal_panel.update_data(slot_data)

        # Update stats panel
        self.stats_panel.update_data(slot_data)

    def _create_icon(self):
        """Create a simple garden-themed icon"""
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw a simple plant/flower icon
        # Stem
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.theme.GARDEN_READY))
        painter.drawRect(28, 32, 8, 24)

        # Flower petals (circle)
        painter.setBrush(QColor(self.theme.GARDEN_GROWING))
        painter.drawEllipse(16, 16, 32, 32)

        # Center
        painter.setBrush(QColor(self.theme.ACCENT_BLUE))
        painter.drawEllipse(24, 24, 16, 16)

        painter.end()
        return QIcon(pixmap)
