"""
Qt Components for Magic Garden Bot

Modular UI components following VS Code Dark+ theme.
"""

from .theme import VSCodeTheme
from .garden_canvas import GardenCanvas, GardenWidget
from .connection_panel import ConnectionPanel
from .inventory_panel import InventoryPanel
from .pet_panel import PetPanel
from .shop_panel import ShopPanel
from .journal_panel import JournalPanel
from .stats_panel import StatsPanel
from .console_widget import ConsoleWidget, ConsoleRedirector

__all__ = [
    'VSCodeTheme',
    'GardenCanvas',
    'GardenWidget',
    'ConnectionPanel',
    'InventoryPanel',
    'PetPanel',
    'ShopPanel',
    'JournalPanel',
    'StatsPanel',
    'ConsoleWidget',
    'ConsoleRedirector',
]
