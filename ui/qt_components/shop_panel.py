"""
Shop Panel Component

Displays shop inventory with clickable items for purchasing.
"""

import asyncio
from typing import Optional, Dict, Any

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QGroupBox,
    QPushButton,
    QScrollArea,
    QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal

from .theme import VSCodeTheme


class ShopPanel(QWidget):
    """Panel for displaying shop with clickable purchase items"""

    # Signal emitted when purchase is requested
    purchase_requested = pyqtSignal(str, dict)  # shop_type, item_data

    def __init__(self):
        super().__init__()
        self.theme = VSCodeTheme
        self.client_holder = None
        self._last_shops_data = {}

        self._setup_ui()

    def set_client_holder(self, client_holder: Dict[str, Any]):
        """Set the client holder for sending purchase messages"""
        self.client_holder = client_holder

    def _setup_ui(self):
        """Setup the UI components"""
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Instructions
        info_label = QLabel("Click an item to purchase it")
        info_label.setStyleSheet(f"""
            color: {self.theme.TEXT_SECONDARY};
            font-style: italic;
            padding: 4px;
        """)
        layout.addWidget(info_label)

        # Create scrollable area for shop sections
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(8)

        # Shop sections
        self.shop_sections = {}
        shop_types = [
            ("seed", "🌱 Seeds"),
            ("tool", "🔧 Tools"),
            ("egg", "🥚 Eggs"),
            ("decor", "🎨 Decor"),
        ]

        for shop_key, shop_name in shop_types:
            section = self._create_shop_section(shop_key, shop_name)
            self.shop_sections[shop_key] = section
            self.scroll_layout.addWidget(section["group"])

        self.scroll_layout.addStretch()

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, stretch=1)

        self.setLayout(layout)

    def _create_shop_section(self, shop_key: str, shop_name: str) -> dict:
        """Create a shop section with list and timer"""
        group = QGroupBox(shop_name)
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 8, 4, 4)
        layout.setSpacing(4)

        # Timer label
        timer_label = QLabel("Restock: --")
        timer_label.setStyleSheet(f"""
            color: {self.theme.TEXT_SECONDARY};
            font-size: 9pt;
        """)
        layout.addWidget(timer_label)

        # Item list
        item_list = QListWidget()
        item_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        item_list.setMinimumHeight(80)
        item_list.setMaximumHeight(120)
        item_list.itemDoubleClicked.connect(
            lambda item, sk=shop_key: self._on_item_double_clicked(sk, item)
        )
        item_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {self.theme.BG_INPUT};
                border: 1px solid {self.theme.BORDER};
                border-radius: 4px;
            }}
            QListWidget::item {{
                padding: 4px 8px;
                border-bottom: 1px solid {self.theme.BORDER};
            }}
            QListWidget::item:selected {{
                background-color: {self.theme.ACCENT_BLUE};
            }}
            QListWidget::item:hover {{
                background-color: {self.theme.BG_HOVER};
            }}
        """)
        layout.addWidget(item_list)

        # Buy button
        buy_button = QPushButton("Buy Selected")
        buy_button.clicked.connect(lambda: self._on_buy_clicked(shop_key))
        buy_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.theme.SUCCESS};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {self.theme.ACCENT_BLUE};
            }}
            QPushButton:disabled {{
                background-color: {self.theme.BORDER};
                color: {self.theme.TEXT_SECONDARY};
            }}
        """)
        layout.addWidget(buy_button)

        group.setLayout(layout)

        return {
            "group": group,
            "timer_label": timer_label,
            "item_list": item_list,
            "buy_button": buy_button,
        }

    def _on_item_double_clicked(self, shop_key: str, item: QListWidgetItem):
        """Handle double-click to purchase"""
        item_data = item.data(Qt.ItemDataRole.UserRole)
        if item_data and item_data.get("stock", 0) > 0:
            self._purchase_item(shop_key, item_data)

    def _on_buy_clicked(self, shop_key: str):
        """Handle buy button click"""
        section = self.shop_sections.get(shop_key)
        if not section:
            return

        current_item = section["item_list"].currentItem()
        if not current_item:
            print(f"No item selected in {shop_key} shop")
            return

        item_data = current_item.data(Qt.ItemDataRole.UserRole)
        if item_data and item_data.get("stock", 0) > 0:
            self._purchase_item(shop_key, item_data)
        else:
            print("Item out of stock")

    def _purchase_item(self, shop_key: str, item_data: dict):
        """Send purchase message to server"""
        if not self.client_holder:
            print("Cannot purchase: client not available")
            return

        client = self.client_holder.get("client")
        loop = self.client_holder.get("loop")

        if not client or not loop or not client.is_connected:
            print("Cannot purchase: not connected")
            return

        item_type = item_data.get("itemType")
        item_name = item_data.get("name", "Unknown")

        # Build purchase message based on item type
        message = {
            "scopePath": ["Room", "Quinoa"],
            "type": "BuyShopItem",
            "shopType": shop_key,
        }

        if item_type == "Seed":
            message["species"] = item_data.get("species")
        elif item_type == "Tool":
            message["toolId"] = item_data.get("toolId")
        elif item_type == "Egg":
            message["eggId"] = item_data.get("eggId")
        elif item_type == "Decor":
            message["decorId"] = item_data.get("decorId")

        print(f"Purchasing {item_name} from {shop_key} shop...")
        asyncio.run_coroutine_threadsafe(client.send(message), loop)

        # Emit signal for any listeners
        self.purchase_requested.emit(shop_key, item_data)

    def update_data(self, slot_data: dict):
        """Update shop display"""
        shops = slot_data.get("shops", {})

        if not shops:
            # No shop data yet
            for section in self.shop_sections.values():
                section["timer_label"].setText("Restock: No data")
                section["item_list"].clear()
                item = QListWidgetItem("Visit shop in-game to see items")
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                section["item_list"].addItem(item)
                section["buy_button"].setEnabled(False)
            return

        for shop_key, section in self.shop_sections.items():
            shop_info = shops.get(shop_key, {})
            inventory = shop_info.get("inventory", [])
            seconds = shop_info.get("secondsUntilRestock", 0)

            # Update timer
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
                section["timer_label"].setText(f"Restock in: {time_str}")
                section["timer_label"].setStyleSheet(f"""
                    color: {self.theme.ACCENT_ORANGE};
                    font-size: 9pt;
                """)
            else:
                section["timer_label"].setText("✓ Restocked!")
                section["timer_label"].setStyleSheet(f"""
                    color: {self.theme.SUCCESS};
                    font-size: 9pt;
                    font-weight: bold;
                """)

            # Update item list (only if changed to avoid flicker)
            current_items = self._get_inventory_signature(inventory)
            if current_items != self._last_shops_data.get(shop_key):
                self._last_shops_data[shop_key] = current_items
                self._update_shop_list(section, shop_key, inventory)

    def _get_inventory_signature(self, inventory: list) -> str:
        """Get a signature string for inventory comparison"""
        items = []
        for item in inventory:
            name = self._get_item_name(item)
            stock = item.get("initialStock", 0)
            items.append(f"{name}:{stock}")
        return "|".join(items)

    def _get_item_name(self, item: dict) -> str:
        """Get display name for an item"""
        item_type = item.get("itemType")
        if item_type == "Seed":
            return item.get("species", "Unknown")
        elif item_type == "Tool":
            return item.get("toolId", "Unknown")
        elif item_type == "Egg":
            return item.get("eggId", "Unknown")
        elif item_type == "Decor":
            return item.get("decorId", "Unknown")
        return "Unknown"

    def _update_shop_list(self, section: dict, shop_key: str, inventory: list):
        """Update a shop's item list"""
        item_list = section["item_list"]
        item_list.clear()

        has_stock = False

        for item in inventory:
            name = self._get_item_name(item)
            stock = item.get("initialStock", 0)
            price = item.get("price", 0)

            if stock > 0:
                display_text = f"{name} - {price}💰 ({stock} left)"
                has_stock = True
            else:
                display_text = f"{name} - SOLD OUT"

            list_item = QListWidgetItem(display_text)

            # Store item data for purchase
            item_data = {
                "itemType": item.get("itemType"),
                "name": name,
                "stock": stock,
                "price": price,
            }
            # Copy relevant IDs
            if "species" in item:
                item_data["species"] = item["species"]
            if "toolId" in item:
                item_data["toolId"] = item["toolId"]
            if "eggId" in item:
                item_data["eggId"] = item["eggId"]
            if "decorId" in item:
                item_data["decorId"] = item["decorId"]

            list_item.setData(Qt.ItemDataRole.UserRole, item_data)

            # Style based on stock
            if stock == 0:
                list_item.setForeground(self.theme.get_qcolor(self.theme.TEXT_SECONDARY))
                list_item.setFlags(list_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)

            item_list.addItem(list_item)

        section["buy_button"].setEnabled(has_stock)

        if not inventory:
            item = QListWidgetItem("No items available")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            item_list.addItem(item)
            section["buy_button"].setEnabled(False)
