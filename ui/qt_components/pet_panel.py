"""
Pet Panel Component

Displays active pets (hunger vs. cap, diet, what the brain farms for them,
abilities) and pets in inventory.
"""

from html import escape

from PyQt6.QtWidgets import QWidget, QTextEdit, QVBoxLayout

from automation.economy import PETS, GRANTER_ABILITIES
from .theme import VSCodeTheme

BAR_WIDTH = 24
GOLD = "#ffd700"


def _bar(frac: float, color: str, empty_color: str) -> str:
    frac = max(0.0, min(1.0, frac))
    filled = int(round(frac * BAR_WIDTH))
    return (
        f'<span style="color:{color};">{"&#9608;" * filled}</span>'
        f'<span style="color:{empty_color};">{"&#9617;" * (BAR_WIDTH - filled)}</span>'
    )


class PetPanel(QWidget):
    """Panel for displaying pets"""

    def __init__(self):
        super().__init__()
        self.theme = VSCodeTheme
        self._last_content = ""  # Track last content to prevent unnecessary updates

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        layout.addWidget(self.text_edit)

        self.setLayout(layout)

    def _active_pet_html(self, pet: dict, food_plan: dict) -> str:
        t = self.theme
        species = pet.get("petSpecies") or "Unknown"
        mutations = pet.get("mutations") or []
        abilities = pet.get("abilities") or []
        xp = pet.get("xp", 0) or 0
        hunger = pet.get("hunger", 0) or 0
        info = PETS.get(species) or {}
        cap = info.get("hungerCap") or 0
        diet = info.get("diet") or []
        granters = [a for a in abilities if a in GRANTER_ABILITIES]
        starving = hunger <= 0

        title = f'<b style="font-size:11pt;">{escape(species)}</b>'
        if mutations:
            title += f' <span style="color:{GOLD};">[{escape(", ".join(mutations))}]</span>'
        if granters:
            title += f' <span style="color:{GOLD};"><b>&#9733; {escape("/".join(g.replace("Granter", "") for g in granters))} multiplier</b></span>'

        if cap:
            pct = hunger / cap * 100
            hunger_txt = f"{hunger:,.0f}/{cap:,} ({pct:.0f}%)"
            frac = hunger / cap
        else:
            hunger_txt = f"{hunger:,.0f}/? "
            frac = 0
        if starving:
            color = t.ERROR
            status = f' <b style="color:{t.ERROR};background-color:#5a1d1d;">&nbsp;STARVING&nbsp;</b>'
        elif frac < 0.15:
            color = t.WARNING
            status = f' <b style="color:{t.WARNING};">low</b>'
        else:
            color = t.SUCCESS
            status = ""

        lines = [title]
        lines.append(
            f'<span style="font-family:Consolas,monospace;">{_bar(frac, color, '#5a5a5a')}</span> '
            f'<b style="color:{color};">{hunger_txt}</b>{status}'
        )
        muted = t.TEXT_SECONDARY
        lines.append(f'<span style="color:{muted};">XP</span> {xp:,.0f}')
        if abilities:
            ab = ", ".join(
                f'<span style="color:{GOLD};"><b>{escape(a)}</b></span>' if a in GRANTER_ABILITIES else escape(a)
                for a in abilities
            )
            lines.append(f'<span style="color:{muted};">Abilities</span> {ab}')
        if diet:
            lines.append(f'<span style="color:{muted};">Diet</span> {escape(", ".join(diet))}')
        food = (food_plan or {}).get(species)
        if food_plan is not None:
            if food:
                lines.append(f'<span style="color:{muted};">Brain farms</span> <b style="color:{t.ACCENT_TEAL};">{escape(food)}</b>')
            else:
                lines.append(f'<span style="color:{muted};">Brain farms</span> <span style="color:{t.WARNING};">nothing (no usable diet seed)</span>')
        return "<br>".join(lines)

    def update_data(self, slot_data: dict, plan: dict = None):
        """Update pet display. plan = brain.last_plan (optional)"""
        t = self.theme
        food_plan = None
        if plan:
            food_plan = plan.get("food_plan") or {}

        html = []

        # Active pets
        active_pets = [p for p in (slot_data.get("petSlots") or []) if p]
        if active_pets:
            html.append(f'<h3 style="color:{t.ACCENT_BLUE};">Active Pets ({len(active_pets)})</h3>')
            for pet in active_pets:
                html.append(self._active_pet_html(pet, food_plan))
                html.append('<hr>')
        else:
            html.append("<b>Active Pets:</b> None")

        # Inventory pets
        items_list = (slot_data.get("inventory") or {}).get("items", [])
        pets = [item for item in items_list if item.get("itemType") == "Pet"]

        if pets:
            html.append(f'<h3 style="color:{t.ACCENT_BLUE};">Pets in Inventory ({len(pets)})</h3>')
            for i, pet in enumerate(pets[:10]):
                species = pet.get("petSpecies", "Unknown")
                xp = pet.get("xp", 0) or 0
                mutations = pet.get("mutations") or []
                abilities = pet.get("abilities") or []
                mutation_str = f' <span style="color:{GOLD};">[{escape(", ".join(mutations))}]</span>' if mutations else ""
                ab = ", ".join(
                    f'<span style="color:{GOLD};">{escape(a)}</span>' if a in GRANTER_ABILITIES else escape(a)
                    for a in abilities[:3]
                ) or "None"
                html.append(f'{i + 1:2d}. <b>{escape(species)}</b>{mutation_str} (XP {xp:,.0f}) - {ab}')
            if len(pets) > 10:
                html.append(f"... and {len(pets) - 10} more pets")
        else:
            html.append("<br><b>Pets in Inventory:</b> None")

        # Only update if content changed (prevents interrupting copy/paste)
        new_content = "".join(
            h if h.startswith("<h3") or h == "<hr>" else h + "<br>" for h in html
        )
        if new_content != self._last_content:
            self._last_content = new_content
            scrollbar = self.text_edit.verticalScrollBar()
            scroll_pos = scrollbar.value()
            self.text_edit.setHtml(new_content)
            scrollbar.setValue(scroll_pos)
