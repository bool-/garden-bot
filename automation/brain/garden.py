"""Garden: harvest (valuable first), plant, and upgrade low-value tiles."""

from .common import *  # noqa: F401,F403
from .common import _now_ms  # noqa: F401


class GardenMixin:
    # --------------------------------------------------------------- harvest
    def _harvest_targets(self, s, cheap: Optional[bool] = None) -> List[Tuple[int, int, int]]:
        food_species = set(self._food_plan(s).values())
        hold = self._has_granters(s)
        out = []
        for tile_id, obj in s["garden"].items():
            if (obj or {}).get("objectType") != "plant":
                continue
            for idx, sl in enumerate(obj.get("slots") or []):
                if not sl or s["now"] < sl.get("endTime", 0):
                    continue
                sp = sl.get("species")
                key = (int(tile_id), idx)
                muts = sl.get("mutations") or []
                if key in self._pending_harvest or sp in self.never_harvest:
                    continue
                if sp in food_species and not eco.has_growth_mutation(muts):
                    continue  # pet food; a Gold/Rainbow-stamped one is sold like any money crop
                if hold and eco.base_price(sp) >= self.hold_min_base and not eco.has_growth_mutation(muts):
                    continue  # wait for a Gold/Rainbow stamp
                value = eco.crop_value(sp, sl.get("size", 50), muts)
                if cheap is not None and (value < self.cheap_crop_value) != cheap:
                    continue
                out.append((int(tile_id), idx, value))
        return out

    async def harvest_valuable_step(self, s) -> bool:
        return await self.harvest_batch_step(s, cheap=False)

    async def harvest_cheap_step(self, s) -> bool:
        return await self.harvest_batch_step(s, cheap=True)

    async def harvest_batch_step(self, s, cheap: Optional[bool] = None) -> bool:
        targets = self._harvest_targets(s, cheap)
        if not targets:
            return False
        free = INVENTORY_CAPACITY - len(s["items"])
        if free <= 0:
            return await self.sell_if_needed(s, force=True)
        slot_index = self.gs.get_user_slot_index()
        done = 0
        # Most valuable first, then walk nearest-first through the rest.
        targets.sort(key=lambda t: -t[2])
        first = targets[0]
        rest = targets[1:]
        route = [first]
        while rest and len(route) < min(self.harvest_batch, free):
            here = tile_to_server(route[-1][0], slot_index)
            rest.sort(key=lambda t: distance(here, tile_to_server(t[0], slot_index)))
            route.append(rest.pop(0))
        for tile, idx, value in route:
            if not await self._harvest_slot(s, tile, idx):
                break
            done += 1
            await asyncio.sleep(random.uniform(0.2, 0.8))
        if done:
            self._log(f"harvested {done} crop(s)")
        return done > 0

    # ----------------------------------------------------------------- plant
    def _empty_tiles(self, s) -> List[int]:
        return [t for t in range(GARDEN_TILES) if str(t) not in s["garden"]]

    def _choose_seed(self, s) -> Optional[str]:
        seeds = self._usable_seeds(s)
        if not seeds:
            return None
        # Food farm first: N tiles of each pet's food crop.
        planted = {}
        for obj in s["garden"].values():
            sp = (obj or {}).get("species")
            if sp:
                planted[sp] = planted.get(sp, 0) + 1
        need: Dict[str, int] = {}
        for food in self._food_plan(s).values():
            need[food] = need.get(food, 0) + self.food_tiles_per_pet
        for food, n in need.items():
            if planted.get(food, 0) < n and seeds.get(food, 0) > 0:
                return food
        # Then the most valuable seed we have.
        return max(seeds, key=eco.planting_score)

    def _choose_planting(self, s) -> Optional[Tuple[str, str]]:
        """('seed', species) or ('egg', eggId) for the next empty tile."""
        seeds = self._usable_seeds(s)
        food_first = self._choose_seed(s)
        if food_first and food_first in set(self._food_plan(s).values()):
            planted = sum(1 for o in s["garden"].values() if (o or {}).get("species") == food_first)
            need = sum(self.food_tiles_per_pet for f in self._food_plan(s).values() if f == food_first)
            if planted < need:
                return ("seed", food_first)
        # Journal: one tile of every seed species we've never logged.
        wanted = self._journal_wanted_species(s)
        if wanted:
            growing = {(o or {}).get("species") for o in s["garden"].values()}
            journal_now = sum(1 for sp in growing if sp in wanted)
            todo = sorted(sp for sp in wanted if sp not in growing)
            cap = max(self.journal_tiles, 40) if self.journal_first_active else self.journal_tiles
            if todo and journal_now < cap:
                return ("seed", todo[0])
        if len(self._egg_tiles(s)) < self.effective_egg_tiles:
            egg = self._choose_egg(s)
            if egg:
                return ("egg", egg)
        if seeds:
            return ("seed", max(seeds, key=eco.planting_score))
        return None

    async def plant_step(self, s) -> bool:
        empties = self._empty_tiles(s)
        if not empties:
            return False
        if not self._choose_planting(s):
            return False
        slot_index = self.gs.get_user_slot_index()
        here = current_position(self.gs)
        empties.sort(key=lambda t: distance(here, tile_to_server(t, slot_index)) if here else t)
        planted = 0
        for tile in empties[: random.randint(3, 8)]:
            choice = self._choose_planting(s)
            if not choice:
                break
            kind, species = choice
            if not await walk_to_tile(self.client, self.gs, tile):
                break
            await self._select(s, species)
            if kind == "egg":
                await self.client.send_command({"type": "GrowEgg", "slot": tile, "eggId": species})
                s["garden"][str(tile)] = {"objectType": "egg", "eggId": species, "plantedAt": s["now"]}
                for it in s["items"]:
                    if it.get("itemType") == "Egg" and it.get("eggId") == species:
                        it["quantity"] = int(it.get("quantity", 1)) - 1
                planted += 1
                await asyncio.sleep(random.uniform(0.3, 0.9))
                continue
            nxt = self._next_item_id(s, species)
            await self.client.send_command(
                {"type": "PlantSeed", "slot": tile, "species": species},
                **({"successorItemId": nxt} if nxt else {}),
            )
            # local bookkeeping until the server frame lands
            s["garden"][str(tile)] = {"objectType": "plant", "species": species, "slots": []}
            for it in s["items"]:
                if it.get("itemType") == "Seed" and it.get("species") == species:
                    it["quantity"] = int(it.get("quantity", 1)) - 1
            planted += 1
            await asyncio.sleep(random.uniform(0.3, 0.9))
        if planted:
            self._log(f"planted {planted} tile(s)")
        return planted > 0

    # --------------------------------------------------------------- upgrade
    def _upgrade_candidates(self, s) -> List[int]:
        seeds = self._usable_seeds(s)
        if not seeds:
            return []
        best = max(seeds, key=eco.planting_score)
        best_score = eco.planting_score(best)
        spare_seeds = seeds[best] - len(self._empty_tiles(s))
        if spare_seeds <= 0:
            return []
        food = set(self._food_plan(s).values())
        out = []
        for tile_id, obj in s["garden"].items():
            if (obj or {}).get("objectType") != "plant":
                continue
            sp = obj.get("species")
            if sp in food or sp == best or eco.base_price(sp) >= self.hold_min_base:
                continue
            if sp in self._journal_wanted_species(s):
                continue  # let it ripen and get logged first
            if eco.planting_score(sp) * self.upgrade_factor > best_score:
                continue
            slots = [x for x in obj.get("slots") or [] if x]
            if any(x.get("locked") or eco.has_growth_mutation(x.get("mutations")) for x in slots):
                continue
            if any(s["now"] >= x.get("endTime", 0)
                   and eco.crop_value(sp, x.get("size", 50), x.get("mutations")) >= self.cheap_crop_value
                   for x in slots):
                continue  # a ripe crop worth having: harvest it first
            out.append(int(tile_id))
        out.sort(key=lambda t: eco.planting_score(s["garden"][str(t)].get("species")))
        return out[: min(self.upgrade_per_tick, spare_seeds)]

    async def upgrade_step(self, s) -> bool:
        tiles = self._upgrade_candidates(s)
        if not tiles:
            return False
        removed = []
        for tile in tiles:
            if not await walk_to_tile(self.client, self.gs, tile):
                break
            await self._select(s, "Shovel")
            await self.client.send_command({"type": "RemoveGardenObject", "slot": tile, "slotType": "Dirt"})
            removed.append(s["garden"].pop(str(tile), {}).get("species"))
            await asyncio.sleep(random.uniform(0.5, 1.2))
        if removed:
            self._log(f"dug up {len(removed)} low-value plant(s) ({', '.join(sorted(set(filter(None, removed))))}) to replant better")
        return bool(removed)
