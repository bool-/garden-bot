"""
Inventory Panel Component

Displays player inventory including seeds, tools, eggs, and produce.
"""

from PyQt6.QtWidgets import QWidget, QTextEdit, QVBoxLayout
from PyQt6.QtCore import Qt

from .theme import VSCodeTheme


class InventoryPanel(QWidget):
    """Panel for displaying inventory"""

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
        """Update inventory display"""
        text = []

        # Coins
        coins = slot_data.get("coinsCount", 0)
        text.append(f"💰 Coins: {coins:,}\n")

        # Parse inventory
        inv_data = slot_data.get("inventory", {})
        items_list = inv_data.get("items", [])

        seeds = {}
        tools = {}
        eggs = {}
        produce = []

        for item in items_list:
            item_type = item.get("itemType")
            quantity = item.get("quantity", 0)

            if item_type == "Seed" and "species" in item:
                seeds[item["species"]] = quantity
            elif item_type == "Tool" and "toolId" in item:
                tools[item["toolId"]] = quantity
            elif item_type == "Egg" and "eggId" in item:
                eggs[item["eggId"]] = quantity
            elif item_type == "Produce":
                produce.append({
                    "species": item.get("species"),
                    "mutations": item.get("mutations", []),
                })

        # Format inventory
        if seeds:
            text.append("\n🌱 Seeds:")
            for seed_type, count in sorted(seeds.items()):
                text.append(f"  {seed_type:<25} {count:>5}")
        else:
            text.append("\n🌱 Seeds: None")

        if tools:
            text.append("\n\n🔧 Tools:")
            for tool_type, count in sorted(tools.items()):
                text.append(f"  {tool_type:<25} {count:>5}")
        else:
            text.append("\n\n🔧 Tools: None")

        if eggs:
            text.append("\n\n🥚 Eggs:")
            for egg_type, count in sorted(eggs.items()):
                text.append(f"  {egg_type:<25} {count:>5}")
        else:
            text.append("\n\n🥚 Eggs: None")

        if produce:
            text.append(f"\n\n🌾 Produce: {len(produce)} items")
            produce_count = {}
            for item in produce:
                species = item.get("species", "Unknown")
                produce_count[species] = produce_count.get(species, 0) + 1

            for species, count in sorted(produce_count.items()):
                text.append(f"  {species:<25} {count:>5}")

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
