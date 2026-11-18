"""Eggs: grow and hatch eggs; every hatch is a roll for a Gold/Rainbow pet."""

from .common import *  # noqa: F401,F403
from .common import _now_ms  # noqa: F401


class EggsMixin:
    # ------------------------------------------------------------------ eggs
    def _egg_tiles(self, s) -> List[Tuple[int, dict]]:
        return [(int(t), o) for t, o in s["garden"].items() if (o or {}).get("objectType") == "egg"]

    @staticmethod
    def _egg_ready(s, obj) -> bool:
        ready_at = obj.get("maturedAt")
        if ready_at is None and obj.get("plantedAt") is not None:
            ready_at = obj["plantedAt"] + eco.egg_hatch_seconds(obj.get("eggId")) * 1000
        return ready_at is not None and s["now"] >= ready_at

    def _usable_eggs(self, s) -> Dict[str, int]:
        return {
            i["eggId"]: int(i.get("quantity", 1))
            for i in s["items"]
            if i.get("itemType") == "Egg" and i.get("eggId") and int(i.get("quantity", 1)) > 0
            and i["eggId"] not in s["locked"] and i["eggId"] not in self.never_hatch
            and i["eggId"] in eco.EGGS
        }

    async def hatch_step(self, s) -> bool:
        ready = [(t, o) for t, o in self._egg_tiles(s) if self._egg_ready(s, o)]
        if not ready:
            return False
        if INVENTORY_CAPACITY - len(s["items"]) <= 1:
            return False  # "Can't carry more": selling pets/crops frees room first
        slot_index = self.gs.get_user_slot_index()
        here = current_position(self.gs)
        ready.sort(key=lambda to: distance(here, tile_to_server(to[0], slot_index)) if here else to[0])
        hatched = 0
        for tile, obj in ready[: random.randint(2, 5)]:
            if not await walk_to_tile(self.client, self.gs, tile):
                break
            await self.client.send_command({"type": "HatchEgg", "slot": tile})
            s["garden"].pop(str(tile), None)
            hatched += 1
            await asyncio.sleep(random.uniform(0.6, 1.4))
        if hatched:
            self._log(f"hatched {hatched} egg(s)")
        return hatched > 0

    def _choose_egg(self, s) -> Optional[str]:
        """Most egg tiles hatch the fastest egg (every hatch is a Gold/Rainbow
        roll); a share hatches the biggest eggs owned, whose pets carry sell
        boosts, coin finders, weather granters and pet-mutation boosts."""
        eggs = self._usable_eggs(s)
        if not eggs:
            return None
        fast = min(eggs, key=eco.egg_hatch_seconds)
        logged_pets = set((s["data"].get("journal") or {}).get("pets") or {})

        def unlogged(e):  # chance-weighted share of this egg's pets missing from the Journal
            w = eco.EGGS[e].get("weights") or {}
            total = sum(w.values()) or 1
            return sum(v for k, v in w.items() if k not in logged_pets) / total

        journal = self._journal_active(s)
        big = max(eggs, key=lambda e: (unlogged(e) > 0 and journal, eco.EGGS[e]["price"],
                                       -eco.egg_hatch_seconds(e)))
        if big != fast:
            growing = [o.get("eggId") for _, o in self._egg_tiles(s)]
            big_now = sum(1 for e in growing if e != fast)
            share = max(self.big_egg_share, 0.5) if self.journal_first_active else self.big_egg_share
            if big_now < round(self.effective_egg_tiles * share):
                return big
        return fast
