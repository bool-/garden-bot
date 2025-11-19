"""
Pet Panel Component

Displays active pets and pets in inventory.
"""

from PyQt6.QtWidgets import QWidget, QTextEdit, QVBoxLayout

from .theme import VSCodeTheme


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

    def update_data(self, slot_data: dict):
        """Update pet display"""
        text = []

        # Active pets
        pet_slots = slot_data.get("petSlots", [])
        active_pets = []
        for pet_slot in pet_slots:
            if pet_slot:
                active_pets.append({
                    "species": pet_slot.get("petSpecies"),
                    "xp": pet_slot.get("xp", 0),
                    "hunger": pet_slot.get("hunger", 0),
                    "mutations": pet_slot.get("mutations", []),
                    "abilities": pet_slot.get("abilities", []),
                })

        if active_pets:
            text.append(f"Active Pets ({len(active_pets)}):")
            for pet in active_pets:
                species = pet.get("species", "Unknown")
                xp = pet.get("xp", 0)
                hunger = pet.get("hunger", 0)
                mutations = pet.get("mutations", [])
                abilities = pet.get("abilities", [])

                mutation_str = f" [{', '.join(mutations)}]" if mutations else ""
                text.append(f"  • {species}{mutation_str}")
                text.append(f"    XP: {xp:,} | Hunger: {hunger:.0f}")
                if abilities:
                    text.append(f"    Abilities: {', '.join(abilities)}")
        else:
            text.append("Active Pets: None")

        # Inventory pets
        inv_data = slot_data.get("inventory", {})
        items_list = inv_data.get("items", [])
        pets = [item for item in items_list if item.get("itemType") == "Pet"]

        if pets:
            text.append(f"\n\nPets in Inventory ({len(pets)}):")
            for i, pet in enumerate(pets[:10]):
                species = pet.get("petSpecies", "Unknown")
                xp = pet.get("xp", 0)
                mutations = pet.get("mutations", [])
                abilities = pet.get("abilities", [])

                mutation_str = f" [{', '.join(mutations)}]" if mutations else ""
                ability_str = ", ".join(abilities[:2]) if abilities else "None"
                text.append(f"  {i+1:2d}. {species}{mutation_str} (XP: {xp:,}) - {ability_str}")

            if len(pets) > 10:
                text.append(f"\n  ... and {len(pets) - 10} more pets")
        else:
            text.append("\n\nPets in Inventory: None")

        # Only update if content changed (prevents interrupting copy/paste)
        new_content = "\n".join(text)
        if new_content != self._last_content:
            self._last_content = new_content
            # Save scroll position
            scrollbar = self.text_edit.verticalScrollBar()
            scroll_pos = scrollbar.value()
            # Update content
            self.text_edit.setPlainText(new_content)
            # Restore scroll position
            scrollbar.setValue(scroll_pos)
