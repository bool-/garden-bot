"""
Dashboard: KPI strip, exceptions that need attention, the garden map, the
active team and the brain's activity log.
"""

import collections
import time

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from .garden_canvas import GardenCanvas, Legend
from .model import (
    egg_groups,
    event_matches,
    food_for,
    format_event,
    has_camera,
    held_and_stamped,
    hunger_color,
    hunger_of,
    next_meal,
    pet_name,
    stamp_of,
)
from .theme import Carbon as C, body_font, duration, full_number, heading_font, label_font, mono_font, short_number, spaced
from .widgets import (
    CarbonTable,
    Cell,
    FlatButton,
    KpiTile,
    Sparkline,
    gap_grid,
    heading,
    make_label,
    rule,
    set_color,
    set_text,
)

SAMPLE_EVERY_S = 30
HISTORY = 720  # 6 hours of 30s samples
MAX_EVENTS = 60
ATTENTION_ORDER = {"error": 0, "warn": 1, "info": 2}


class CoinsTile(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("tile")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(C.S3, C.S3, C.S3, C.S3)
        lay.setSpacing(C.S1)
        lay.addWidget(make_label("Coins", label_font(), C.TEXT_SECONDARY))
        row = QHBoxLayout()
        row.setSpacing(C.S3)
        self.value = make_label("-", mono_font(28), C.MONEY)
        self.value.setFixedHeight(36)
        row.addWidget(self.value, 0, Qt.AlignmentFlag.AlignBottom)
        self.spark = Sparkline(C.MONEY)
        row.addWidget(self.spark, 1, Qt.AlignmentFlag.AlignBottom)
        lay.addLayout(row)
        lay.addStretch(1)


class AttentionRow(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("attn")
        self.setFixedHeight(41)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(C.S3, 0, C.S3, 1)
        lay.setSpacing(12)
        self.mark = QWidget()
        self.mark.setFixedWidth(3)
        self.mark.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        mark_box = QVBoxLayout()
        mark_box.setContentsMargins(0, 8, 0, 8)
        mark_box.addWidget(self.mark)
        lay.addLayout(mark_box)
        self.title = make_label("", heading_font())
        lay.addWidget(self.title)
        self.detail = make_label("", body_font(), C.TEXT_SECONDARY)
        lay.addWidget(self.detail, 1)
        self.when = make_label("", mono_font(14), C.TEXT_SECONDARY)
        lay.addWidget(self.when)
        self._kind = None

    def set(self, kind, title, detail, when):
        if kind != self._kind:
            self._kind = kind
            bg = {"warn": C.WARNING_ROW, "error": C.ERROR_ROW}.get(kind, C.LAYER_01)
            mark = {"warn": C.WARNING, "error": C.ERROR}.get(kind, C.INFO)
            self.setStyleSheet(f"QFrame#attn {{ background: {bg}; border: 0; border-bottom: 1px solid {C.BORDER_SUBTLE}; }}")
            self.mark.setStyleSheet(f"background: {mark};")
        set_text(self.title, title)
        set_text(self.detail, detail)
        set_text(self.when, when)


class DashboardPage(QWidget):
    def __init__(self, game_state, harvest_config=None):
        super().__init__()
        self.setObjectName("page")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.started = time.time()
        self.history = collections.deque(maxlen=HISTORY)
        self._last_sample = 0.0
        self.filter = "All"
        self._brain = None

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---------------------------------------------------------- main
        main = QWidget()
        mlay = QVBoxLayout(main)
        mlay.setContentsMargins(0, 0, 0, 0)
        mlay.setSpacing(0)

        self.coins = CoinsTile()
        self.k_session = KpiTile("This session")
        self.k_held = KpiTile("Held for stamp")
        self.k_eggs = KpiTile("Eggs growing")
        self.k_cmds = KpiTile("Commands")
        mlay.addWidget(gap_grid([self.coins, self.k_session, self.k_held, self.k_eggs, self.k_cmds], [7, 5, 5, 5, 5]))
        mlay.addWidget(rule())

        self.attn_box = QVBoxLayout()
        self.attn_box.setSpacing(0)
        self.attn_rows = []
        mlay.addLayout(self.attn_box)

        ghead = QWidget()
        ghead.setFixedHeight(48)
        gl = QHBoxLayout(ghead)
        gl.setContentsMargins(C.S3, 0, C.S3, 0)
        gl.setSpacing(C.S4)
        gl.addWidget(heading("Garden"))
        self.garden_sub = make_label("", body_font(), C.TEXT_SECONDARY)
        self.garden_sub.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        gl.addWidget(self.garden_sub, 1)
        self.legend = Legend(keys={"stamped", "held", "ripe", "growing", "egg", "food"})
        gl.addWidget(self.legend)
        mlay.addWidget(ghead)
        self.canvas = GardenCanvas(game_state, harvest_config, slot_index=None, max_cell=36)
        cwrap = QVBoxLayout()
        cwrap.setContentsMargins(C.S3, 0, C.S3, C.S3)
        cwrap.addWidget(self.canvas)
        mlay.addLayout(cwrap, 1)
        root.addWidget(main, 1)
        root.addWidget(rule(vertical=True))

        # ---------------------------------------------------------- aside
        aside = QWidget()
        aside.setFixedWidth(448)
        alay = QVBoxLayout(aside)
        alay.setContentsMargins(0, 0, 0, 0)
        alay.setSpacing(0)
        th = QWidget()
        th.setFixedHeight(48)
        tl = QHBoxLayout(th)
        tl.setContentsMargins(C.S3, 0, C.S3, 0)
        tl.addWidget(heading("Team"))
        tl.addStretch(1)
        alay.addWidget(th)
        self.team = CarbonTable([("Pet", "stretch", (16, 8)), ("Stamp", 100, (8, 8)),
                                  ("Hunger", 132, (8, 8)), (">Eats", 112, (8, 16))])
        alay.addWidget(self.team)
        alay.addSpacing(C.S3)

        ah = QWidget()
        ah.setFixedHeight(48)
        al = QHBoxLayout(ah)
        al.setContentsMargins(C.S3, 0, 0, 0)
        al.setSpacing(0)
        al.addWidget(heading("Activity"))
        al.addStretch(1)
        self.filter_buttons = {}
        for name in ("All", "Money", "Pets"):
            b = FlatButton(name, bg=C.LAYER_01, hover=C.LAYER_HOVER_01, fg=C.TEXT_SECONDARY,
                           sel_bg=C.LAYER_02, sel_fg=C.TEXT_PRIMARY, height=32)
            b.clicked.connect(lambda _=False, n=name: self.set_filter(n))
            self.filter_buttons[name] = b
            if name != "All":
                sep = QWidget()
                sep.setFixedSize(1, 32)
                sep.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
                sep.setStyleSheet(f"background: {C.BACKGROUND};")
                al.addWidget(sep)
            al.addWidget(b)
        self.filter_buttons["All"].set_selected(True)
        alay.addWidget(ah)
        self.activity = CarbonTable([("Time", 92, (16, 8)), ("Event", "stretch", (8, 8)), (">Value", 96, (8, 16))],
                                    header=False,
                                    rowbg="none", fit_height=False)
        alay.addWidget(self.activity, 1)
        root.addWidget(aside)

    # -------------------------------------------------------------- filter
    def set_filter(self, name: str):
        self.filter = name
        for n, b in self.filter_buttons.items():
            b.set_selected(n == name)
        self._render_activity(self._brain)

    # -------------------------------------------------------------- update
    def sample(self, snap):
        """Coins history for the sparkline (runs every tick, samples every 30s)."""
        now = time.time()
        if snap.coins is not None and (not self.history or now - self._last_sample >= SAMPLE_EVERY_S):
            self.history.append(float(snap.coins))
            self._last_sample = now

    def update_data(self, snap):
        self._brain = snap.brain
        self.sample(snap)
        client = snap.client

        # KPIs
        set_text(self.coins.value, short_number(snap.coins) if snap.coins is not None else "-")
        self.coins.spark.set_values(self.history)
        self.coins.spark.setToolTip(f"Coins, sampled every {SAMPLE_EVERY_S}s ({len(self.history)} samples)")
        earned = getattr(client, "session_coins_earned", 0) if client is not None else 0
        hours = (time.time() - self.started) / 3600
        rate = f"{short_number(earned / hours)} per hour" if hours >= 2 / 60 else "rate after 2 minutes"
        self.k_session.set(short_number(earned, signed=True), rate)
        held, held_gold, stamped, stamped_value, names = held_and_stamped(snap)
        self.k_held.set(full_number(held), f"{short_number(held_gold)} if all stamped Gold")
        groups = egg_groups(snap)
        eggs = sum(g["tiles"] for g in groups)
        ready = sum(g["ready"] for g in groups)
        if ready:
            sub = f"{ready} ready to hatch"
        elif groups and groups[0]["left"] is not None:
            sub = f"next hatch in {duration(groups[0]['left'])}"
        else:
            sub = "none on tiles"
        self.k_eggs.set(full_number(eggs), sub)
        ok = getattr(client, "command_ok", 0) if client is not None else 0
        rej = getattr(client, "command_rejected", 0) if client is not None else 0
        self.k_cmds.set(full_number(ok), f"{full_number(rej)} rejected", C.ERROR if rej else C.SUCCESS)

        self._render_attention(snap, stamped, stamped_value, names, rej)

        # Garden
        set_text(self.garden_sub, f"{snap.player_name}, slot {snap.slot_index}" if snap.ready else "")
        self.canvas.slot_index = snap.slot_index
        self.canvas.set_view(snap.now_ms, snap.hold_min, snap.food_crops)
        self.canvas.set_player_slot(snap.slot)
        self.legend.set_counts(self.canvas.counts)

        # Team
        rows = []
        for pet in snap.pets:
            hunger, cap, frac = hunger_of(pet)
            stamp, scolor = stamp_of(pet)
            food = food_for(snap, pet)
            rows.append([
                Cell(pet_name(pet)),
                Cell(stamp, scolor, mono=True, px=12),
                Cell(bar=(frac, hunger_color(frac, hunger), f"{frac * 100:.0f}%", 72)),
                Cell(spaced(food) if food else "-", C.TEXT_SECONDARY, right=True),
            ])
        self.team.set_rows(rows, empty="No pets on the team")
        self._render_activity(snap.brain)

    def _render_attention(self, snap, stamped, stamped_value, names, rejected):
        items = []
        client = snap.client
        if client is not None and not getattr(client, "is_connected", False):
            items.append(("error", "Disconnected", "Waiting for the game server; the bot reconnects on its own", ""))
        if snap.brain is None:
            items.append(("info", "Brain disabled", "Enable brain.enabled in bot_config.json to let the bot play", ""))
        elif snap.paused:
            items.append(("info", "Paused", "Space resumes. While paused, WASD or the arrows move you and E plants or harvests", ""))
        for pet in snap.pets:
            hunger, cap, frac = hunger_of(pet)
            if cap and frac < 0.2:
                detail, when = next_meal(snap, pet)
                if hunger <= 0:
                    items.append(("error", f"{pet_name(pet)} is starving", detail, when))
                else:
                    items.append(("warn", f"{pet_name(pet)} hunger {frac * 100:.0f}%", detail, when))
        if stamped:
            kinds = " and ".join(sorted(names)) or "Gold"
            items.append(("info", f"{stamped} crop{'s' if stamped != 1 else ''} stamped {kinds}",
                          f"Harvest and sell queued, about {short_number(stamped_value)}", "next"))
        if rejected:
            items.append(("warn", f"{full_number(rejected)} command{'s' if rejected != 1 else ''} rejected",
                          "The server refused some actions; see Activity for what and why", ""))
        if snap.brain is not None and snap.plan and snap.plan.get("granters_working") is False:
            items.append(("warn", "Granters not working",
                          "No fed Gold or Rainbow pet on the team, so valuable crops are harvested unstamped", ""))
        if snap.brain is not None and snap.ready and snap.cfg.get("journal") and not has_camera(snap):
            items.append(("info", "Journal paused", "No Camera on this account, and the Camera isn't sold in shops", ""))
        items.sort(key=lambda it: ATTENTION_ORDER[it[0]])
        while len(self.attn_rows) < len(items):
            row = AttentionRow()
            self.attn_rows.append(row)
            self.attn_box.addWidget(row)
        for i, row in enumerate(self.attn_rows):
            if i < len(items):
                row.set(*items[i])
                row.show()
            else:
                row.hide()

    def _render_activity(self, brain):
        if brain is None:
            self.activity.set_rows([], empty="Brain disabled")
            return
        events = sorted(list(getattr(brain, "events", []) or []), key=lambda e: e[0], reverse=True)
        rows = []
        for ts, text in events:
            disp, val, kind = format_event(text)
            if not event_matches(kind, self.filter):
                continue
            color = {"m": C.MONEY, "g": C.SUCCESS}.get(kind, C.TEXT_HELPER)
            rows.append([
                Cell(time.strftime("%H:%M:%S", time.localtime(ts)), C.TEXT_HELPER, mono=True, px=12),
                Cell(disp, tip=str(text)),
                Cell(val, color, mono=True, px=12, right=True),
            ])
            if len(rows) >= MAX_EVENTS:
                break
        self.activity.set_rows(rows, empty="Nothing yet")
