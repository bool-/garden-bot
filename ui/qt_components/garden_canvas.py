"""
Garden map: 23x12 square cells with 2px gaps, colored by what the brain will
do with each tile. The player's tile gets a 2px white outline.
"""

from typing import Optional

from PyQt6.QtCore import QEvent, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QHBoxLayout, QSizePolicy, QToolTip, QWidget

from game_state import GameState
from utils.constants import SPAWN_POSITIONS

from .model import classify_tile, garden_counts, tile_tooltip, DEFAULT_HOLD_MIN_BASE
from .tile_art import describe, paint_tile
from .theme import Carbon as C, label_font, mono_font
from .widgets import make_label, set_text

COLS, ROWS, GAP = 23, 12, 2

# Legend swatches (the map itself is drawn by tile_art.paint_tile).
CELL_COLORS = {
    "stamped": "#F1C21B",
    "held": "#FF832B",
    "ripe": "#6FDC8C",
    "growing": "#3E5A3A",
    "egg": "#A56EFF",
    "food": "#42BE65",
    "empty": "#2E241C",
}

LEGEND = [
    ("stamped", "Stamped"),
    ("held", "Held"),
    ("ripe", "Ripe"),
    ("growing", "Growing"),
    ("egg", "Eggs"),
    ("food", "Food"),
    ("empty", "Empty"),
]


def visual_to_tile_id(vrow: int, vcol: int) -> Optional[int]:
    if vrow < 1 or vrow > 10 or vcol < 1 or vcol > 21 or vcol == 11:
        return None
    col = vcol - 1 if vcol < 11 else vcol - 2
    return (vrow - 1) * 20 + col


class GardenCanvas(QWidget):
    """One player's garden. Data comes in through set_player_slot(); the
    brain's view (hold threshold, food crops, server time) through set_view()."""

    def __init__(self, game_state: GameState, harvest_config=None, slot_index: Optional[int] = None,
                 max_cell: int = 36):
        super().__init__()
        self.game_state = game_state
        self.harvest_config = harvest_config
        self.slot_index = slot_index
        self.player_slot = None
        self.client_holder = {}
        self.max_cell = max_cell
        self.now_ms = 0
        self.hold_min = DEFAULT_HOLD_MIN_BASE
        self.food = set()
        self.counts = {}
        self._geom = None  # (cell, ox, oy)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    # -------------------------------------------------------------- data
    def set_client_holder(self, client_holder):
        self.client_holder = client_holder if client_holder is not None else {}

    def set_view(self, now_ms: int, hold_min: int, food: set):
        self.now_ms, self.hold_min, self.food = now_ms, hold_min, set(food or ())

    def set_player_slot(self, player_slot):
        self.player_slot = player_slot
        self.counts = garden_counts(self._tiles(), self.now_ms, self.hold_min, self.food) if player_slot else {}
        self.update()

    def _tiles(self) -> dict:
        return (((self.player_slot or {}).get("data") or {}).get("garden") or {}).get("tileObjects") or {}

    def sizeHint(self):  # noqa: N802
        return QSize(COLS * self.max_cell + GAP * (COLS - 1), ROWS * self.max_cell + GAP * (ROWS - 1))

    def minimumSizeHint(self):  # noqa: N802
        return QSize(COLS * 12 + GAP * (COLS - 1), ROWS * 12 + GAP * (ROWS - 1))

    # -------------------------------------------------------------- geometry
    def _layout(self):
        cell = int(min((self.width() - GAP * (COLS - 1)) / COLS, (self.height() - GAP * (ROWS - 1)) / ROWS))
        cell = max(6, min(self.max_cell, cell))
        w = COLS * cell + GAP * (COLS - 1)
        h = ROWS * cell + GAP * (ROWS - 1)
        return cell, (self.width() - w) // 2, (self.height() - h) // 2

    def _cell_at(self, px, py):
        cell, ox, oy = self._geom or self._layout()
        step = cell + GAP
        vcol, vrow = (px - ox) // step, (py - oy) // step
        if not (0 <= vcol < COLS and 0 <= vrow < ROWS):
            return None
        if (px - ox) % step >= cell or (py - oy) % step >= cell:
            return None
        return int(vrow), int(vcol)

    def _is_own_garden(self) -> bool:
        if self.slot_index is None:
            return True
        own = self.game_state.get_user_slot_index()
        if own is not None:
            return own == self.slot_index
        slot = self.player_slot or {}
        pid = self.game_state.get_player_id()
        return bool(pid) and (slot.get("userId") or slot.get("playerId")) == pid

    def _player_cell(self):
        if not self._is_own_garden():
            return None
        pos = self.game_state.get_player_position() or {}
        slot_idx = self.slot_index if self.slot_index is not None else self.game_state.get_user_slot_index()
        if pos.get("x") is None or pos.get("y") is None or slot_idx is None or slot_idx >= len(SPAWN_POSITIONS):
            return None
        spawn = SPAWN_POSITIONS[slot_idx]
        lx = 11 + (pos["x"] - spawn["x"])
        ly = 11 + (pos["y"] - spawn["y"])
        if 0 <= lx < COLS and 0 <= ly < ROWS:
            return int(ly), int(lx)
        return None

    # -------------------------------------------------------------- tooltip
    def event(self, ev):
        if ev.type() == QEvent.Type.ToolTip:
            text = self.tooltip_at(ev.pos().x(), ev.pos().y())
            if text:
                QToolTip.showText(ev.globalPos(), text, self)
            else:
                QToolTip.hideText()
                ev.ignore()
            return True
        return super().event(ev)

    def tooltip_at(self, px: int, py: int) -> Optional[str]:
        if not self.player_slot:
            return None
        rc = self._cell_at(px, py)
        if rc is None:
            return None
        tile_id = visual_to_tile_id(*rc)
        if tile_id is None:
            return "Boardwalk"
        return tile_tooltip(tile_id, self._tiles().get(str(tile_id)), self.now_ms, self.hold_min, self.food)

    # -------------------------------------------------------------- paint
    def paintEvent(self, _ev):  # noqa: N802
        p = QPainter(self)
        cell, ox, oy = self._geom = self._layout()
        if not self.player_slot:
            p.setPen(QColor(C.TEXT_HELPER))
            p.setFont(label_font())
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Waiting for game state")
            p.end()
            return
        tiles = self._tiles()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(QRect(ox - GAP, oy - GAP, COLS * (cell + GAP) + GAP, ROWS * (cell + GAP) + GAP),
                   QColor("#1B1612"))
        for vrow in range(ROWS):
            for vcol in range(COLS):
                x = ox + vcol * (cell + GAP)
                y = oy + vrow * (cell + GAP)
                tid = visual_to_tile_id(vrow, vcol)
                rect = QRectF(x, y, cell, cell)
                if tid is None:
                    paint_tile(p, rect, {}, walk=True)
                else:
                    paint_tile(p, rect, describe(tiles.get(str(tid)), self.now_ms, self.hold_min, self.food))
        you = self._player_cell()
        if you:
            vrow, vcol = you
            x = ox + vcol * (cell + GAP)
            y = oy + vrow * (cell + GAP)
            pen = QPen(QColor(C.CELL_PLAYER), 2)
            pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRect(x + 1, y + 1, cell - 2, cell - 2))
        p.end()


class Legend(QWidget):
    """Swatch + label + live mono count per cell state."""

    def __init__(self, keys=None):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(C.S4)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        self.counts = {}
        for key, label in LEGEND:
            if keys and key not in keys:
                continue
            item = QHBoxLayout()
            item.setSpacing(C.S2)
            sw = QWidget()
            sw.setFixedSize(12, 12)
            sw.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            sw.setStyleSheet(f"background: {CELL_COLORS[key]};" + (
                f" border: 1px solid {C.LAYER_02};" if key == "empty" else ""))
            item.addWidget(sw)
            item.addWidget(make_label(label, label_font(), C.TEXT_SECONDARY))
            count = make_label("0", mono_font(12))
            item.addWidget(count)
            self.counts[key] = count
            lay.addLayout(item)

    def set_counts(self, counts):
        for key, lab in self.counts.items():
            set_text(lab, str((counts or {}).get(key, 0)))
