"""
PyQt6 GUI for Magic Garden Bot

Modern, component-based UI with VS Code Dark+ theme.
"""

import sys
import asyncio
from typing import Optional, Dict, Any

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QStatusBar,
    QTabWidget,
    QSplitter,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QKeyEvent

from game_state import GameState
from config import HarvestConfig
from utils.coordinates import convert_local_to_server_coords
from .qt_components import (
    VSCodeTheme,
    GardenWidget,
    GardenTabs,
    ConnectionPanel,
    InventoryPanel,
    PetPanel,
    ShopPanel,
    JournalPanel,
    StatsPanel,
    ConsoleWidget,
    ConsoleRedirector,
)


class MagicGardenGUI(QMainWindow):
    """Main PyQt6 GUI window for Magic Garden Bot"""

    def __init__(
        self,
        game_state: GameState,
        harvest_config: Optional[HarvestConfig] = None,
        client_holder: Optional[Dict[str, Any]] = None,
    ):
        super().__init__()
        self.game_state = game_state
        self.harvest_config = harvest_config
        self.client_holder = client_holder or {}
        self.theme = VSCodeTheme

        # Local player position tracking (visual coords: x=0-22, y=0-11)
        self._local_player_pos = {"x": 11, "y": 11}

        self.setWindowTitle("Magic Garden Bot")
        self.resize(1400, 900)
        self.setMinimumSize(1000, 700)  # Minimum size for usability

        # Set application icon
        self.setWindowIcon(QIcon("magic_garden_bot.ico"))

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
        self.connection_panel.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        left_layout.addWidget(self.connection_panel)

        # Garden tabs widget (priority expansion)
        self.garden_tabs = GardenTabs(self.game_state, self.harvest_config)
        self.garden_tabs.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        left_layout.addWidget(self.garden_tabs, stretch=3)

        # Console widget (secondary expansion)
        self.console_widget = ConsoleWidget()
        self.console_widget.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        left_layout.addWidget(self.console_widget, stretch=1)

        splitter.addWidget(left_panel)

        # RIGHT PANEL - Tabs (fixed size, doesn't expand)
        right_panel = QTabWidget()
        right_panel.setDocumentMode(True)
        right_panel.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred
        )
        right_panel.setFixedWidth(
            486
        )  # Fixed width - calculated for clean garden tile rendering

        # Tab 1: Inventory
        self.inventory_panel = InventoryPanel()
        self.inventory_panel.selection_made.connect(self._on_inventory_selection)
        right_panel.addTab(self.inventory_panel, "🎒 Inventory")

        # Tab 2: Pets
        self.pet_panel = PetPanel()
        right_panel.addTab(self.pet_panel, "🐾 Pets")

        # Tab 3: Shop
        self.shop_panel = ShopPanel()
        self.shop_panel.set_client_holder(self.client_holder)
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

        # Update all garden tabs
        self.garden_tabs.update_gardens()

        # Extract player slot
        player_slot = self.extract_player_data()

        if not player_slot:
            # Waiting for game state
            return

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

    def _on_inventory_selection(self):
        """Return focus to main window after inventory selection"""
        self.setFocus()
        self.activateWindow()

    def _optimistic_move(self, new_x: int, new_y: int):
        """Optimistically update player position in local state"""
        def update(full_state):
            player_id = self.game_state.get_player_id()
            if not player_id:
                return
            child = full_state.get("child", {})
            if child.get("scope") != "Quinoa":
                return
            user_slots = child.get("data", {}).get("userSlots", [])
            for slot in user_slots:
                if slot and slot.get("playerId") == player_id:
                    slot["position"] = {"x": new_x, "y": new_y}
                    break
        self.game_state.update_full_state_locked(update)
        # Trigger immediate UI update
        self.garden_tabs.update_gardens()

    def _optimistic_harvest(self, tile_id: int):
        """Optimistically remove plant from tile"""
        def update(full_state):
            player_id = self.game_state.get_player_id()
            if not player_id:
                return
            child = full_state.get("child", {})
            if child.get("scope") != "Quinoa":
                return
            user_slots = child.get("data", {}).get("userSlots", [])
            for slot in user_slots:
                if slot and slot.get("playerId") == player_id:
                    tile_objects = slot.get("data", {}).get("garden", {}).get("tileObjects", {})
                    tile_key = str(tile_id)
                    if tile_key in tile_objects:
                        del tile_objects[tile_key]
                    break
        self.game_state.update_full_state_locked(update)
        self.garden_tabs.update_gardens()

    def _get_egg_count(self, inventory: dict, egg_id: str) -> int:
        """Get count of specific egg type in inventory"""
        items = inventory.get("items", [])
        for item in items:
            if item.get("itemType") == "Egg" and item.get("eggId") == egg_id:
                return item.get("quantity", 0)
        return 0

    def _optimistic_plant(self, tile_id: int, species: str, is_egg: bool = False):
        """Optimistically add plant/egg to tile"""
        import time
        def update(full_state):
            player_id = self.game_state.get_player_id()
            if not player_id:
                return
            child = full_state.get("child", {})
            if child.get("scope") != "Quinoa":
                return
            user_slots = child.get("data", {}).get("userSlots", [])
            for slot in user_slots:
                if slot and slot.get("playerId") == player_id:
                    tile_objects = slot.get("data", {}).get("garden", {}).get("tileObjects", {})
                    if is_egg:
                        # Add egg placeholder
                        tile_objects[str(tile_id)] = {
                            "objectType": "egg",
                            "eggId": species,
                            "maturedAt": int(time.time() * 1000) + 60000,  # 1 min placeholder
                        }
                    else:
                        # Add plant placeholder
                        tile_objects[str(tile_id)] = {
                            "objectType": "plant",
                            "slots": [{
                                "species": species,
                                "mutations": [],
                                "endTime": int(time.time() * 1000) + 60000,  # 1 min placeholder
                            }]
                        }
                    break
        self.game_state.update_full_state_locked(update)
        self.garden_tabs.update_gardens()

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

    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard input for player movement and interaction"""
        key = event.key()

        # Check if client is available
        client = self.client_holder.get("client")
        loop = self.client_holder.get("loop")

        if not client or not loop or not client.is_connected:
            super().keyPressEvent(event)
            return

        # Get current player position from game state
        player_slot = self.game_state.get_player_slot()
        if not player_slot:
            if key == Qt.Key.Key_Space:
                print("Space pressed but no player_slot")
            super().keyPressEvent(event)
            return

        current_pos = player_slot.get("position")
        if not current_pos:
            if key == Qt.Key.Key_Space:
                print("Space pressed but no current_pos in player_slot")
            super().keyPressEvent(event)
            return

        # WASD and Arrow key movement
        movement = None
        if key in (Qt.Key.Key_W, Qt.Key.Key_Up):
            movement = (0, -1)  # Up
        elif key in (Qt.Key.Key_S, Qt.Key.Key_Down):
            movement = (0, 1)  # Down
        elif key in (Qt.Key.Key_A, Qt.Key.Key_Left):
            movement = (-1, 0)  # Left
        elif key in (Qt.Key.Key_D, Qt.Key.Key_Right):
            movement = (1, 0)  # Right
        elif key == Qt.Key.Key_Space:
            # Interact with tile at current position
            print("Space pressed - calling interact")
            self._handle_interact(client, loop, player_slot)
            return

        if movement:
            dx, dy = movement
            new_x = current_pos["x"] + dx
            new_y = current_pos["y"] + dy

            # Optimistic update - update local state immediately
            self._optimistic_move(new_x, new_y)

            # Send PlayerPosition message
            message = {
                "scopePath": ["Room", "Quinoa"],
                "type": "PlayerPosition",
                "position": {"x": new_x, "y": new_y},
            }

            # Send via asyncio thread-safe
            asyncio.run_coroutine_threadsafe(client.send(message), loop)
            return

        super().keyPressEvent(event)

    def _handle_interact(self, client, loop, player_slot):
        """Handle Space key interaction - harvest or plant"""
        slot_data = player_slot.get("data", {})
        garden_data = slot_data.get("garden", {})
        tile_objects = garden_data.get("tileObjects", {})
        inventory = slot_data.get("inventory", {})

        # Get player position and convert to tile ID
        position = player_slot.get("position")
        if not position:
            print("No position found in player_slot")
            return

        # Convert server coords to local, then to tile ID
        slot_index = self.game_state.get_user_slot_index()
        if slot_index is None:
            print("slot_index is None")
            return

        from utils.constants import SPAWN_POSITIONS
        if slot_index >= len(SPAWN_POSITIONS):
            print(f"slot_index {slot_index} out of range")
            return

        spawn_pos = SPAWN_POSITIONS[slot_index]
        local_spawn = {"x": 11, "y": 11}

        # Convert server position to local
        local_x = local_spawn["x"] + (position["x"] - spawn_pos["x"])
        local_y = local_spawn["y"] + (position["y"] - spawn_pos["y"])
        print(f"Position: server=({position['x']},{position['y']}) local=({local_x},{local_y})")

        # Convert local to tile ID (skip boardwalk)
        # Visual row 0 and 11 are boardwalk, visual col 0, 11, 22 are boardwalk
        # Tile row = visual_row - 1, tile col depends on which side of center
        if local_y < 1 or local_y > 10:
            print("Standing on boardwalk - can't interact")
            return

        if local_x < 1 or local_x > 21 or local_x == 11:
            print("Standing on boardwalk - can't interact")
            return

        # Calculate tile ID
        tile_row = local_y - 1  # 0-9 (10 rows of plantable tiles)
        if local_x < 11:
            tile_col = local_x - 1  # 0-9
        else:
            tile_col = local_x - 2  # 10-19

        tile_id = tile_row * 20 + tile_col

        # Check if tile has something
        tile_obj = tile_objects.get(str(tile_id))

        if tile_obj:
            obj_type = tile_obj.get("objectType")
            if obj_type == "plant":
                # Harvest the plant
                message = {
                    "scopePath": ["Room", "Quinoa"],
                    "type": "HarvestCrop",
                    "slot": tile_id,
                    "slotsIndex": 0,
                }
                print(f"Harvesting tile {tile_id}")
                self._optimistic_harvest(tile_id)
                asyncio.run_coroutine_threadsafe(client.send(message), loop)
            elif obj_type == "egg":
                # Hatch the egg
                message = {
                    "scopePath": ["Room", "Quinoa"],
                    "type": "HatchEgg",
                    "slot": tile_id,
                }
                print(f"Hatching egg on tile {tile_id}")
                self._optimistic_harvest(tile_id)
                asyncio.run_coroutine_threadsafe(client.send(message), loop)
            else:
                print(f"Unknown object type on tile: {obj_type}")
        else:
            # Empty tile - try to plant seed or egg
            selected_seed = self.inventory_panel.get_selected_seed()
            selected_egg = self.inventory_panel.get_selected_egg()

            if selected_seed:
                message = {
                    "scopePath": ["Room", "Quinoa"],
                    "type": "PlantSeed",
                    "slot": tile_id,
                    "species": selected_seed,
                }
                print(f"Planting {selected_seed} on tile {tile_id}")
                self._optimistic_plant(tile_id, selected_seed, is_egg=False)
                asyncio.run_coroutine_threadsafe(client.send(message), loop)
            elif selected_egg:
                message = {
                    "scopePath": ["Room", "Quinoa"],
                    "type": "PlantEgg",
                    "slot": tile_id,
                    "eggId": selected_egg,
                }
                print(f"Planting egg {selected_egg} on tile {tile_id}")
                self._optimistic_plant(tile_id, selected_egg, is_egg=True)
                asyncio.run_coroutine_threadsafe(client.send(message), loop)
            else:
                print("No seed or egg selected - click one in the Inventory tab first")
