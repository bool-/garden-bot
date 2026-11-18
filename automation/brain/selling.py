"""Selling crops at the crop stand."""

from .common import *  # noqa: F401,F403
from .common import _now_ms  # noqa: F401


class SellingMixin:
    # ------------------------------------------------------------------ sell
    async def sell_if_needed(self, s, force: bool = False) -> bool:
        produce = self._produce(s)
        if not produce:
            return False
        value = sum(eco.crop_value(i.get("species"), i.get("size", 50), i.get("mutations")) for i in produce)
        free = INVENTORY_CAPACITY - len(s["items"])
        if not (force or len(produce) >= self.sell_at_produce or free <= 5 or value >= self.sell_at_value):
            return False
        stand = eco.STALLS["sellCrops"]["stand"]
        await teleport(self.client, self.gs, random.randint(*stand["x"]), random.randint(*stand["y"]))
        await asyncio.sleep(random.uniform(0.5, 1.3))
        await self.client.send_command({"type": "SellAllCrops"})
        self._log(f"sold {len(produce)} crop(s), ~{value:,} coins")
        await asyncio.sleep(random.uniform(0.8, 1.8))
        await go_home(self.client, self.gs)
        await asyncio.sleep(random.uniform(1.0, 2.0))  # let the emptied bag arrive
        return True
