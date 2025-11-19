"""
Stats Panel Component

Displays game statistics and achievements.
"""

from PyQt6.QtWidgets import QWidget, QTextEdit, QVBoxLayout

from .theme import VSCodeTheme


class StatsPanel(QWidget):
    """Panel for displaying game stats"""

    def __init__(self):
        super().__init__()
        self.theme = VSCodeTheme
        self._last_content = ""  # Track last content to prevent unnecessary updates

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        layout.addWidget(self.text_edit)

        self.setLayout(layout)

    def update_data(self, slot_data: dict):
        """Update game stats"""
        text = []

        stats = slot_data.get("stats", {})
        player_stats = stats.get("player", {})

        text.append(f"Crops Harvested: {player_stats.get('numCropsHarvested', 0):,}")
        text.append(f"Seeds Planted: {player_stats.get('numSeedsPlanted', 0):,}")
        text.append(f"Pets Sold: {player_stats.get('numPetsSold', 0):,}")
        text.append(f"Eggs Hatched: {player_stats.get('numEggsHatched', 0):,}")

        total_earnings = (
            player_stats.get("totalEarningsSellCrops", 0) +
            player_stats.get("totalEarningsSellPet", 0)
        )
        text.append(f"Total Earnings: {total_earnings:,} coins")

        # Only update if content changed (prevents interrupting copy/paste)
        new_content = "\n".join(text)
        if new_content != self._last_content:
            self._last_content = new_content
            # Save scroll position
            scrollbar = self.text_edit.verticalScrollBar()
            scroll_pos = scrollbar.value()
            # Update content
            self.text_edit.setPlainText(new_content)
            # Restore scroll position
            scrollbar.setValue(scroll_pos)
