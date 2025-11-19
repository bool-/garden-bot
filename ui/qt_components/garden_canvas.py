"""
Garden Canvas Widget

Renders the garden grid with plants, pets, and player position.
"""

import time
from typing import Optional

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGroupBox, QSizePolicy
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QBrush

from game_state import GameState
from config import HarvestConfig
from utils.coordinates import convert_server_to_local_coords
from utils.constants import SPAWN_POSITIONS
from .theme import VSCodeTheme


class GardenCanvas(QWidget):
    """Custom widget for rendering the garden grid"""

    def __init__(self, game_state: GameState, harvest_config: Optional[HarvestConfig] = None, slot_index: Optional[int] = None):
        super().__init__()
        self.game_state = game_state
        self.harvest_config = harvest_config
        self.player_slot = None
        self.slot_index = slot_index  # Specific slot index for coordinate conversion

        # Grid configuration
        self.base_tile_size = 28
        self.visual_cols = 23
        self.visual_rows = 12
        self.border_offset = 2

        # Theme colors
        self.theme = VSCodeTheme

    def sizeHint(self):
        """Provide size hint for layout"""
        width = self.visual_cols * self.base_tile_size + self.border_offset * 2
        height = self.visual_rows * self.base_tile_size + self.border_offset * 2
        return QSize(width, height)

    def minimumSizeHint(self):
        """Provide minimum size hint"""
        width = self.visual_cols * 20 + self.border_offset * 2  # Minimum 20px tiles
        height = self.visual_rows * 20 + self.border_offset * 2
        return QSize(width, height)

    def set_player_slot(self, player_slot):
        """Update player slot data and trigger repaint"""
        self.player_slot = player_slot
        self.update()

    def _convert_server_to_local_for_slot(self, server_x: int, server_y: int) -> Optional[dict]:
        """Convert server coordinates to local coordinates for this canvas's slot.

        Args:
            server_x: Server X coordinate
            server_y: Server Y coordinate

        Returns:
            Dict with 'x' and 'y' local coordinates, or None if conversion fails
        """
        slot_idx = self.slot_index
        if slot_idx is None:
            # Use game state's current slot if not specified
            slot_idx = self.game_state.get_user_slot_index()

        if slot_idx is None or slot_idx >= len(SPAWN_POSITIONS):
            return None

        if server_x is None or server_y is None:
            return None

        # Get spawn position for this slot
        spawn_pos = SPAWN_POSITIONS[slot_idx]
        local_spawn = {"x": 11, "y": 11}  # Player spawns at bottom center

        # Convert: local = local_spawn + (server - spawn_pos)
        local_x = local_spawn["x"] + (server_x - spawn_pos["x"])
        local_y = local_spawn["y"] + (server_y - spawn_pos["y"])
        return {"x": int(local_x), "y": int(local_y)}

    def paintEvent(self, event):
        """Render the garden grid"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        painter.fillRect(self.rect(), self.theme.get_qcolor(self.theme.GARDEN_BG))

        if not self.player_slot:
            painter.setPen(self.theme.get_qcolor(self.theme.TEXT_SECONDARY))
            painter.setFont(QFont("Segoe UI", 12))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Waiting for game state...")
            return

        slot_data = self.player_slot.get("data", {})
        garden_data = slot_data.get("garden", {})
        tile_objects = garden_data.get("tileObjects", {})

        # Build position map for fast lookup
        position_map = self._build_tile_position_map(tile_objects)

        # Get config
        min_mutations = self.harvest_config.min_mutations if self.harvest_config else 3

        # Calculate dynamic tile size to fill available space
        available_width = self.width()
        available_height = self.height()

        # Calculate tile size based on both dimensions and use the smaller one
        # This ensures the grid fits completely without being cut off
        tile_size_w = available_width / self.visual_cols
        tile_size_h = available_height / self.visual_rows
        tile_size_float = min(tile_size_w, tile_size_h)
        tile_size_float = max(tile_size_float, 10)  # Minimum tile size of 10px

        # Calculate total grid size and center it
        total_width = tile_size_float * self.visual_cols
        total_height = tile_size_float * self.visual_rows
        offset_x = (available_width - total_width) / 2
        offset_y = (available_height - total_height) / 2

        # Draw grid
        for row in range(self.visual_rows):
            for col in range(self.visual_cols):
                x = int(offset_x + col * tile_size_float)
                y = int(offset_y + row * tile_size_float)

                # Check if boardwalk
                is_boardwalk = row in (0, self.visual_rows - 1) or col in (0, self.visual_cols - 1, 11)

                if is_boardwalk:
                    fill_color = self.theme.get_qcolor(self.theme.GARDEN_BOARDWALK)
                    outline_color = self.theme.get_qcolor(self.theme.GARDEN_BOARDWALK_BORDER)
                else:
                    # Check for tile object
                    tile_info = position_map.get((row, col))
                    if tile_info:
                        _, tile_obj = tile_info
                        fill_color, outline_color = self._get_tile_color(tile_obj, min_mutations)
                    else:
                        fill_color = self.theme.get_qcolor(self.theme.GARDEN_EMPTY)
                        outline_color = self.theme.get_qcolor(self.theme.GARDEN_EMPTY_BORDER)

                # Draw tile - calculate width/height to fill to edge
                tile_width = int(offset_x + (col + 1) * tile_size_float) - x
                tile_height = int(offset_y + (row + 1) * tile_size_float) - y

                painter.setBrush(QBrush(fill_color))
                painter.setPen(QPen(outline_color, 1))
                painter.drawRect(x, y, tile_width, tile_height)

                # Draw mutation indicators
                if not is_boardwalk:
                    tile_info = position_map.get((row, col))
                    if tile_info:
                        _, tile_obj = tile_info
                        if tile_obj.get("objectType") == "plant":
                            slots = tile_obj.get("slots", [])
                            if slots:
                                # Get max mutations
                                max_mutations = []
                                for slot in slots:
                                    if slot:
                                        mutations = slot.get("mutations", [])
                                        if len(mutations) > len(max_mutations):
                                            max_mutations = mutations

                                if max_mutations:
                                    self._draw_mutation_indicators(painter, x, y, tile_size_float, max_mutations)

        # Draw overlays (pets and player)
        self._draw_pets(painter, tile_size_float, offset_x, offset_y)
        self._draw_player(painter, tile_size_float, offset_x, offset_y)

        painter.end()

    def _build_tile_position_map(self, tile_objects, garden_cols=20):
        """Build map from visual position to tile object"""
        position_map = {}

        for tid, obj in tile_objects.items():
            if tid.isdigit():
                tile_id = int(tid)
                row = tile_id // garden_cols
                col = tile_id % garden_cols

                # Convert to visual position
                visual_row = row + 1
                visual_col = col + 1 if col < 10 else col + 2

                position_map[(visual_row, visual_col)] = (tid, obj)

        return position_map

    def _get_tile_color(self, tile_obj, min_mutations):
        """Determine fill and outline color for tile"""
        current_time = int(time.time() * 1000)
        obj_type = tile_obj.get("objectType")

        if obj_type == "plant":
            slots = tile_obj.get("slots", [])
            if slots:
                # Find best slot
                best_slot = None
                max_mutation_count = -1

                for slot in slots:
                    if not slot:
                        continue

                    mutations = slot.get("mutations", [])
                    mutation_count = len(mutations)

                    if mutation_count > max_mutation_count:
                        max_mutation_count = mutation_count
                        best_slot = slot

                if best_slot:
                    end_time = best_slot.get("endTime", 0)
                    mutations = best_slot.get("mutations", [])
                    mutation_count = len(mutations)

                    if current_time >= end_time:
                        if mutation_count >= min_mutations:
                            return (self.theme.get_qcolor(self.theme.GARDEN_READY),
                                    self.theme.get_qcolor(self.theme.GARDEN_READY_BORDER))
                        else:
                            return (self.theme.get_qcolor(self.theme.GARDEN_GROWN),
                                    self.theme.get_qcolor(self.theme.GARDEN_GROWN_BORDER))
                    else:
                        return (self.theme.get_qcolor(self.theme.GARDEN_GROWING),
                                self.theme.get_qcolor(self.theme.GARDEN_GROWING_BORDER))
                else:
                    return (self.theme.get_qcolor(self.theme.GARDEN_EMPTY),
                            self.theme.get_qcolor(self.theme.GARDEN_EMPTY_BORDER))
            else:
                return (self.theme.get_qcolor(self.theme.GARDEN_EMPTY),
                        self.theme.get_qcolor(self.theme.GARDEN_EMPTY_BORDER))

        elif obj_type == "egg":
            matured_at = tile_obj.get("maturedAt", 0)
            if current_time >= matured_at:
                return (self.theme.get_qcolor(self.theme.GARDEN_EGG_READY),
                        self.theme.get_qcolor(self.theme.GARDEN_EGG_READY_BORDER))
            else:
                return (self.theme.get_qcolor(self.theme.GARDEN_EGG_GROWING),
                        self.theme.get_qcolor(self.theme.GARDEN_EGG_GROWING_BORDER))

        elif obj_type == "pet":
            return (self.theme.get_qcolor(self.theme.GARDEN_PET),
                    self.theme.get_qcolor(self.theme.GARDEN_PET_BORDER))

        else:
            return (self.theme.get_qcolor(self.theme.GARDEN_EMPTY),
                    self.theme.get_qcolor(self.theme.GARDEN_EMPTY_BORDER))

    def _draw_mutation_indicators(self, painter, x, y, tile_size, mutations):
        """Draw mutation indicators on tile"""
        # Convert tile_size to int for all calculations
        tile_size = int(tile_size)
        indicator_size = max(tile_size // 4, 3)

        # Rainbow indicator (top-right)
        if "Rainbow" in mutations:
            indicator_x = x + tile_size - indicator_size - 2
            indicator_y = y + 2
            stripe_height = max(indicator_size // len(self.theme.MUTATION_RAINBOW), 1)

            for i, color in enumerate(self.theme.MUTATION_RAINBOW):
                painter.fillRect(
                    indicator_x,
                    indicator_y + i * stripe_height,
                    indicator_size,
                    stripe_height,
                    QColor(color)
                )

        # Gold indicator
        if "Gold" in mutations:
            indicator_x = x + 2 if "Rainbow" in mutations else x + tile_size - indicator_size - 2
            indicator_y = y + 2
            painter.setBrush(QBrush(self.theme.get_qcolor(self.theme.MUTATION_GOLD)))
            painter.setPen(QPen(self.theme.get_qcolor(self.theme.MUTATION_GOLD_BORDER), 1))
            painter.drawEllipse(indicator_x, indicator_y, indicator_size, indicator_size)

        # Water states (left side)
        water_states = {
            "Frozen": self.theme.MUTATION_FROZEN,
            "Chilled": self.theme.MUTATION_CHILLED,
            "Wet": self.theme.MUTATION_WET,
        }
        for state, color in water_states.items():
            if state in mutations:
                indicator_x = x + 2
                indicator_y = y + tile_size // 2 - indicator_size // 2
                painter.setBrush(QBrush(self.theme.get_qcolor(color)))
                painter.setPen(QPen(QColor("#FFFFFF"), 1))
                painter.drawEllipse(indicator_x, indicator_y, indicator_size, indicator_size)
                break

        # Light states (bottom)
        light_states = {
            "Ambershine": self.theme.MUTATION_AMBERSHINE,
            "Dawnlit": self.theme.MUTATION_DAWNLIT,
        }
        for state, color in light_states.items():
            if state in mutations:
                indicator_x = x + tile_size // 2 - indicator_size // 2
                indicator_y = y + tile_size - indicator_size - 2
                painter.setBrush(QBrush(self.theme.get_qcolor(color)))
                painter.setPen(QPen(QColor("#FFFFFF"), 1))
                painter.drawEllipse(indicator_x, indicator_y, indicator_size, indicator_size)
                break

    def _draw_pets(self, painter, tile_size, offset_x, offset_y):
        """Draw pet markers"""
        if not self.player_slot:
            return

        pet_slot_infos = self.player_slot.get("petSlotInfos")
        if not isinstance(pet_slot_infos, dict):
            return

        for slot_info in pet_slot_infos.values():
            if not isinstance(slot_info, dict):
                continue

            position = slot_info.get("position")
            if not isinstance(position, dict):
                continue

            # Use slot-specific coordinate conversion
            local_coords = self._convert_server_to_local_for_slot(
                position.get("x"), position.get("y")
            )
            if not local_coords:
                continue

            local_x, local_y = local_coords.get("x"), local_coords.get("y")
            if local_x < 0 or local_x > 22 or local_y < 0 or local_y > 11:
                continue

            # Use float calculations for accurate positioning
            center_x = int(offset_x + local_x * tile_size + tile_size / 2)
            center_y = int(offset_y + local_y * tile_size + tile_size / 2)
            radius = max(int(tile_size / 3), 4)

            painter.setBrush(QBrush(self.theme.get_qcolor(self.theme.GARDEN_PET)))
            painter.setPen(QPen(self.theme.get_qcolor(self.theme.GARDEN_PET_BORDER), 2))
            painter.drawEllipse(center_x - radius, center_y - radius, radius * 2, radius * 2)

    def _draw_player(self, painter, tile_size, offset_x, offset_y):
        """Draw player marker"""
        if not self.player_slot:
            return

        player_pos = self.player_slot.get("position")
        if not isinstance(player_pos, dict):
            return

        server_x, server_y = player_pos.get("x"), player_pos.get("y")
        if server_x is None or server_y is None:
            return

        # Use slot-specific coordinate conversion
        local_coords = self._convert_server_to_local_for_slot(server_x, server_y)
        if not local_coords:
            return

        player_x, player_y = local_coords.get("x", -1), local_coords.get("y", -1)
        if player_x < 0 or player_y < 0:
            return

        # Use float calculations for accurate positioning
        center_x = int(offset_x + player_x * tile_size + tile_size / 2)
        center_y = int(offset_y + player_y * tile_size + tile_size / 2)
        radius = max(int(tile_size / 3), 4)

        painter.setBrush(QBrush(self.theme.get_qcolor(self.theme.GARDEN_PLAYER)))
        painter.setPen(QPen(self.theme.get_qcolor(self.theme.GARDEN_PLAYER_BORDER), 2))
        painter.drawEllipse(center_x - radius, center_y - radius, radius * 2, radius * 2)


class GardenWidget(QWidget):
    """Complete garden widget with canvas and legend"""

    def __init__(self, game_state: GameState, harvest_config: Optional[HarvestConfig] = None):
        super().__init__()
        self.game_state = game_state
        self.harvest_config = harvest_config
        self.theme = VSCodeTheme

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Group box
        group = QGroupBox("🌻 Garden View")
        group_layout = QVBoxLayout()
        group_layout.setContentsMargins(12, 16, 12, 12)
        group_layout.setSpacing(8)

        # Garden canvas with expanding size policy - fills available space
        self.canvas = GardenCanvas(game_state, harvest_config)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        group_layout.addWidget(self.canvas, stretch=1)  # No alignment = fills space

        # Legend
        legend_widget = self._create_legend()
        group_layout.addWidget(legend_widget)

        group.setLayout(group_layout)
        main_layout.addWidget(group)
        self.setLayout(main_layout)

    def set_player_slot(self, player_slot):
        """Update player slot data"""
        self.canvas.set_player_slot(player_slot)

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
