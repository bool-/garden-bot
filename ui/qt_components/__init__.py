"""
Qt components for Garden Bot, styled with IBM Carbon (Gray 100).
"""

from .theme import Carbon, font, font_families, stylesheet
from .garden_canvas import GardenCanvas, Legend
from .garden_tabs import GardenTabs, GardenPage
from .shell import ShellHeader, StatusFooter, TABS
from .dashboard_page import DashboardPage
from .pets_page import PetsPage
from .inventory_panel import InventoryPage, InventoryPanel
from .shop_panel import ShopPage, ShopPanel
from .journal_panel import JournalPage, JournalPanel
from .settings_page import SettingsPage
from .model import Snapshot, ServerClock

__all__ = [
    "Carbon", "font", "font_families", "stylesheet",
    "GardenCanvas", "Legend", "GardenTabs", "GardenPage",
    "ShellHeader", "StatusFooter", "TABS",
    "DashboardPage", "PetsPage", "InventoryPage", "InventoryPanel",
    "ShopPage", "ShopPanel", "JournalPage", "JournalPanel", "SettingsPage",
    "Snapshot", "ServerClock",
]
