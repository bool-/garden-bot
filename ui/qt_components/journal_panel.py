"""
Journal: which crop and pet variants the account has logged, what is still
missing, and whether the bot can log right now (it needs a Camera).
"""

from PyQt6.QtWidgets import QGridLayout, QVBoxLayout

from automation import economy as eco

from .dashboard_page import AttentionRow
from .model import has_camera, journal_counts
from .theme import Carbon as C, spaced
from .widgets import CarbonTable, Cell, Page, section_head, set_text


def _rows(entries: dict, all_species):
    logged, missing = [], []
    for sp in sorted(set(all_species) | set(entries)):
        variants = [v.get("variant") for v in (entries.get(sp) or {}).get("variantsLogged") or [] if v.get("variant")]
        if variants:
            logged.append([Cell(spaced(sp)), Cell(str(len(variants)), mono=True, right=True),
                           Cell(", ".join(variants), C.TEXT_SECONDARY, tip=", ".join(variants))])
        else:
            missing.append([Cell(spaced(sp), C.TEXT_HELPER), Cell("0", C.TEXT_HELPER, mono=True, right=True),
                            Cell("Not logged", C.TEXT_HELPER)])
    return logged + missing


class JournalPage(Page):
    def __init__(self):
        super().__init__("Journal", "Each crop and pet variant is logged once.")
        self.camera = AttentionRow()
        self.camera.set("info", "Journal paused", "No Camera on this account, and the Camera isn't sold in shops. "
                        "Logging starts once you have one.", "")
        self.outer.addWidget(self.camera)
        grid = QGridLayout()
        grid.setHorizontalSpacing(C.S5)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        box = QVBoxLayout()
        box.setSpacing(0)
        head, self.crop_note = section_head("Crops", "")
        box.addWidget(head)
        self.crops = CarbonTable([("Crop", 180), (">Variants", 96), ("Logged", "stretch")], fit_height=False)
        box.addWidget(self.crops, 1)
        grid.addLayout(box, 0, 0)
        box = QVBoxLayout()
        box.setSpacing(0)
        head, self.pet_note = section_head("Pets", "")
        box.addWidget(head)
        self.pets = CarbonTable([("Pet", 180), (">Variants", 96), ("Logged", "stretch")], fit_height=False)
        box.addWidget(self.pets, 1)
        grid.addLayout(box, 0, 1)
        self.outer.addLayout(grid, 1)

    def update_data(self, snap):
        crops, crops_total, pets, pets_total = journal_counts(snap)
        on = bool(snap.cfg.get("journal")) if snap.brain is not None else False
        state = "The bot fills it as it plays" if on and has_camera(snap) else (
            "Filling is off in Settings" if snap.brain is not None and not on else
            "Brain disabled" if snap.brain is None else "Paused until the account has a Camera")
        self.set_helper(f"Each crop and pet variant is logged once. Crops {crops} of {crops_total} logged, "
                        f"pets {pets} of {pets_total}. {state}.")
        self.camera.setVisible(snap.ready and on and not has_camera(snap))
        j = snap.data.get("journal") or {}
        set_text(self.crop_note, f"{crops} of {crops_total} species")
        set_text(self.pet_note, f"{pets} of {pets_total} species")
        self.crops.set_rows(_rows(j.get("produce") or {}, eco.CROPS), empty="No journal data yet")
        self.pets.set_rows(_rows(j.get("pets") or {}, eco.PETS), empty="No journal data yet")


JournalPanel = JournalPage
