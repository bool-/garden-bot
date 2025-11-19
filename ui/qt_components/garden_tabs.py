"""
Garden Tabs Widget

Tabbed interface for viewing multiple players' gardens.
"""

from typing import Optional

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QGroupBox, QLabel, QFrame
from PyQt6.QtCore import Qt

from game_state import GameState
from config import HarvestConfig
from .garden_canvas import GardenCanvas
from .theme import VSCodeTheme


class GardenTabs(QWidget):
    """Tabbed garden view widget for displaying multiple players' gardens"""

    def __init__(self, game_state: GameState, harvest_config: Optional[HarvestConfig] = None):
        super().__init__()
        self.game_state = game_state
        self.harvest_config = harvest_config
        self.theme = VSCodeTheme

        # Store canvas instances by player_id
        self.canvases = {}

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Group box
        group = QGroupBox("🌻 Garden Views")
        group_layout = QVBoxLayout()
        group_layout.setContentsMargins(12, 16, 12, 12)
        group_layout.setSpacing(8)

        # Tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)
        group_layout.addWidget(self.tab_widget)

        # Legend
        legend_widget = self._create_legend()
        group_layout.addWidget(legend_widget)

        group.setLayout(group_layout)
        main_layout.addWidget(group)
        self.setLayout(main_layout)

    def update_gardens(self):
        """Update all garden tabs with latest data from all user slots"""
        all_slots = self.game_state.get_all_user_slots()
        current_player_id = self.game_state.get_player_id()

        if not all_slots:
            # Clear all tabs if no data
            self.tab_widget.clear()
            self.canvases.clear()
            return

        # Track which player IDs we've seen
        active_player_ids = set()

        # Update or create tabs for each slot
        for slot_index, slot in enumerate(all_slots):
            player_id = slot.get("playerId")
            if not player_id:
                continue

            active_player_ids.add(player_id)

            # Get player name
            player_name = self.game_state.get_player_name_by_id(player_id)
            if not player_name:
                player_name = player_id

            # Add "(You)" to current player's tab
            is_current_player = (player_id == current_player_id)
            tab_label = f"{player_name} (You)" if is_current_player else player_name

            # Create or update canvas for this player
            if player_id not in self.canvases:
                # Create new canvas with slot index for coordinate conversion
                canvas = GardenCanvas(self.game_state, self.harvest_config, slot_index=slot_index)
                self.canvases[player_id] = canvas

                # Add tab - current player's tab goes first
                if is_current_player:
                    self.tab_widget.insertTab(0, canvas, tab_label)
                else:
                    self.tab_widget.addTab(canvas, tab_label)
            else:
                # Update existing tab label in case name changed
                canvas = self.canvases[player_id]
                # Update slot index (in case player moved slots somehow)
                canvas.slot_index = slot_index
                for i in range(self.tab_widget.count()):
                    if self.tab_widget.widget(i) == canvas:
                        self.tab_widget.setTabText(i, tab_label)
                        # Move current player's tab to first position if needed
                        if is_current_player and i != 0:
                            self.tab_widget.removeTab(i)
                            self.tab_widget.insertTab(0, canvas, tab_label)
                            self.tab_widget.setCurrentIndex(0)
                        break

            # Update canvas with slot data
            canvas.set_player_slot(slot)

        # Remove tabs for players who left
        player_ids_to_remove = []
        for player_id in self.canvases.keys():
            if player_id not in active_player_ids:
                player_ids_to_remove.append(player_id)

        for player_id in player_ids_to_remove:
            canvas = self.canvases[player_id]
            # Find and remove the tab
            for i in range(self.tab_widget.count()):
                if self.tab_widget.widget(i) == canvas:
                    self.tab_widget.removeTab(i)
                    break
            del self.canvases[player_id]

    def _create_legend(self):
        """Create the color legend"""
        legend_widget = QWidget()
        legend_widget.setMaximumHeight(35)
        legend_layout = QHBoxLayout(legend_widget)
        legend_layout.setContentsMargins(0, 5, 0, 5)
        legend_layout.setSpacing(12)

        legend_items = [
            (self.theme.GARDEN_PLAYER, "You"),
            (self.theme.GARDEN_READY, "Ready"),
            (self.theme.GARDEN_GROWN, "Grown"),
            (self.theme.GARDEN_GROWING, "Growing"),
            (self.theme.GARDEN_EGG_READY, "Ready Egg"),
            (self.theme.GARDEN_EGG_GROWING, "Growing Egg"),
            (self.theme.GARDEN_PET, "Pet"),
            (self.theme.GARDEN_EMPTY, "Empty"),
        ]

        for color, label in legend_items:
            item_layout = QHBoxLayout()
            item_layout.setSpacing(4)

            # Color square
            color_widget = QFrame()
            color_widget.setFixedSize(12, 12)
            color_widget.setStyleSheet(
                f"background-color: {color}; "
                f"border: 1px solid {self.theme.BORDER};"
            )

            # Label
            text_label = QLabel(label)
            text_label.setStyleSheet(f"color: {self.theme.TEXT_SECONDARY}; font-size: 8pt;")

            item_layout.addWidget(color_widget)
            item_layout.addWidget(text_label)

            legend_layout.addLayout(item_layout)

        legend_layout.addStretch()
        return legend_widget
