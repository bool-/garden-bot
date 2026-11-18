"""
Brain Panel Component

Live view of the autonomous brain (automation/brain.py): pause/resume,
current action, session earnings, the brain's last plan, settings and a
rolling event log. All data is read from plain attributes of objects that
live on the bot thread.
"""

import time
from html import escape

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QPlainTextEdit,
    QGroupBox,
    QSizePolicy,
)

from .theme import VSCodeTheme

MAX_EVENTS = 50
DISABLED_TEXT = "Brain disabled (enable it in bot_config.json → brain.enabled)"

# Brain settings worth showing, in order: (cfg key, label, default)
SETTINGS = [
    ("hold_for_gold_min_base_price", "Hold if base price >=", 100_000),
    ("sell_when_produce_count", "Sell at crop count", 20),
    ("sell_when_value_over", "Sell if value over", 5_000_000),
    ("food_tiles_per_pet", "Food tiles per pet", 2),
    ("harvest_batch", "Harvest batch", 12),
    ("min_coins_to_keep", "Min coins to keep", 0),
    ("buy_shops", "Buy shops", ["seed", "egg", "tool"]),
    ("never_plant", "Never plant", []),
    ("never_harvest", "Never harvest", []),
    ("tools_to_buy", "Tools to buy", []),
]


def short_number(value) -> str:
    """8075942165 -> '8.08B'"""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "-"
    sign = "-" if n < 0 else ""
    n = abs(n)
    for limit, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= limit:
            return f"{sign}{n / limit:.2f}{suffix}"
    return f"{sign}{n:,.0f}"


def full_number(value) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "-"


class BrainPanel(QWidget):
    """Panel for controlling/inspecting the autonomous brain"""

    def __init__(self):
        super().__init__()
        self.theme = VSCodeTheme
        self.client_holder = {}
        self._last = {}  # section name -> last rendered content

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Disabled notice (shown instead of everything else)
        self.disabled_label = QLabel(DISABLED_TEXT)
        self.disabled_label.setWordWrap(True)
        self.disabled_label.setStyleSheet(f"color: {self.theme.WARNING};")
        layout.addWidget(self.disabled_label)

        # Controls row
        controls = QHBoxLayout()
        self.pause_button = QPushButton("Pause")
        self.pause_button.setFixedWidth(90)
        self.pause_button.clicked.connect(self._toggle_pause)
        controls.addWidget(self.pause_button)
        self.action_label = QLabel("")
        self.action_label.setTextFormat(Qt.TextFormat.RichText)
        controls.addWidget(self.action_label, stretch=1)
        layout.addLayout(controls)

        # Sections (rich-text labels)
        self._section_boxes = []
        self.session_label = self._make_section(layout, "Session")
        self.plan_label = self._make_section(layout, "Plan")
        self.food_label = self._make_section(layout, "Food plan")
        self.counters_label = self._make_section(layout, "Actions done")
        self.settings_label = self._make_section(layout, "Settings (read only)")

        # Events
        events_box = QGroupBox("Events (newest first)")
        events_layout = QVBoxLayout(events_box)
        events_layout.setContentsMargins(6, 14, 6, 6)
        self.events_view = QPlainTextEdit()
        self.events_view.setReadOnly(True)
        self.events_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.events_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        events_layout.addWidget(self.events_view)
        layout.addWidget(events_box, stretch=1)
        self._section_boxes.append(events_box)

        self._set_enabled_view(False)

    def _make_section(self, layout, title: str) -> QLabel:
        box = QGroupBox(title)
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(8, 12, 8, 4)
        box_layout.setSpacing(0)
        label = QLabel("")
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        box_layout.addWidget(label)
        layout.addWidget(box)
        self._section_boxes.append(box)
        return label

    def set_client_holder(self, client_holder: dict):
        self.client_holder = client_holder

    # ------------------------------------------------------------------ helpers
    def _brain(self):
        return self.client_holder.get("brain") if self.client_holder else None

    def _toggle_pause(self):
        brain = self._brain()
        if brain is None:
            return
        brain.paused = not bool(brain.paused)
        self.update_data()

    def _set_enabled_view(self, enabled: bool):
        self.disabled_label.setVisible(not enabled)
        self.pause_button.setVisible(enabled)
        self.action_label.setVisible(enabled)
        for w in self._section_boxes:
            w.setVisible(enabled)

    def _set_label(self, key: str, label: QLabel, html: str):
        if self._last.get(key) != html:
            self._last[key] = html
            label.setText(html)

    def _row(self, name: str, value: str, color: str = None) -> str:
        t = self.theme
        val_style = f' style="color:{color};"' if color else ""
        return (
            f'<tr><td style="color:{t.TEXT_SECONDARY}; padding-right:14px;">{escape(name)}</td>'
            f'<td{val_style}><b>{value}</b></td></tr>'
        )

    def _table(self, rows) -> str:
        return f'<table cellspacing="0" cellpadding="1">{"".join(rows)}</table>'

    def _cells(self, name: str, value: str, color: str = None) -> str:
        t = self.theme
        val_style = f' style="color:{color};"' if color else ""
        return (
            f'<td style="color:{t.TEXT_SECONDARY};">{escape(name)}&nbsp;&nbsp;</td>'
            f'<td{val_style}><b>{value}</b>&nbsp;&nbsp;&nbsp;&nbsp;</td>'
        )

    def _table2(self, items) -> str:
        """items: list of (name, value, color|None); laid out two pairs per row."""
        rows = []
        for i in range(0, len(items), 2):
            pair = items[i:i + 2]
            rows.append("<tr>" + "".join(self._cells(*it) for it in pair) + "</tr>")
        return self._table(rows)

    # ------------------------------------------------------------------ update
    def update_data(self, client_holder: dict = None):
        if client_holder is not None:
            self.client_holder = client_holder
        brain = self._brain()
        if brain is None:
            self._set_enabled_view(False)
            return
        self._set_enabled_view(True)
        t = self.theme
        muted = t.TEXT_SECONDARY
        client = self.client_holder.get("client")

        # Pause button + action
        paused = bool(getattr(brain, "paused", False))
        self.pause_button.setText("Resume" if paused else "Pause")
        action = str(getattr(brain, "action", "") or "")
        color = t.WARNING if paused else (muted if action == "idle" else t.SUCCESS)
        self._set_label(
            "action", self.action_label,
            f'<span style="color:{muted};">Action:</span> '
            f'<b style="color:{color};">{escape(action or "-")}</b>',
        )

        # Session
        coins = getattr(client, "session_coins_earned", 0) if client else 0
        ok = getattr(client, "command_ok", 0) if client else 0
        rej = getattr(client, "command_rejected", 0) if client else 0
        items = [
            ("Coins earned", f'{short_number(coins)} <span style="color:{muted};">({full_number(coins)})</span>', "#ffd700"),
            ("Game build", escape(str(getattr(client, "version", "-"))) if client is not None else "-", None),
        ]
        cmds = (f'<span style="color:{t.SUCCESS};">{full_number(ok)} accepted</span> / '
                f'<span style="color:{t.ERROR if rej else muted};">{full_number(rej)} rejected</span>')
        rows = [self._table2(items), self._table([self._row("Commands", cmds)])]
        self._set_label("session", self.session_label, "".join(rows))

        # Plan
        plan = getattr(brain, "last_plan", None) or {}
        if plan:
            granters = plan.get("granters_working")
            items = [
                ("Coins", short_number(plan.get("coins")), None),
                ("Inventory", escape(str(plan.get("inventory", "-"))), None),
                ("Granters working", "yes" if granters else "NO", t.SUCCESS if granters else t.ERROR),
                ("Held for Gold/Rainbow", full_number(plan.get("held_for_stamp", 0)), "#ffd700"),
                ("Ready to harvest", full_number(plan.get("ready_to_harvest", 0)), None),
                ("Empty tiles", full_number(plan.get("empty_tiles", 0)), None),
                ("Eggs growing", full_number(plan.get("egg_tiles", 0)), None),
                ("Journal", escape(
                    f"{plan.get('journal_crops', '-')}/{plan.get('journal_total_crops', '-')} crops, "
                    f"{plan.get('journal_pets', '-')}/{plan.get('journal_total_pets', '-')} pets"), None),
            ]
            rows = [self._table2(items)]
            self._set_label("plan", self.plan_label, "".join(rows))
            food = plan.get("food_plan") or {}
            if food:
                self._set_label("food", self.food_label, self._table2(
                    [(str(pet), escape(str(crop)) if crop else "-", None) for pet, crop in food.items()]))
            else:
                self._set_label("food", self.food_label, f'<span style="color:{muted};">No food plan yet</span>')
        else:
            waiting = f'<span style="color:{muted};">Waiting for the first tick...</span>'
            self._set_label("plan", self.plan_label, waiting)
            self._set_label("food", self.food_label, waiting)

        # Counters
        counters = dict(getattr(brain, "counters", {}) or {})
        if counters:
            txt = " &nbsp;|&nbsp; ".join(
                f'{escape(str(k))}: <b>{full_number(v)}</b>'
                for k, v in sorted(counters.items(), key=lambda kv: -kv[1])
            )
        else:
            txt = f'<span style="color:{muted};">Nothing yet</span>'
        self._set_label("counters", self.counters_label, txt)

        # Settings
        cfg = getattr(brain, "cfg", None) or {}
        items = []
        for key, label, default in SETTINGS:
            value = cfg.get(key, default)
            if isinstance(value, bool):
                text = "yes" if value else "no"
            elif isinstance(value, (int, float)):
                text = f"{value:,}"
            elif isinstance(value, (list, tuple, set)):
                text = ", ".join(map(str, value)) if value else "(none)"
            else:
                text = str(value)
            items.append((label, escape(text), None))
        self._set_label("settings", self.settings_label, self._table2(items))

        # Events: newest first, only touch the widget when content changed
        events = sorted(list(getattr(brain, "events", []) or []), key=lambda e: e[0], reverse=True)[:MAX_EVENTS]
        lines = [
            f'{time.strftime("%H:%M:%S", time.localtime(ts))}  {text}'
            for ts, text in events
        ]
        content = "\n".join(lines)
        if self._last.get("events") != content:
            self._last["events"] = content
            bar = self.events_view.verticalScrollBar()
            pos = bar.value()
            self.events_view.setPlainText(content)
            bar.setValue(pos)
