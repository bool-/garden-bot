"""
Garden page: every player's garden in the room, one Carbon tab per player
(yours first), with a legend of live counts for the garden on screen.
"""

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from config import HarvestConfig
from game_state import GameState

from .garden_canvas import GardenCanvas, Legend
from .theme import Carbon as C
from .widgets import FlatButton, Page, make_label, label_font, rule, set_text


class GardenTabs(QWidget):
    """Tabs of player gardens (keeps one canvas per player id)."""

    def __init__(self, game_state: GameState, harvest_config: Optional[HarvestConfig] = None):
        super().__init__()
        self.game_state = game_state
        self.harvest_config = harvest_config
        self.client_holder = {}
        self.canvases = {}  # player id -> canvas
        self.buttons = {}  # player id -> tab button
        self.order = []  # player ids, yours first

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar = QWidget()
        bar.setFixedHeight(40)
        self.tab_row = QHBoxLayout(bar)
        self.tab_row.setContentsMargins(0, 0, 0, 0)
        self.tab_row.setSpacing(0)
        self.tab_row.addStretch(1)
        self.legend = Legend()
        self.tab_row.addWidget(self.legend)
        lay.addWidget(bar)
        lay.addWidget(rule())
        self.stack = QStackedWidget()
        lay.addSpacing(C.S3)
        lay.addWidget(self.stack, 1)
        self.empty = make_label("Waiting for game state", label_font(), C.TEXT_HELPER)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stack.addWidget(self.empty)

    def set_client_holder(self, client_holder):
        self.client_holder = client_holder if client_holder is not None else {}
        for canvas in self.canvases.values():
            canvas.set_client_holder(self.client_holder)

    def _select(self, pid):
        canvas = self.canvases.get(pid)
        if canvas is None:
            return
        self.stack.setCurrentWidget(canvas)
        for other, b in self.buttons.items():
            b.set_selected(other == pid)
        self.legend.set_counts(canvas.counts)

    def current_canvas(self) -> Optional[GardenCanvas]:
        w = self.stack.currentWidget()
        return w if isinstance(w, GardenCanvas) else None

    def update_gardens(self, snap=None):
        """Sync tabs with the room's user slots (snap: model.Snapshot)."""
        slots = snap.user_slots if snap is not None else []
        me = snap.player_id if snap is not None else self.game_state.get_player_id()
        seen = []
        for idx, slot in enumerate(slots):
            if not slot:
                continue
            pid = slot.get("userId") or slot.get("playerId")
            if not pid:
                continue
            seen.append(pid)
            name = self.game_state.get_player_name_by_id(pid) or str(pid)
            label = f"{name} (you)" if pid == me else name
            canvas = self.canvases.get(pid)
            if canvas is None:
                canvas = GardenCanvas(self.game_state, self.harvest_config, slot_index=idx, max_cell=48)
                canvas.set_client_holder(self.client_holder)
                self.canvases[pid] = canvas
                self.stack.addWidget(canvas)
                btn = FlatButton(label, hover=C.LAYER_HOVER_01, fg=C.TEXT_SECONDARY, sel_bg=C.LAYER_01,
                                 sel_fg=C.TEXT_PRIMARY, marker="bottom")
                btn.clicked.connect(lambda _=False, p=pid: self._select(p))
                self.buttons[pid] = btn
            else:
                canvas.slot_index = idx
                self.buttons[pid].setText(label)
            canvas.set_view(snap.now_ms, snap.hold_min, snap.food_crops if pid == me else set())
            canvas.set_player_slot(slot)

        # yours first, then by slot order
        order = sorted(seen, key=lambda p: (p != me, seen.index(p)))
        if order != self.order:
            for pid in self.order:
                if pid in self.buttons:
                    self.tab_row.removeWidget(self.buttons[pid])
            for i, pid in enumerate(order):
                self.tab_row.insertWidget(i, self.buttons[pid])
            self.order = order
        for pid in [p for p in self.canvases if p not in seen]:
            canvas = self.canvases.pop(pid)
            self.stack.removeWidget(canvas)
            canvas.deleteLater()
            self.buttons.pop(pid).deleteLater()

        current = self.current_canvas()
        if current is None and order:
            self._select(order[0])
        elif current is not None:
            self.legend.set_counts(current.counts)
        elif not order:
            self.stack.setCurrentWidget(self.empty)


class GardenPage(Page):
    def __init__(self, game_state: GameState, harvest_config=None):
        super().__init__("Garden", "Your garden and every other garden in the room. Hover a tile for its crop, "
                                   "mutations, value and what the bot will do with it.")
        self.tabs = GardenTabs(game_state, harvest_config)
        self.outer.addWidget(self.tabs, 1)

    def update_data(self, snap):
        self.tabs.update_gardens(snap)
        if snap.ready:
            n = sum(1 for s in snap.user_slots if s)
            set_text(self.helper_label, f"Room {snap.room_id or '-'}: {n} garden{'s' if n != 1 else ''}. "
                     "Hover a tile for its crop, mutations, value and what the bot will do with it.")
