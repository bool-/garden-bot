"""
Connection Panel Component

Displays player info and connection statistics.
"""

from PyQt6.QtWidgets import QWidget, QGridLayout, QLabel, QGroupBox, QVBoxLayout
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt

from game_state import GameState
from .theme import VSCodeTheme


class ConnectionPanel(QWidget):
    """Panel showing player and connection information"""

    def __init__(self, game_state: GameState):
        super().__init__()
        self.game_state = game_state
        self.theme = VSCodeTheme

        self.setup_ui()

    def setup_ui(self):
        """Setup the UI"""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # Group box
        group = QGroupBox("👤 Player & Connection")
        grid = QGridLayout()
        grid.setSpacing(8)
        grid.setContentsMargins(12, 16, 12, 12)

        # Create labels
        self.player_name_label = QLabel("Unknown")
        self.player_id_label = QLabel("Unknown")
        self.room_id_label = QLabel("Unknown")
        self.player_count_label = QLabel("0/6")
        self.ping_pong_label = QLabel("↑0 / ↓0")
        self.messages_label = QLabel("↑0 / ↓0")
        self.patches_label = QLabel("0")
        self.last_update_label = QLabel("Never")

        # Row 0: Player info
        grid.addWidget(self._create_label("Player:", bold=True), 0, 0)
        grid.addWidget(self.player_name_label, 0, 1)
        grid.addWidget(self._create_label("ID:", bold=True), 0, 2)
        grid.addWidget(self.player_id_label, 0, 3)

        # Row 1: Room info
        grid.addWidget(self._create_label("Room:", bold=True), 1, 0)
        grid.addWidget(self.room_id_label, 1, 1)
        grid.addWidget(self._create_label("Players:", bold=True), 1, 2)
        grid.addWidget(self.player_count_label, 1, 3)

        # Row 2: Network stats
        grid.addWidget(self._create_label("Ping/Pong:", bold=True), 2, 0)
        grid.addWidget(self.ping_pong_label, 2, 1)
        grid.addWidget(self._create_label("Messages:", bold=True), 2, 2)
        grid.addWidget(self.messages_label, 2, 3)

        # Row 3: Updates
        grid.addWidget(self._create_label("Patches:", bold=True), 3, 0)
        grid.addWidget(self.patches_label, 3, 1)
        grid.addWidget(self._create_label("Last Update:", bold=True), 3, 2)
        grid.addWidget(self.last_update_label, 3, 3)

        group.setLayout(grid)
        layout.addWidget(group)
        self.setLayout(layout)

    def _create_label(self, text: str, bold: bool = False) -> QLabel:
        """Create a styled label"""
        label = QLabel(text)
        if bold:
            font = label.font()
            font.setBold(True)
            label.setFont(font)
            label.setStyleSheet(f"color: {self.theme.ACCENT_TEAL};")
        return label

    def update_data(self):
        """Update panel with latest data"""
        # Player info
        player_id = self.game_state.get("player_id")
        self.player_id_label.setText(player_id or "Unknown")
        display_name = self.game_state.get("player_name") or player_id or "Unknown"
        self.player_name_label.setText(display_name)

        # Connection stats
        stats = self.game_state["statistics"]
        self.ping_pong_label.setText(f"↑{stats['pings_sent']:,} / ↓{stats['pongs_received']:,}")
        self.messages_label.setText(f"↑{stats['messages_sent']:,} / ↓{stats['messages_received']:,}")
        self.patches_label.setText(f"{stats['patches_applied']:,}")
        self.last_update_label.setText(stats["last_update"])

        # Room info
        room_id = self.game_state.get("room_id", "Unknown")
        self.room_id_label.setText(room_id)

        # Player count
        player_count = 0
        full_state = self.game_state["full_state"]
        if full_state:
            room_data = full_state.get("data", {})
            players = room_data.get("players", [])
            player_count = sum(1 for p in players if p is not None)
        self.player_count_label.setText(f"{player_count}/6")
