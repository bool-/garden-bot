"""
Pets and eggs: the active team, the bench (inventory pets and what the
brain plans for each), and eggs growing on garden tiles.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from automation import economy as eco

from .model import (
    ability_name,
    bench_pets,
    bench_plan,
    egg_groups,
    food_for,
    hatches_per_day,
    hunger_color,
    hunger_of,
    pet_name,
    stamp_of,
)
from .theme import Carbon as C, duration, full_number, spaced
from .widgets import CarbonTable, Cell, FlatButton, KpiTile, Page, gap_grid, section_head, set_text

BENCH_ROWS = 12


def _hatched_this_session(brain) -> int:
    total = 0
    for _ts, text in list(getattr(brain, "events", []) or []):
        t = str(text)
        if t.startswith("hatched "):
            try:
                total += int(t.split()[1])
            except (IndexError, ValueError):
                pass
    return total


class PetsPage(Page):
    def __init__(self):
        super().__init__(
            "Pets and eggs",
            "Team is chosen by stamp (Rainbow ×50, Gold ×25), then money abilities, then size. "
            "Bigger pets reach a higher max strength, so their abilities fire more often.")

        team_box = QVBoxLayout()
        team_box.setSpacing(0)
        head, _ = section_head("Active team")
        team_box.addWidget(head)
        self.team = CarbonTable([
            ("Pet", 136), ("Stamp", 128), (">Size", 80), (">Max strength", 128), (">Score", 96),
            ("Hunger", 260), ("Eats", 128), ("Abilities", "stretch"),
        ], row_height=40)
        team_box.addWidget(self.team)
        self.outer.addLayout(team_box)

        grid = QGridLayout()
        grid.setHorizontalSpacing(C.S5)
        grid.setVerticalSpacing(0)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        bench = QVBoxLayout()
        bench.setSpacing(0)
        head, self.bench_note = section_head("Bench", "Pets you owned before the bot are never sold")
        bench.addWidget(head)
        self.bench = CarbonTable([("Pet", "stretch"), (">Size", 72), (">Score", 88), ("Plan", 196), ("", 112)],
                                 row_height=40)
        self.bench.horizontalHeaderItem(4).setText("")
        bench.addWidget(self.bench)
        bench.addStretch(1)
        grid.addLayout(bench, 0, 0, Qt.AlignmentFlag.AlignTop)

        eggs = QVBoxLayout()
        eggs.setSpacing(0)
        head, self.eggs_note = section_head("Eggs", "")
        eggs.addWidget(head)
        self.k_hatched = KpiTile("Hatched this session")
        self.k_granters = KpiTile("Gold / Rainbow owned")
        self.k_rate = KpiTile("Hatches per day")
        tiles = gap_grid([self.k_hatched, self.k_granters, self.k_rate])
        eggs.addWidget(tiles)
        eggs.addSpacing(C.S3)
        self.eggs = CarbonTable([("Egg", 168), (">Tiles", 72), ("Progress", "stretch"), (">Next hatch", 120)],
                                row_height=40)
        eggs.addWidget(self.eggs)
        eggs.addStretch(1)
        grid.addLayout(eggs, 0, 1, Qt.AlignmentFlag.AlignTop)
        self.outer.addLayout(grid, 1)
        self._buttons = {}

    def update_data(self, snap):
        # Team
        rows = []
        for pet in snap.pets:
            hunger, cap, frac = hunger_of(pet)
            stamp, scolor = stamp_of(pet)
            food = food_for(snap, pet)
            strength = eco.pet_max_strength(pet.get("petSpecies"), pet.get("targetScale"))
            abilities = ", ".join(ability_name(a) for a in pet.get("abilities") or []) or "-"
            rows.append([
                Cell(pet_name(pet), bold=True),
                Cell(stamp, scolor, mono=True, px=12),
                Cell(f"{float(pet.get('targetScale') or 1):.2f}", mono=True, right=True),
                Cell(str(strength), mono=True, right=True),
                Cell(full_number(eco.pet_score(pet)), C.MONEY, mono=True, right=True),
                Cell(bar=(frac, hunger_color(frac, hunger), f"{full_number(hunger)} / {full_number(cap)}", 96)),
                Cell(spaced(food) if food else "-", C.TEXT_SECONDARY),
                Cell(abilities, C.TEXT_SECONDARY, tip=abilities),
            ])
        self.team.set_rows(rows, empty="No pets on the team")

        # Bench
        plan = bench_plan(snap)
        bag = sorted(bench_pets(snap), key=eco.pet_score, reverse=True)
        rows = []
        for pet in bag[:BENCH_ROWS]:
            muts = " ".join(pet.get("mutations") or [])
            name = f"{muts} {pet_name(pet)}".strip()
            what = plan.get(pet.get("id"), "-")
            rows.append([
                Cell(name, tip=", ".join(ability_name(a) for a in pet.get("abilities") or [])),
                Cell(f"{float(pet.get('targetScale') or 1):.2f}", mono=True, right=True),
                Cell(full_number(eco.pet_score(pet)), mono=True, right=True),
                Cell(what, C.TEXT_SECONDARY),
                Cell("", data=(None if what in ("Locked in game", "Brain disabled") else
                               "Swap in" if what in ("Kept, original pet", "Spare granter", "Kept, better than the team")
                               else "Keep")),
            ])
        changed = self.bench.set_rows(rows, empty="No pets in the bag")
        if changed:
            for r in range(self.bench.rowCount()):
                label = self.bench.row_data(r, 4)
                if not label:
                    self.bench.removeCellWidget(r, 4)
                    continue
                btn = FlatButton(label, bg=C.LAYER_02, hover=C.LAYER_HOVER_02, height=40)
                btn.setEnabled(False)
                btn.setToolTip("Not wired up yet: the bot decides team swaps and pet sales on its own")
                self.bench.setCellWidget(r, 4, btn)
        extra = len(bag) - BENCH_ROWS
        orig = "Pets you owned before the bot are never sold" if not snap.cfg.get("sell_original_pets") \
            else "Pets you owned before the bot may be sold"
        set_text(self.bench_note, orig + (f". {extra} more not shown" if extra > 0 else ""))

        # Eggs
        tiles = int(snap.cfg.get("egg_tiles", 0) or 0)
        share = float(snap.cfg.get("big_egg_share", 0) or 0)
        set_text(self.eggs_note, f"{tiles} tiles, {share * 100:.0f}% big eggs")
        self.k_hatched.set(full_number(_hatched_this_session(snap.brain)) if snap.brain is not None else "-")
        owned = list(snap.pets) + bench_pets(snap)
        gold = sum(1 for p in owned if eco.pet_growth_multiplier(p) == 25)
        rainbow = sum(1 for p in owned if eco.pet_growth_multiplier(p) >= 50)
        self.k_granters.set(f"{gold} / {rainbow}", value_color=C.MONEY)
        self.k_rate.set(f"{hatches_per_day(snap):,.0f}")
        rows = []
        for g in egg_groups(snap):
            left = g["left"]
            rows.append([
                Cell(spaced(g["egg"])),
                Cell(str(g["tiles"]), mono=True, right=True),
                Cell(bar=(g["frac"], C.CELL_EGG, "", 0)),
                Cell("ready" if left is not None and left <= 0 else (duration(left) if left is not None else "-"),
                     C.SUCCESS if left is not None and left <= 0 else C.TEXT_SECONDARY, mono=True, right=True),
            ])
        self.eggs.set_rows(rows, empty="No eggs growing")
