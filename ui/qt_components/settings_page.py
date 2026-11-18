"""
Settings: the brain's live-editable settings. Reads brain.settings(),
writes with brain.apply_settings({key: value}) (applied live, saved to
bot_config.json).
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from .theme import Carbon as C, body_font, compact_number, font, label_font, title_font
from .widgets import FlatButton, NumberStepper, Toggle, make_label, set_text

SAVED_TEXT = "Saved. Applies on the next loop."


def _coins(v):
    return compact_number(v)


def _plain(v):
    return compact_number(v)


def _pct(v):
    return f"{compact_number(v)}%"


def _times(v):
    return f"{compact_number(v)}×"


# (title, about, rows). Row: ("num", key, label, help, step, lo, hi, fmt, scale)
#                            ("toggle", key, label, help) | ("shop", stall, label, help)
GROUPS = [
    ("Money", "What to hold for a Gold/Rainbow stamp and when to sell.", [
        ("num", "hold_for_gold_min_base_price", "Hold crops for a stamp above",
         "Ripe crops worth less are sold right away", 50_000, 0, 10_000_000, _coins, 1),
        ("num", "cheap_crop_value", "Cheap crop value",
         "Harvested last, only when there is nothing else to do", 5_000, 0, 1_000_000, _coins, 1),
        ("num", "sell_when_produce_count", "Sell when the bag holds",
         "Crops. Also sells when the bag is nearly full", 5, 5, 95, _plain, 1),
    ]),
    ("Shopping", "Restocks are bought on the next loop after they appear.", [
        ("shop", "seed", "Seed stall", "Buy every seed left at each restock"),
        ("shop", "egg", "Egg stall", "Buy every egg left at each restock"),
        ("shop", "tool", "Tool stall", "Only tools the bot uses; never buildings or one-use items"),
        ("num", "min_coins_to_keep", "Never spend below",
         "Coins the bot keeps no matter what", 1_000_000, 0, 1_000_000_000_000, _coins, 1),
    ]),
    ("Garden", "How empty and low-value tiles are used.", [
        ("num", "food_tiles_per_pet", "Food tiles per pet",
         "Grows the diet crop that best fits each pet", 1, 0, 10, _plain, 1),
        ("num", "upgrade_when_better_by", "Replace plants worth less by",
         "Digs up and replants with the best seed in hand", 1, 2, 100, _times, 1),
    ]),
    ("Eggs", "Every hatch is a roll for a Gold or Rainbow pet.", [
        ("num", "egg_tiles", "Egg tiles", "Tiles kept growing eggs", 1, 0, 60, _plain, 1),
        ("num", "big_egg_share", "Big egg share",
         "The rest hatch the fastest egg for more rolls", 5, 0, 100, _pct, 100),
    ]),
    ("Pets", "Team changes and selling.", [
        ("num", "spare_granters_to_keep", "Spare granters to keep",
         "Gold/Rainbow pets kept on the bench", 1, 0, 10, _plain, 1),
        ("toggle", "sell_original_pets", "Sell pets I had before the bot", "Off keeps them on the bench forever"),
    ]),
    ("Journal", "Each variant is logged once. Needs a Camera.", [
        ("toggle", "journal", "Fill the Journal", "Paused automatically while the account has no Camera"),
        ("num", "journal_tiles", "Journal tiles", "One tile per species never logged", 1, 0, 20, _plain, 1),
    ]),
]

INT_KEYS = {"hold_for_gold_min_base_price", "cheap_crop_value", "sell_when_produce_count", "min_coins_to_keep",
            "food_tiles_per_pet", "egg_tiles", "spare_granters_to_keep", "journal_tiles"}


class SettingRow(QFrame):
    def __init__(self, label: str, help_text: str, control: QWidget):
        super().__init__()
        self.setObjectName("settingRow")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, C.S3, 0, C.S3 + 1)
        lay.setSpacing(C.S4)
        text = QVBoxLayout()
        text.setSpacing(C.S1)
        text.addWidget(make_label(label, body_font()))
        text.addWidget(make_label(help_text, label_font(), C.TEXT_SECONDARY, wrap=True))
        lay.addLayout(text, 1)
        lay.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)


class SettingsPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("page")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.brain = None
        self.controls = {}  # key -> (kind, widget, scale)  (shops: key "shop:seed")
        self._loaded = None
        self.saved_labels = []

        root = QHBoxLayout(self)
        root.setContentsMargins(C.S5, C.S4, C.S5, C.S4)
        root.setSpacing(C.S5)

        nav = QWidget()
        nav.setFixedWidth(240)
        nl = QVBoxLayout(nav)
        nl.setContentsMargins(0, 0, 0, 0)
        nl.setSpacing(0)
        title = make_label("Settings", title_font())
        title.setFixedHeight(28)
        nl.addWidget(title)
        nl.addSpacing(C.S3)
        self.nav_buttons = []
        for i, (name, _about, _rows) in enumerate(GROUPS):
            b = FlatButton(name, hover=C.LAYER_HOVER_01, fg=C.TEXT_SECONDARY, sel_bg=C.LAYER_01,
                           sel_fg=C.TEXT_PRIMARY, marker="left", height=40)
            b.setSizePolicy(b.sizePolicy().Policy.Expanding, b.sizePolicy().Policy.Fixed)
            b.clicked.connect(lambda _=False, idx=i: self.show_section(idx))
            self.nav_buttons.append(b)
            nl.addWidget(b)
        nl.addStretch(1)
        nl.addWidget(make_label("Changes apply on the bot's next loop and are saved to bot_config.json.",
                                label_font(), C.TEXT_SECONDARY, wrap=True))
        root.addWidget(nav)

        right_box = QWidget()
        right_box.setMaximumWidth(760)
        right = QVBoxLayout(right_box)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        self.disabled = make_label("Brain disabled. Enable brain.enabled in bot_config.json to edit these.",
                                   body_font(), C.WARNING, wrap=True)
        self.disabled.setVisible(False)
        right.addWidget(self.disabled)
        self.stack = QStackedWidget()
        self.stack.setMaximumWidth(760)
        for name, about, rows in GROUPS:
            sec = QWidget()
            sl = QVBoxLayout(sec)
            sl.setContentsMargins(0, 0, 0, 0)
            sl.setSpacing(0)
            h2 = make_label(name, font(16, "semibold"))
            h2.setFixedHeight(22)
            sl.addWidget(h2)
            sl.addSpacing(C.S1)
            sl.addWidget(make_label(about, body_font(), C.TEXT_SECONDARY, wrap=True))
            sl.addSpacing(C.S3)
            for row in rows:
                sl.addWidget(SettingRow(row[2], row[3], self._control(row)))
            sl.addSpacing(C.S3)
            saved = make_label("", label_font(), C.SUCCESS)
            self.saved_labels.append(saved)
            sl.addWidget(saved)
            sl.addStretch(1)
            self.stack.addWidget(sec)
        right.addWidget(self.stack, 1)
        root.addWidget(right_box, 100)
        root.addStretch(1)
        self.show_section(0)

    # -------------------------------------------------------------- build
    def _control(self, row):
        kind = row[0]
        if kind in ("toggle", "shop"):
            t = Toggle()
            ckey = row[1] if kind == "toggle" else f"shop:{row[1]}"
            t.toggled.connect(lambda on, k=ckey: self._changed(k, on))
            self.controls[ckey] = (kind, t, 1)
            return t
        _, key, _label, _help, step, lo, hi, fmt, scale = row
        s = NumberStepper(step, lo, hi, fmt)
        s.valueChanged.connect(lambda v, k=key: self._changed(k, v))
        self.controls[key] = ("num", s, scale)
        return s

    def show_section(self, idx: int):
        self.stack.setCurrentIndex(idx)
        for i, b in enumerate(self.nav_buttons):
            b.set_selected(i == idx)

    def _note(self, text: str, color: str):
        for lab in self.saved_labels:
            set_text(lab, text)
            lab.setStyleSheet(f"color: {color};")

    @property
    def saved_text(self) -> str:
        return self.saved_labels[0].text() if self.saved_labels else ""

    # -------------------------------------------------------------- data
    def _changed(self, ckey: str, value):
        brain = self.brain
        if brain is None:
            return
        if ckey.startswith("shop:"):
            shops = [s for s in ("seed", "egg", "tool") if (self.controls[f"shop:{s}"][1].isChecked())]
            # keep any non-UI stalls the config already lists
            current = list(self._settings().get("buy_shops") or [])
            extra = [s for s in current if s not in ("seed", "egg", "tool")]
            update = {"buy_shops": shops + extra}
        else:
            kind, _w, scale = self.controls[ckey]
            if kind == "toggle":
                update = {ckey: bool(value)}
            else:
                v = float(value) / scale
                update = {ckey: int(round(v)) if ckey in INT_KEYS else (round(v, 4) if scale != 1 else
                                                                        (int(v) if float(v).is_integer() else v))}
        try:
            brain.apply_settings(update)
        except Exception as e:  # never let a bad write kill the UI
            self._note(f"Could not save: {e}", C.ERROR)
            return
        self._note(SAVED_TEXT, C.SUCCESS)
        self._loaded = None  # re-read on next update

    def _settings(self) -> dict:
        try:
            return dict(self.brain.settings()) if self.brain is not None else {}
        except Exception:
            return dict(getattr(self.brain, "cfg", None) or {})

    def update_data(self, snap):
        self.brain = snap.brain
        enabled = self.brain is not None
        self.disabled.setVisible(not enabled)
        for _k, (_kind, w, _s) in self.controls.items():
            w.setEnabled(enabled)
        if not enabled:
            return
        cfg = self._settings()
        if cfg == self._loaded:
            return
        self._loaded = cfg
        shops = set(cfg.get("buy_shops") or [])
        for ckey, (kind, w, scale) in self.controls.items():
            if ckey.startswith("shop:"):
                w.setChecked(ckey.split(":", 1)[1] in shops)
            elif kind == "toggle":
                w.setChecked(bool(cfg.get(ckey)))
            else:
                try:
                    w.setValue(float(cfg.get(ckey, 0) or 0) * scale)
                except (TypeError, ValueError):
                    pass
