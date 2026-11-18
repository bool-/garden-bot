"""
Inventory: seeds and eggs (select one to plant by hand while paused),
crops in the bag, tools.
"""

from collections import defaultdict
from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QGridLayout, QVBoxLayout

from automation import economy as eco

from .theme import Carbon as C, duration, full_number, short_number, spaced
from .widgets import CarbonTable, Cell, Page, make_label, section_head, set_color, set_text
from .theme import label_font


class InventoryPage(Page):
    selection_made = pyqtSignal()

    def __init__(self):
        super().__init__("Inventory", "")
        self._seed: Optional[str] = None
        self._egg: Optional[str] = None

        grid = QGridLayout()
        grid.setHorizontalSpacing(C.S5)
        grid.setVerticalSpacing(C.S4)
        for i in range(3):
            grid.setColumnStretch(i, 1)

        col = QVBoxLayout()
        col.setSpacing(0)
        head, self.seed_note = section_head("Seeds", "")
        col.addWidget(head)
        self.seeds = CarbonTable([("Seed", "stretch"), (">Count", 80), (">Base price", 112)],
                                 selectable=True, fit_height=False)
        self.seeds.cellClicked.connect(lambda r, _c: self._pick("seed", r))
        col.addWidget(self.seeds, 1)
        grid.addLayout(col, 0, 0)

        col = QVBoxLayout()
        col.setSpacing(0)
        head, self.crop_note = section_head("Crops", "")
        col.addWidget(head)
        self.crops = CarbonTable([("Crop", "stretch"), (">Count", 80), (">Value", 112)], fit_height=False)
        col.addWidget(self.crops, 1)
        grid.addLayout(col, 0, 1)

        col = QVBoxLayout()
        col.setSpacing(0)
        head, self.egg_note = section_head("Eggs", "")
        col.addWidget(head)
        self.eggs = CarbonTable([("Egg", "stretch"), (">Count", 80), (">Hatch time", 112)], selectable=True)
        self.eggs.cellClicked.connect(lambda r, _c: self._pick("egg", r))
        col.addWidget(self.eggs)
        col.addSpacing(C.S4)
        head, _ = section_head("Tools", "")
        col.addWidget(head)
        self.tools = CarbonTable([("Tool", "stretch"), (">Count", 80)])
        col.addWidget(self.tools)
        col.addSpacing(C.S4)
        self.selected = make_label("Nothing selected for hand planting", label_font(), C.TEXT_SECONDARY, wrap=True)
        col.addWidget(self.selected)
        col.addStretch(1)
        grid.addLayout(col, 0, 2)
        self.outer.addLayout(grid, 1)

    # -------------------------------------------------------------- selection
    def _pick(self, kind: str, row: int):
        table = self.seeds if kind == "seed" else self.eggs
        value = table.row_data(row)
        if not value:
            return
        if kind == "seed":
            self._seed, self._egg = value, None
            self.eggs.clearSelection()
        else:
            self._egg, self._seed = value, None
            self.seeds.clearSelection()
        self._render_selected()
        self.selection_made.emit()

    def _render_selected(self):
        if self._seed:
            set_text(self.selected, f"Selected {spaced(self._seed)} seed. While paused, E plants it on the tile you stand on.")
            set_color(self.selected, C.TEXT_PRIMARY)
        elif self._egg:
            set_text(self.selected, f"Selected {spaced(self._egg)}. While paused, E plants it on the tile you stand on.")
            set_color(self.selected, C.TEXT_PRIMARY)
        else:
            set_text(self.selected, "Nothing selected for hand planting")
            set_color(self.selected, C.TEXT_SECONDARY)

    def get_selected_seed(self) -> Optional[str]:
        return self._seed

    def get_selected_egg(self) -> Optional[str]:
        return self._egg

    # -------------------------------------------------------------- update
    def update_data(self, snap):
        seeds, eggs, tools = defaultdict(int), defaultdict(int), defaultdict(int)
        crops = defaultdict(lambda: [0, 0])
        pets = 0
        for it in snap.items:
            kind = it.get("itemType")
            q = int(it.get("quantity", 1) or 0)
            if kind == "Seed" and it.get("species"):
                seeds[it["species"]] += q
            elif kind == "Egg" and it.get("eggId"):
                eggs[it["eggId"]] += q
            elif kind == "Tool" and it.get("toolId"):
                tools[it["toolId"]] += q
            elif kind == "Produce":
                c = crops[it.get("species") or "?"]
                c[0] += 1
                c[1] += eco.crop_value(it.get("species"), it.get("size", 50), it.get("mutations"))
            elif kind == "Pet":
                pets += 1
        n, cap = snap.bag
        self.set_helper(f"Bag {n} of {cap}: {sum(1 for _ in seeds)} seed stacks, {sum(v[0] for v in crops.values())} crops, "
                        f"{pets} pet{'s' if pets != 1 else ''}. Pick a seed or egg to plant by hand while the bot is paused.")

        if self._seed and self._seed not in seeds:
            self._seed = None
            self._render_selected()
        if self._egg and self._egg not in eggs:
            self._egg = None
            self._render_selected()

        rows = [[Cell(spaced(s), data=s), Cell(full_number(q), mono=True, right=True),
                 Cell(short_number(eco.base_price(s)), C.TEXT_SECONDARY, mono=True, right=True)]
                for s, q in sorted(seeds.items(), key=lambda kv: -eco.base_price(kv[0]))]
        self.seeds.set_rows(rows, empty="No seeds")
        set_text(self.seed_note, f"{sum(seeds.values()):,} seeds")
        self._reselect(self.seeds, self._seed)

        total = sum(v[1] for v in crops.values())
        rows = [[Cell(spaced(s)), Cell(full_number(v[0]), mono=True, right=True),
                 Cell(short_number(v[1]), C.MONEY, mono=True, right=True)]
                for s, v in sorted(crops.items(), key=lambda kv: -kv[1][1])]
        self.crops.set_rows(rows, empty="No crops in the bag")
        set_text(self.crop_note, f"worth {short_number(total)}" if crops else "")

        rows = [[Cell(spaced(e), data=e), Cell(full_number(q), mono=True, right=True),
                 Cell(duration(eco.egg_hatch_seconds(e)) if e in eco.EGGS else "-", C.TEXT_SECONDARY, mono=True, right=True)]
                for e, q in sorted(eggs.items(), key=lambda kv: eco.egg_hatch_seconds(kv[0]))]
        self.eggs.set_rows(rows, empty="No eggs")
        set_text(self.egg_note, f"{sum(eggs.values()):,} eggs" if eggs else "")
        self._reselect(self.eggs, self._egg)

        rows = [[Cell(spaced(t)), Cell(full_number(q), mono=True, right=True)] for t, q in sorted(tools.items())]
        self.tools.set_rows(rows, empty="No tools")

    @staticmethod
    def _reselect(table, value):
        if not value:
            return
        for r in range(table.rowCount()):
            if table.row_data(r) == value:
                if table.currentRow() != r:
                    table.selectRow(r)
                return


InventoryPanel = InventoryPage
