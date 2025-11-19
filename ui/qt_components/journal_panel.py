"""
Journal Panel Component

Displays journal entries for produce and pets with variants logged.
"""

from PyQt6.QtWidgets import QWidget, QTextEdit, QVBoxLayout

from .theme import VSCodeTheme


class JournalPanel(QWidget):
    """Panel for displaying journal entries"""

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
        """Update journal display"""
        text = []

        # Parse journal data
        journal = slot_data.get("journal", {})

        if journal:
            text.append("📖 Journal Entries:\n")

            # Produce section
            produce = journal.get("produce", {})
            if produce:
                text.append("🌾 Produce Discovered:")
                produce_count = 0
                for species, data in sorted(produce.items()):
                    variants = data.get("variantsLogged", [])
                    if variants:
                        produce_count += 1
                        variant_names = []
                        for variant in variants:
                            variant_name = variant.get("variant", "Unknown")
                            variant_names.append(variant_name)

                        # Compact formatting: show variants on next line if > 3
                        variant_count = len(variants)
                        variants_str = ", ".join(variant_names)

                        if variant_count <= 3:
                            # Short list - show on one line
                            text.append(f"  {species:<20} ({variant_count} variant{'s' if variant_count != 1 else ''}: {variants_str})")
                        else:
                            # Long list - show count on first line, variants indented on next
                            text.append(f"  {species:<20} ({variant_count} variants):")
                            text.append(f"    {variants_str}")

                text.append(f"\n  Total: {produce_count} produce types\n")
            else:
                text.append("🌾 Produce Discovered: None\n")

            # Pets section
            pets = journal.get("pets", {})
            if pets:
                text.append("🐾 Pets Discovered:")
                pets_count = 0
                for species, data in sorted(pets.items()):
                    variants = data.get("variantsLogged", [])
                    if variants:
                        pets_count += 1
                        variant_names = []
                        for variant in variants:
                            variant_name = variant.get("variant", "Unknown")
                            variant_names.append(variant_name)

                        # Compact formatting: show variants on next line if > 3
                        variant_count = len(variants)
                        variants_str = ", ".join(variant_names)

                        if variant_count <= 3:
                            # Short list - show on one line
                            text.append(f"  {species:<20} ({variant_count} variant{'s' if variant_count != 1 else ''}: {variants_str})")
                        else:
                            # Long list - show count on first line, variants indented on next
                            text.append(f"  {species:<20} ({variant_count} variants):")
                            text.append(f"    {variants_str}")

                text.append(f"\n  Total: {pets_count} pet types")
            else:
                text.append("🐾 Pets Discovered: None")

        else:
            text.append("📖 Journal:\n")
            text.append("\n  Journal data not available yet.")
            text.append("\n  Your journal will populate as you:")
            text.append("  • Harvest new produce")
            text.append("  • Discover new pets")
            text.append("  • Find variant mutations")

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
