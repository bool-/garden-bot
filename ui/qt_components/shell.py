"""
UI Shell: 48px header (name, section tabs, Sell / Shop / Pause) and the
24px status bar.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel

from automation import economy as eco

from .theme import Carbon as C, body_font, clock, label_font
from .widgets import FlatButton, set_color, set_text

TABS = ["Dashboard", "Garden", "Pets", "Inventory", "Shop", "Journal", "Settings"]


class ShellHeader(QFrame):
    tab_selected = pyqtSignal(int)
    sell_clicked = pyqtSignal()
    shop_clicked = pyqtSignal()
    pause_clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setObjectName("header")
        self.setFixedHeight(48)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 1)
        lay.setSpacing(0)

        brand = QLabel('Garden&nbsp;<span style="font-weight:600;">Bot</span>')
        brand.setTextFormat(Qt.TextFormat.RichText)
        brand.setFont(body_font())
        brand.setContentsMargins(16, 0, 16, 0)
        lay.addWidget(brand)

        self.tabs = []
        for i, name in enumerate(TABS):
            b = FlatButton(name, str(i + 1), fg=C.TEXT_SECONDARY, hint_color=C.TEXT_PLACEHOLDER,
                           hover=C.LAYER_HOVER_01, sel_bg=C.LAYER_01, sel_fg=C.TEXT_PRIMARY, marker="bottom")
            b.clicked.connect(lambda _=False, idx=i: self.tab_selected.emit(idx))
            self.tabs.append(b)
            lay.addWidget(b)
        lay.addStretch(1)

        self.sell = FlatButton("Sell now", "S", hover=C.LAYER_HOVER_01, left_rule=True, gap=12)
        self.shop = FlatButton("Shop now", "B", hover=C.LAYER_HOVER_01, left_rule=True, gap=12)
        self.pause = FlatButton("Pause", "Space", bg=C.LAYER_02, hover=C.LAYER_HOVER_02, fg=C.TEXT_ON_COLOR,
                                hint_color="#B3FFFFFF", justify=True, gap=16)
        self.pause.set_min_width(160)
        self.sell.clicked.connect(self.sell_clicked)
        self.shop.clicked.connect(self.shop_clicked)
        self.pause.clicked.connect(self.pause_clicked)
        for b in (self.sell, self.shop, self.pause):
            lay.addWidget(b)
        self.select(0)

    def select(self, idx: int):
        for i, b in enumerate(self.tabs):
            b.set_selected(i == idx)

    def set_state(self, brain_present: bool, paused: bool):
        for b in (self.sell, self.shop, self.pause):
            b.setEnabled(brain_present)
        if not brain_present:
            self.pause.setText("Brain disabled")
            self.pause.set_colors(C.LAYER_02, C.LAYER_02)
        elif paused:
            self.pause.setText("Resume")
            self.pause.set_colors(C.INTERACTIVE, C.INTERACTIVE_HOVER, C.TEXT_ON_COLOR)
        else:
            self.pause.setText("Pause")
            self.pause.set_colors(C.LAYER_02, C.LAYER_HOVER_02, C.TEXT_ON_COLOR)


class StatusFooter(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("footer")
        self.setFixedHeight(24)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 1, 0, 0)
        lay.setSpacing(0)

        def part(sep=True):
            lab = QLabel("")
            lab.setFont(label_font())
            lab.setProperty("sep", "true" if sep else "false")
            lab.setFixedHeight(23)
            return lab

        self.conn = part(sep=False)
        self.room = part()
        self.build = part()
        self.ping = part()
        self.bag = part()
        self.restock = part()
        for w in (self.conn, self.room, self.build, self.ping, self.bag):
            lay.addWidget(w)
        lay.addStretch(1)
        lay.addWidget(self.restock)

    def update_data(self, snap):
        client = snap.client
        connected = bool(getattr(client, "is_connected", False)) if client is not None else False
        set_text(self.conn, "Connected" if connected else "Disconnected")
        set_color(self.conn, C.SUCCESS if connected else C.ERROR)
        set_text(self.room, f"Room {snap.room_id or '-'}")
        version = str(getattr(client, "version", "") or "") if client is not None else ""
        data_build = str(eco.GAME.get("build") or "")
        if version and data_build and version == data_build:
            build = f"Build {version}, game data current"
        elif version:
            build = f"Build {version}, game data from {data_build or 'unknown build'}"
        else:
            build = f"Game data build {data_build or '-'}"
        set_text(self.build, build)
        ping = getattr(client, "ping_ms", None) if client is not None else None
        self.ping.setVisible(isinstance(ping, (int, float)))
        if isinstance(ping, (int, float)):
            set_text(self.ping, f"Ping {int(ping)} ms")
        n, cap = snap.bag
        self.bag.setVisible(snap.ready)
        set_text(self.bag, f"Bag {n} of {cap}")
        seed = (snap.quinoa.get("shops") or {}).get("seed") or {}
        deadline = seed.get("deadlineMs")
        if deadline:
            left = (deadline - snap.now_ms) / 1000
            set_text(self.restock, f"Next restock in {clock(left)}" if left > 0 else "Seed stall restocked")
            self.restock.setVisible(True)
        else:
            self.restock.setVisible(False)
