"""
PyQt6 GUI for Garden Bot, IBM Carbon (Gray 100) design.

UI Shell header with section tabs and Sell / Shop / Pause, a stacked page
area, and a 24px status bar. Keyboard: 1-7 switch tabs, Space pauses or
resumes the brain, S sells now, B shops now. While the brain is paused (or
disabled) W/A/S/D and the arrows move you and E plants or harvests the tile
you stand on.
"""

import asyncio
import os
import time
import uuid
from typing import Any, Dict, Optional

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtGui import QIcon, QKeyEvent
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import HarvestConfig
from game_state import GameState
from .qt_components import (
    TABS,
    DashboardPage,
    GardenPage,
    InventoryPage,
    JournalPage,
    PetsPage,
    ServerClock,
    SettingsPage,
    ShellHeader,
    ShopPage,
    Snapshot,
    StatusFooter,
    font,
    stylesheet,
)

TEXT_INPUTS = (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)
MOVE_KEYS = {
    Qt.Key.Key_W: (0, -1), Qt.Key.Key_Up: (0, -1),
    Qt.Key.Key_S: (0, 1), Qt.Key.Key_Down: (0, 1),
    Qt.Key.Key_A: (-1, 0), Qt.Key.Key_Left: (-1, 0),
    Qt.Key.Key_D: (1, 0), Qt.Key.Key_Right: (1, 0),
}
TAB_KEYS = {getattr(Qt.Key, f"Key_{i + 1}"): i for i in range(len(TABS))}


class MagicGardenGUI(QMainWindow):
    """Main window"""

    def __init__(
        self,
        game_state: GameState,
        harvest_config: Optional[HarvestConfig] = None,
        client_holder: Optional[Dict[str, Any]] = None,
    ):
        super().__init__()
        self.game_state = game_state
        self.harvest_config = harvest_config
        self.client_holder = client_holder if client_holder is not None else {}
        self.clock = ServerClock()
        self.snap: Optional[Snapshot] = None
        self._flash = {}  # button -> time a "Queued" hint expires

        app = QApplication.instance()
        if app is not None:
            app.setStyle("Fusion")
            app.setFont(font(14))
        self.setWindowTitle("Garden Bot")
        self.setWindowIcon(QIcon(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                              "magic_garden_bot.ico")))
        self._fit_to_screen()
        self.setStyleSheet(stylesheet())

        self.setup_ui()
        if app is not None:
            app.installEventFilter(self)

        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_ui)
        self.update_timer.start(250)  # cheap: full redraws only when something changed
        self._last_key = None
        self._last_full = 0.0

    def _fit_to_screen(self):
        """Open at the designed 1440x900 when it fits, otherwise as large as
        the screen's free area allows (laptops), centred with the title bar
        on screen so the window can always be dragged."""
        screen = QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else None
        width, height = 1440, 900
        if avail is not None:
            frame = 40  # room for the native title bar and borders
            width = min(width, avail.width() - 16)
            height = min(height, avail.height() - frame)
        self.setMinimumSize(min(1200, width), min(760, height))
        self.resize(width, height)
        if avail is not None:
            self.move(avail.x() + (avail.width() - width) // 2,
                      avail.y() + max(0, (avail.height() - height - 32) // 2))

    # ------------------------------------------------------------------ layout
    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.header = ShellHeader()
        self.header.tab_selected.connect(self.select_tab)
        self.header.sell_clicked.connect(lambda: self.request("sell"))
        self.header.shop_clicked.connect(lambda: self.request("shop"))
        self.header.pause_clicked.connect(self.toggle_pause)
        lay.addWidget(self.header)

        self.pages = QStackedWidget()
        self.dashboard = DashboardPage(self.game_state, self.harvest_config)
        self.garden_page = GardenPage(self.game_state, self.harvest_config)
        self.garden_page.tabs.set_client_holder(self.client_holder)
        self.garden_tabs = self.garden_page.tabs
        self.pets_page = PetsPage()
        self.inventory_panel = InventoryPage()
        self.inventory_panel.selection_made.connect(self._on_inventory_selection)
        self.shop_panel = ShopPage()
        self.shop_panel.set_client_holder(self.client_holder)
        self.journal_panel = JournalPage()
        self.settings_page = SettingsPage()
        for page in (self.dashboard, self.garden_page, self.pets_page, self.inventory_panel,
                     self.shop_panel, self.journal_panel, self.settings_page):
            self.pages.addWidget(page)
        lay.addWidget(self.pages, 1)

        self.footer = StatusFooter()
        lay.addWidget(self.footer)

    def select_tab(self, idx: int):
        if 0 <= idx < self.pages.count():
            self.pages.setCurrentIndex(idx)
            self.header.select(idx)
            self.update_ui()

    # ------------------------------------------------------------------ brain
    def _brain(self):
        return self.client_holder.get("brain")

    def toggle_pause(self):
        brain = self._brain()
        if brain is None:
            return
        brain.paused = not bool(getattr(brain, "paused", False))
        self.update_ui()

    def request(self, action: str):
        brain = self._brain()
        if brain is None:
            return
        brain.request(action)
        btn = self.header.sell if action == "sell" else self.header.shop
        btn.set_hint("Queued")
        self._flash[btn] = time.time() + 2.0

    # ------------------------------------------------------------------ update
    def _change_key(self):
        """Fingerprint of what the pages show; unchanged -> skip the rebuild."""
        brain = self.client_holder.get("brain")
        client = self.client_holder.get("client")
        rev = self.game_state.get_revision() if hasattr(self.game_state, "get_revision") else time.time()
        if brain is not None:
            events = getattr(brain, "events", ()) or ()
            settings = getattr(brain, "settings", None)
            b = (getattr(brain, "paused", None), getattr(brain, "action", None), len(events),
                 events[-1][0] if events else 0,
                 tuple(sorted((settings() if callable(settings) else {}).items(), key=lambda kv: kv[0]))
                 if hasattr(brain, "src") else None)
        else:
            b = None
        c = (getattr(client, "is_connected", None), getattr(client, "command_ok", None)) if client else None
        return (rev, b, c, self.pages.currentIndex())

    def update_ui(self):
        remote = self.client_holder.get("remote")
        if remote is not None:
            remote.fast = self.isActiveWindow() and not self.isMinimized()
        if self.isMinimized():
            return  # nothing to draw
        key = self._change_key()
        now = time.time()
        if key == self._last_key and now - self._last_full < 5.0:
            return  # nothing changed; clocks catch up on the 5s refresh
        self._last_key, self._last_full = key, now
        try:
            snap = Snapshot(self.game_state, self.client_holder, self.clock)
        except Exception as e:  # a half-applied patch should never kill the UI
            print(f"UI snapshot failed: {e!r}")
            return
        self.snap = snap
        self.header.set_state(snap.brain is not None, snap.paused)
        now = time.time()
        for btn, until in list(self._flash.items()):
            if now >= until:
                btn.set_hint("S" if btn is self.header.sell else "B")
                del self._flash[btn]
        self.footer.update_data(snap)
        self.dashboard.sample(snap)
        self.pages.currentWidget().update_data(snap)

    def _on_inventory_selection(self):
        self.setFocus()
        self.activateWindow()

    # ------------------------------------------------------------------ keys
    def eventFilter(self, obj: QObject, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.KeyPress and isinstance(obj, QWidget) and obj.window() is self:
            if self.handle_key(event):
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent):  # noqa: N802
        if not self.handle_key(event):
            super().keyPressEvent(event)

    def handle_key(self, event: QKeyEvent) -> bool:
        """Shortcuts; returns True when the key was used."""
        focus = QApplication.focusWidget()
        if isinstance(focus, TEXT_INPUTS) or (isinstance(focus, QComboBox) and focus.isEditable()):
            return False
        mods = event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier
        if mods not in (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ShiftModifier):
            return False
        key = event.key()
        brain = self._brain()
        manual = brain is None or bool(getattr(brain, "paused", False))
        if not event.isAutoRepeat():
            if key in TAB_KEYS:
                self.select_tab(TAB_KEYS[key])
                return True
            if key == Qt.Key.Key_Space:
                self.toggle_pause()
                return True
            if key == Qt.Key.Key_B and brain is not None:
                self.request("shop")
                return True
            if key == Qt.Key.Key_S and brain is not None and not manual:
                self.request("sell")
                return True
        if manual and (key in MOVE_KEYS or key in (Qt.Key.Key_E, Qt.Key.Key_Return, Qt.Key.Key_Enter)):
            self._manual_key(key)
            return True
        return False

    # ------------------------------------------------------------------ manual play
    def _manual_key(self, key):
        client = self.client_holder.get("client")
        loop = self.client_holder.get("loop")
        if not client or not loop or not getattr(client, "is_connected", False):
            return
        player_slot = self.game_state.get_player_slot()
        pos = self.game_state.get_player_position()
        if not player_slot or not pos or pos.get("x") is None or pos.get("y") is None:
            print("Manual control: player position is unknown")
            return
        if key in (Qt.Key.Key_E, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._handle_interact(client, loop, player_slot)
            return
        dx, dy = MOVE_KEYS[key]
        new_x, new_y = pos["x"] + dx, pos["y"] + dy
        self._optimistic_move(new_x, new_y)
        message = {
            "scopePath": ["Room", "Quinoa"],
            "type": "PlayerPosition",
            "position": {"x": new_x, "y": new_y},
        }
        asyncio.run_coroutine_threadsafe(client.send(message), loop)

    def _refresh_gardens(self):
        self.update_ui()

    def _optimistic_move(self, new_x: int, new_y: int):
        self.game_state.set_player_position(new_x, new_y)
        self._refresh_gardens()

    def _optimistic_harvest(self, tile_id: int):
        def update(full_state):
            player_id = self.game_state.get_player_id()
            child = full_state.get("child", {})
            if not player_id or child.get("scope") != "Quinoa":
                return
            for slot in child.get("data", {}).get("userSlots", []):
                if slot and (slot.get("userId") or slot.get("playerId")) == player_id:
                    slot.get("data", {}).get("garden", {}).get("tileObjects", {}).pop(str(tile_id), None)
                    break
        self.game_state.update_full_state_locked(update)
        self._refresh_gardens()

    def _optimistic_plant(self, tile_id: int, species: str, is_egg: bool = False):
        def update(full_state):
            player_id = self.game_state.get_player_id()
            child = full_state.get("child", {})
            if not player_id or child.get("scope") != "Quinoa":
                return
            for slot in child.get("data", {}).get("userSlots", []):
                if slot and (slot.get("userId") or slot.get("playerId")) == player_id:
                    tiles = slot.get("data", {}).get("garden", {}).get("tileObjects", {})
                    now = int(time.time() * 1000)
                    if is_egg:
                        tiles[str(tile_id)] = {"objectType": "egg", "eggId": species, "maturedAt": now + 60000}
                    else:
                        tiles[str(tile_id)] = {"objectType": "plant", "species": species, "slots": [
                            {"species": species, "mutations": [], "endTime": now + 60000}]}
                    break
        self.game_state.update_full_state_locked(update)
        self._refresh_gardens()

    def _handle_interact(self, client, loop, player_slot):
        """E / Enter: harvest or hatch the tile you stand on, or plant the
        seed or egg selected on the Inventory page."""
        tile_objects = player_slot.get("data", {}).get("garden", {}).get("tileObjects", {})
        position = self.game_state.get_player_position()
        slot_index = self.game_state.get_user_slot_index()
        if slot_index is None:
            print("Manual control: garden slot unknown")
            return
        from utils.constants import SPAWN_POSITIONS
        if slot_index >= len(SPAWN_POSITIONS):
            print(f"Manual control: slot {slot_index} out of range")
            return
        spawn = SPAWN_POSITIONS[slot_index]
        local_x = 11 + (position["x"] - spawn["x"])
        local_y = 11 + (position["y"] - spawn["y"])
        if local_y < 1 or local_y > 10 or local_x < 1 or local_x > 21 or local_x == 11:
            print("Standing on the boardwalk: nothing to plant or harvest")
            return
        tile_col = local_x - 1 if local_x < 11 else local_x - 2
        tile_id = (local_y - 1) * 20 + tile_col
        tile_obj = tile_objects.get(str(tile_id))

        if tile_obj:
            obj_type = tile_obj.get("objectType")
            if obj_type == "plant":
                # QuinoaCommand envelope; cropItemId is a client-generated UUID (v2036).
                command = {"type": "HarvestCrop", "slot": tile_id, "slotsIndex": 0, "cropItemId": str(uuid.uuid4())}
                print(f"Harvesting tile {tile_id}")
            elif obj_type == "egg":
                command = {"type": "HatchEgg", "slot": tile_id}
                print(f"Hatching egg on tile {tile_id}")
            else:
                print(f"Unknown object on tile {tile_id}: {obj_type}")
                return
            self._optimistic_harvest(tile_id)
            asyncio.run_coroutine_threadsafe(client.send_command(command), loop)
            return

        seed = self.inventory_panel.get_selected_seed()
        egg = self.inventory_panel.get_selected_egg()
        if seed:
            command = {"type": "PlantSeed", "slot": tile_id, "species": seed}
            print(f"Planting {seed} on tile {tile_id}")
            self._optimistic_plant(tile_id, seed, is_egg=False)
        elif egg:
            # The old "PlantEgg" is "GrowEgg" now (slot + eggId), in a QuinoaCommand (v2036).
            command = {"type": "GrowEgg", "slot": tile_id, "eggId": egg}
            print(f"Planting egg {egg} on tile {tile_id}")
            self._optimistic_plant(tile_id, egg, is_egg=True)
        else:
            print("No seed or egg selected: pick one on the Inventory page first")
            return
        asyncio.run_coroutine_threadsafe(client.send_command(command), loop)
