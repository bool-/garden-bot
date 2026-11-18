"""
Shop: what each stall has left this restock, when it restocks, and manual
buying (select a row, then Buy selected, or double-click a row).
"""

import asyncio
from typing import Any, Dict

from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout

from automation import economy as eco

from .theme import Carbon as C, clock, full_number, short_number, spaced
from .widgets import CarbonTable, Cell, Page, secondary_button, section_head, set_text

STALLS = [("seed", "Seed stall"), ("egg", "Egg stall"), ("tool", "Tool stall"), ("decor", "Decor stall")]


def _item_key(item: dict) -> str:
    return item.get("species") or item.get("eggId") or item.get("toolId") or item.get("decorId") or "?"


def _price(shop: str, item: dict):
    if "price" in item:
        return item["price"]
    if shop == "seed":
        return (eco.CROPS.get(item.get("species")) or {}).get("seedPrice")
    if shop == "egg":
        return (eco.EGGS.get(item.get("eggId")) or {}).get("price")
    return None


class ShopPage(Page):
    def __init__(self):
        super().__init__("Shop", "")
        self.client_holder: Dict[str, Any] = {}
        self.sections = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(C.S5)
        grid.setVerticalSpacing(C.S4)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        for i, (key, title) in enumerate(STALLS):
            box = QVBoxLayout()
            box.setSpacing(0)
            head, note = section_head(title, "")
            box.addWidget(head)
            table = CarbonTable([("Item", "stretch"), (">Price", 112), (">Left", 104)], selectable=True,
                                fit_height=False)
            table.cellDoubleClicked.connect(lambda r, _c, k=key: self._buy_row(k, r))
            box.addWidget(table, 1)
            foot = QHBoxLayout()
            foot.setContentsMargins(0, C.S2, 0, 0)
            foot.addStretch(1)
            buy = secondary_button("Buy selected")
            buy.clicked.connect(lambda _=False, k=key: self._buy_selected(k))
            foot.addWidget(buy)
            box.addLayout(foot)
            grid.addLayout(box, i // 2, i % 2)
            self.sections[key] = {"table": table, "note": note, "buy": buy}
        self.outer.addLayout(grid, 1)

    def set_client_holder(self, client_holder: Dict[str, Any]):
        self.client_holder = client_holder if client_holder is not None else {}

    # -------------------------------------------------------------- buying
    def _buy_selected(self, shop: str):
        t = self.sections[shop]["table"]
        if t.currentRow() >= 0:
            self._buy_row(shop, t.currentRow())

    def _buy_row(self, shop: str, row: int):
        item = self.sections[shop]["table"].row_data(row)
        if item and int(item.get("_left", 0) or 0) > 0:
            self._purchase(shop, item)

    def _purchase(self, shop: str, data: dict):
        client = self.client_holder.get("client")
        loop = self.client_holder.get("loop")
        if not client or not loop or not getattr(client, "is_connected", False):
            print("Cannot purchase: not connected")
            return
        # v2036: PurchaseShopItem in a QuinoaCommand; item keyed on itemType.
        kind = data.get("itemType")
        item = {"itemType": kind}
        for field in ("species", "toolId", "eggId", "decorId"):  # never the UI-only _left
            if field in data:
                item[field] = data[field]
        command = {"type": "PurchaseShopItem", "shop": shop, "viewMode": "grid", "item": item}
        print(f"Purchasing {_item_key(data)} from the {shop} stall")
        asyncio.run_coroutine_threadsafe(client.send_command(command), loop)

    # -------------------------------------------------------------- update
    def update_data(self, snap):
        shops = snap.quinoa.get("shops") or {}
        buying = set(snap.cfg.get("buy_shops") or []) if snap.brain is not None else set()
        self.set_helper(
            ("The bot buys everything left in the " + ", ".join(s for s, _ in STALLS if s in buying)
             + " stalls at each restock. " if buying else "")
            + "Select an item and Buy selected (or double-click) to buy one yourself.")
        purchases = snap.data.get("shopPurchases") or {}
        for key, sec in self.sections.items():
            shop = shops.get(key) or {}
            mine = purchases.get(key) or {}
            bought = (mine.get("purchases") or {}) if mine.get("restockId") == shop.get("restockId") else {}
            deadline = shop.get("deadlineMs")
            if deadline:
                left = (deadline - snap.now_ms) / 1000
                set_text(sec["note"], f"Restock in {clock(left)}" if left > 0 else "Restocked")
            else:
                set_text(sec["note"], "")
            rows = []
            any_stock = False
            for item in shop.get("inventory") or []:
                if not item:
                    continue
                stock = max(0, int(item.get("initialStock", 0) or 0) - int(bought.get(_item_key(item), 0) or 0))
                item = dict(item, _left=stock)
                any_stock = any_stock or stock > 0
                price = _price(key, item)
                rows.append([
                    Cell(spaced(_item_key(item)), C.TEXT_PRIMARY if stock else C.TEXT_HELPER, data=item),
                    Cell(short_number(price) if price is not None else "-",
                         C.MONEY if stock and price is not None else C.TEXT_HELPER, mono=True, right=True),
                    Cell(full_number(stock) if stock else "Sold out",
                         C.TEXT_SECONDARY if stock else C.TEXT_HELPER, mono=bool(stock), right=True),
                ])
            sec["table"].set_rows(rows, empty="No stock data yet")
            sec["buy"].setEnabled(any_stock)


ShopPanel = ShopPage
