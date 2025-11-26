"""
Inventory Panel Component

Displays player inventory with selectable seeds for planting.
"""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QGroupBox,
    QScrollArea,
    QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal

from .theme import VSCodeTheme


class InventoryPanel(QWidget):
    """Panel for displaying inventory with selectable seeds"""

    # Signals emitted when selection changes
    seed_selected = pyqtSignal(str)  # Emits species name
    egg_selected = pyqtSignal(str)   # Emits egg ID
    selection_made = pyqtSignal()    # Emitted when any selection is made (for focus return)

    def __init__(self):
        super().__init__()
        self.theme = VSCodeTheme
        self._selected_seed = None
        self._selected_egg = None
        self._last_seeds = {}
        self._last_eggs = {}
        self._last_other_data = ""

        self._setup_ui()

    def _setup_ui(self):
        """Setup the UI components"""
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Coins display
        self.coins_label = QLabel("💰 Coins: 0")
        self.coins_label.setStyleSheet(f"""
            font-size: 14pt;
            font-weight: bold;
            color: {self.theme.WARNING};
            padding: 8px;
            background-color: {self.theme.BG_SIDEBAR};
            border: 1px solid {self.theme.BORDER};
            border-radius: 4px;
        """)
        layout.addWidget(self.coins_label)

        # Seeds section (selectable)
        seeds_group = QGroupBox("🌱 Seeds (Click to Select)")
        seeds_layout = QVBoxLayout()
        seeds_layout.setContentsMargins(4, 8, 4, 4)

        self.seeds_list = QListWidget()
        self.seeds_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.seeds_list.setMinimumHeight(120)
        self.seeds_list.setMaximumHeight(200)
        self.seeds_list.itemClicked.connect(self._on_seed_clicked)
        self.seeds_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {self.theme.BG_INPUT};
                border: 1px solid {self.theme.BORDER};
                border-radius: 4px;
            }}
            QListWidget::item {{
                padding: 6px 8px;
                border-bottom: 1px solid {self.theme.BORDER};
            }}
            QListWidget::item:selected {{
                background-color: {self.theme.ACCENT_BLUE};
                color: white;
            }}
            QListWidget::item:hover {{
                background-color: {self.theme.BG_HOVER};
            }}
        """)
        seeds_layout.addWidget(self.seeds_list)

        # Selected seed indicator
        self.selected_label = QLabel("Selected: None")
        self.selected_label.setStyleSheet(f"""
            color: {self.theme.SUCCESS};
            font-weight: bold;
            padding: 4px;
        """)
        seeds_layout.addWidget(self.selected_label)

        seeds_group.setLayout(seeds_layout)
        layout.addWidget(seeds_group)

        # Eggs section (selectable)
        eggs_group = QGroupBox("🥚 Eggs (Click to Select)")
        eggs_layout = QVBoxLayout()
        eggs_layout.setContentsMargins(4, 8, 4, 4)

        self.eggs_list = QListWidget()
        self.eggs_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.eggs_list.setMinimumHeight(60)
        self.eggs_list.setMaximumHeight(100)
        self.eggs_list.itemClicked.connect(self._on_egg_clicked)
        self.eggs_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {self.theme.BG_INPUT};
                border: 1px solid {self.theme.BORDER};
                border-radius: 4px;
            }}
            QListWidget::item {{
                padding: 6px 8px;
                border-bottom: 1px solid {self.theme.BORDER};
            }}
            QListWidget::item:selected {{
                background-color: {self.theme.ACCENT_TEAL};
                color: white;
            }}
            QListWidget::item:hover {{
                background-color: {self.theme.BG_HOVER};
            }}
        """)
        eggs_layout.addWidget(self.eggs_list)

        # Selected egg indicator
        self.selected_egg_label = QLabel("Selected: None")
        self.selected_egg_label.setStyleSheet(f"""
            color: {self.theme.ACCENT_TEAL};
            font-weight: bold;
            padding: 4px;
        """)
        eggs_layout.addWidget(self.selected_egg_label)

        eggs_group.setLayout(eggs_layout)
        layout.addWidget(eggs_group)

        # Other inventory (tools, produce) - scrollable text
        other_group = QGroupBox("📦 Other Items")
        other_layout = QVBoxLayout()
        other_layout.setContentsMargins(4, 8, 4, 4)

        self.other_label = QLabel()
        self.other_label.setWordWrap(True)
        self.other_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.other_label.setStyleSheet(f"""
            color: {self.theme.TEXT_PRIMARY};
            padding: 8px;
            background-color: {self.theme.BG_INPUT};
            border: 1px solid {self.theme.BORDER};
            border-radius: 4px;
        """)

        scroll = QScrollArea()
        scroll.setWidget(self.other_label)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        other_layout.addWidget(scroll)

        other_group.setLayout(other_layout)
        layout.addWidget(other_group, stretch=1)

        self.setLayout(layout)

    def _on_seed_clicked(self, item: QListWidgetItem):
        """Handle seed selection"""
        species = item.data(Qt.ItemDataRole.UserRole)
        if species:
            self._selected_seed = species
            self._selected_egg = None  # Clear egg selection
            self.selected_label.setText(f"Selected: {species}")
            self.selected_label.setStyleSheet(f"""
                color: {self.theme.SUCCESS};
                font-weight: bold;
                padding: 4px;
            """)
            self.selected_egg_label.setText("Selected: None")
            self.selected_egg_label.setStyleSheet(f"""
                color: {self.theme.TEXT_SECONDARY};
                font-weight: bold;
                padding: 4px;
            """)
            self.eggs_list.clearSelection()
            self.seed_selected.emit(species)
            self.selection_made.emit()

    def _on_egg_clicked(self, item: QListWidgetItem):
        """Handle egg selection"""
        egg_id = item.data(Qt.ItemDataRole.UserRole)
        if egg_id:
            self._selected_egg = egg_id
            self._selected_seed = None  # Clear seed selection
            self.selected_egg_label.setText(f"Selected: {egg_id}")
            self.selected_egg_label.setStyleSheet(f"""
                color: {self.theme.ACCENT_TEAL};
                font-weight: bold;
                padding: 4px;
            """)
            self.selected_label.setText("Selected: None")
            self.selected_label.setStyleSheet(f"""
                color: {self.theme.TEXT_SECONDARY};
                font-weight: bold;
                padding: 4px;
            """)
            self.seeds_list.clearSelection()
            self.egg_selected.emit(egg_id)
            self.selection_made.emit()

    def get_selected_seed(self) -> str | None:
        """Get the currently selected seed species"""
        return self._selected_seed

    def get_selected_egg(self) -> str | None:
        """Get the currently selected egg ID"""
        return self._selected_egg

    def update_data(self, slot_data: dict):
        """Update inventory display"""
        # Coins
        coins = slot_data.get("coinsCount", 0)
        self.coins_label.setText(f"💰 Coins: {coins:,}")

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

        # Update seeds list only if changed
        if seeds != self._last_seeds:
            self._last_seeds = seeds.copy()
            self._update_seeds_list(seeds)

        # Update eggs list only if changed
        if eggs != self._last_eggs:
            self._last_eggs = eggs.copy()
            self._update_eggs_list(eggs)

        # Update other items (tools and produce only)
        other_text = self._format_other_items(tools, produce)
        if other_text != self._last_other_data:
            self._last_other_data = other_text
            self.other_label.setText(other_text)

    def _update_seeds_list(self, seeds: dict):
        """Update the seeds list widget"""
        # Remember current selection
        current_selection = self._selected_seed

        self.seeds_list.clear()

        if not seeds:
            item = QListWidgetItem("No seeds available")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.seeds_list.addItem(item)
            return

        # Add seeds sorted by name
        for species, count in sorted(seeds.items()):
            item = QListWidgetItem(f"{species} ({count})")
            item.setData(Qt.ItemDataRole.UserRole, species)
            self.seeds_list.addItem(item)

            # Re-select if this was the previous selection
            if species == current_selection:
                item.setSelected(True)
                self.seeds_list.setCurrentItem(item)

        # If selection was cleared but we had one, try to restore or clear
        if current_selection and current_selection not in seeds:
            self._selected_seed = None
            self.selected_label.setText("Selected: None (out of stock)")
            self.selected_label.setStyleSheet(f"""
                color: {self.theme.ACCENT_ORANGE};
                font-weight: bold;
                padding: 4px;
            """)

    def _update_eggs_list(self, eggs: dict):
        """Update the eggs list widget"""
        # Remember current selection
        current_selection = self._selected_egg

        self.eggs_list.clear()

        if not eggs:
            item = QListWidgetItem("No eggs available")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.eggs_list.addItem(item)
            return

        # Add eggs sorted by name
        for egg_id, count in sorted(eggs.items()):
            item = QListWidgetItem(f"{egg_id} ({count})")
            item.setData(Qt.ItemDataRole.UserRole, egg_id)
            self.eggs_list.addItem(item)

            # Re-select if this was the previous selection
            if egg_id == current_selection:
                item.setSelected(True)
                self.eggs_list.setCurrentItem(item)

        # If selection was cleared but we had one, try to restore or clear
        if current_selection and current_selection not in eggs:
            self._selected_egg = None
            self.selected_egg_label.setText("Selected: None (out of stock)")
            self.selected_egg_label.setStyleSheet(f"""
                color: {self.theme.ACCENT_ORANGE};
                font-weight: bold;
                padding: 4px;
            """)

    def _format_other_items(self, tools: dict, produce: list) -> str:
        """Format tools and produce as text"""
        lines = []

        # Tools
        if tools:
            lines.append("🔧 Tools:")
            for tool_type, count in sorted(tools.items()):
                lines.append(f"  {tool_type}: {count}")
        else:
            lines.append("🔧 Tools: None")

        lines.append("")

        # Produce
        if produce:
            lines.append(f"🌾 Produce: {len(produce)} items")
            produce_count = {}
            for item in produce:
                species = item.get("species", "Unknown")
                produce_count[species] = produce_count.get(species, 0) + 1

            for species, count in sorted(produce_count.items()):
                lines.append(f"  {species}: {count}")
        else:
            lines.append("🌾 Produce: None")

        return "\n".join(lines)
