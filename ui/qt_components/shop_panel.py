"""
Shop Panel Component

Displays shop inventory and purchase information.
"""

from PyQt6.QtWidgets import QWidget, QTextEdit, QVBoxLayout

from .theme import VSCodeTheme


class ShopPanel(QWidget):
    """Panel for displaying shop info"""

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
        """Update shop display"""
        text = []

        # Parse shop data for restock timers and inventory
        shops = slot_data.get("shops", {})

        if shops:
            text.append("🛒 Shop Inventory:\n")

            shop_types = [
                ("seed", "🌱 Seeds"),
                ("tool", "🔧 Tools"),
                ("egg", "🥚 Eggs"),
                ("decor", "🎨 Decor"),
            ]

            # Show inventory for each shop type with timer in header
            for shop_key, shop_name in shop_types:
                shop_info = shops.get(shop_key, {})
                inventory = shop_info.get("inventory", [])
                seconds = shop_info.get("secondsUntilRestock", 0)

                # Format timer
                if seconds > 0:
                    hours = seconds // 3600
                    minutes = (seconds % 3600) // 60
                    secs = seconds % 60

                    if hours > 0:
                        time_str = f"{hours}h {minutes}m {secs}s"
                    elif minutes > 0:
                        time_str = f"{minutes}m {secs}s"
                    else:
                        time_str = f"{secs}s"
                    timer_display = f"(Restock: {time_str})"
                else:
                    timer_display = "(Available!)"

                if inventory:
                    # Header with timer
                    text.append(f"\n{shop_name} Stock {timer_display}:")

                    # Show all items (in stock and out of stock)
                    has_stock = False
                    for item in inventory:
                        item_type = item.get("itemType")
                        stock = item.get("initialStock", 0)

                        # Get item name based on type
                        if item_type == "Seed":
                            name = item.get("species", "Unknown")
                        elif item_type == "Tool":
                            name = item.get("toolId", "Unknown")
                        elif item_type == "Egg":
                            name = item.get("eggId", "Unknown")
                        elif item_type == "Decor":
                            name = item.get("decorId", "Unknown")
                        else:
                            name = "Unknown"

                        if stock > 0:
                            text.append(f"  {name:<20} ({stock} left)")
                            has_stock = True
                        else:
                            text.append(f"  {name:<20} (Out of stock)")

                    if not has_stock:
                        text.append(f"  All items currently out of stock")
        else:
            text.append("🛒 Shop:\n")
            text.append("\n  Shop data not available yet.")
            text.append("\n  Timers will appear when:")
            text.append("  • You visit a shop in-game")
            text.append("  • The server sends shop data")

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
