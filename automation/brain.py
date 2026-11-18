"""
The garden brain: one loop that plays the whole game the way a person would,
one action at a time, and optimises for coins.

Every tick, in priority order (each step does one bounded chunk of work and
returns, so hungry pets are never kept waiting behind a long harvest):

  1. Pets   - keep every pet fed with the diet crop that best fits its hunger
              bar (hunger is measured in coins). Fed GoldGranter/RainbowGranter
              pets are the account's money multiplier.
  2. Shop   - on every restock, Teleport to the market and buy everything left
              in the seed, egg and tool stalls, walking stall to stall.
  3. Sell   - Teleport to the crop stand and Sell crops when the bag is filling
              up or holds something valuable. Locked items are never sold.
  4. Harvest- cheap crops as soon as they're ripe; valuable crops only once a
              pet has stamped Gold/Rainbow on them (x25/x50) - unless no
              granter pet is working, then everything ripe.
  5. Plant  - empty tiles: a small food farm per pet first, then the best
              seeds we own.

Wire formats were captured from the real web client (build 2071).
"""

import asyncio
import json
import os
import random
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from automation import economy as eco
from automation.movement import (
    current_position,
    distance,
    go_home,
    go_to_sell,
    teleport,
    tile_to_server,
    walk_to,
    walk_to_tile,
)
from utils.constants import INVENTORY_CAPACITY

GARDEN_TILES = 200
STATE_FILE = "bot_state.json"  # remembers server-rejected purchases across restarts
REJECTION_TTL_S = 24 * 3600
SCOPE = ["Room", "Quinoa"]


def _now_ms(full_state) -> int:
    try:
        return int(full_state["child"]["data"]["currentTime"])
    except Exception:
        return int(time.time() * 1000)


class Brain:
    def __init__(self, client, game_state, cfg: Dict[str, Any]):
        self.client = client
        self.gs = game_state
        self.cfg = cfg
        self.min_coins = int(cfg.get("min_coins_to_keep", 0))
        self.shops = list(cfg.get("buy_shops", ["seed", "egg", "tool"]))
        self.hold_min_base = int(cfg.get("hold_for_gold_min_base_price", 100_000))
        self.food_tiles_per_pet = int(cfg.get("food_tiles_per_pet", 2))
        self.sell_at_produce = int(cfg.get("sell_when_produce_count", 20))
        self.sell_at_value = int(cfg.get("sell_when_value_over", 5_000_000))
        self.harvest_batch = int(cfg.get("harvest_batch", 12))
        self.never_plant = set(cfg.get("never_plant", []))
        self.never_harvest = set(cfg.get("never_harvest", []))
        self._pending_harvest = set()  # (tile, slotIndex) sent, not yet removed by server
        self._bought_restocks = set()  # (shop, restockId) we already shopped
        self.tools_to_buy = set(cfg.get("tools_to_buy", []))
        self._unbuyable = self._load_unbuyable()  # (shop, item key) the server rejected

    # ------------------------------------------------------------------ state
    def _snapshot(self):
        slot = self.gs.get_player_slot()
        full = self.gs.get_full_state()
        if not slot or not full:
            return None
        data = slot.get("data") or {}
        inv = data.get("inventory") or {}
        return {
            "slot": slot,
            "data": data,
            "items": inv.get("items") or [],
            "locked": set(inv.get("favoritedItemIds") or []),
            "garden": (data.get("garden") or {}).get("tileObjects") or {},
            "pets": data.get("petSlots") or [],
            "coins": data.get("coinsCount", 0),
            "held": (slot.get("heldItem") or {}).get("itemId"),
            "shops": full["child"]["data"].get("shops") or {},
            "purchases": data.get("shopPurchases") or {},
            "now": _now_ms(full),
        }

    @staticmethod
    def _seed_counts(s) -> Dict[str, int]:
        return {
            i["species"]: int(i.get("quantity", 1))
            for i in s["items"]
            if i.get("itemType") == "Seed" and i.get("species")
        }

    def _usable_seeds(self, s) -> Dict[str, int]:
        return {
            sp: q for sp, q in self._seed_counts(s).items()
            if q > 0 and sp not in s["locked"] and sp not in self.never_plant and sp in eco.CROPS
        }

    @staticmethod
    def _produce(s) -> List[dict]:
        return [i for i in s["items"] if i.get("itemType") == "Produce" and i.get("id") not in s["locked"]]

    def _granters_working(self, s) -> bool:
        return any(
            (p.get("hunger") or 0) > 0 and eco.GRANTER_ABILITIES & set(p.get("abilities") or [])
            for p in s["pets"] if p
        )

    def _food_plan(self, s) -> Dict[str, str]:
        """pet id -> crop species we farm for it."""
        seeds = self._usable_seeds(s)
        plan = {}
        for p in s["pets"]:
            if not p:
                continue
            food = eco.best_food_species(p.get("petSpecies"), list(seeds))
            if food:
                plan[p["id"]] = food
        return plan

    # --------------------------------------------------------------- actions
    async def _send(self, msg):
        await self.client.send(msg)

    async def _select(self, s, item_id: str):
        """Hotbar/inventory click: hold an item (seed species or item uuid)."""
        if s["held"] == item_id:
            return
        await self.client.send_command({"type": "SetSelectedItem", "itemId": item_id, "decorRotation": 0})
        await self._send({"scopePath": SCOPE, "type": "PickupObject"})
        s["held"] = item_id
        await asyncio.sleep(random.uniform(0.25, 0.7))

    def _next_item_id(self, s, after_key: str) -> Optional[str]:
        """What the hand switches to if the held stack runs out (the real client
        always sends this)."""
        keys = [i.get("id") or i.get("species") or i.get("toolId") or i.get("eggId") for i in s["items"]]
        keys = [k for k in keys if k]
        if after_key in keys:
            idx = keys.index(after_key)
            for k in keys[idx + 1:] + keys[:idx]:
                if k != after_key:
                    return k
        return None

    async def _harvest_slot(self, s, tile: int, slot_index: int) -> Optional[str]:
        if not await walk_to_tile(self.client, self.gs, tile):
            return None
        crop_id = str(uuid.uuid4())
        await self.client.send_command(
            {"type": "HarvestCrop", "slot": tile, "slotsIndex": slot_index, "cropItemId": crop_id}
        )
        self._pending_harvest.add((tile, slot_index))
        s["held"] = crop_id
        return crop_id

    # ------------------------------------------------------------------ pets
    async def care_for_pets(self, s) -> bool:
        plan = self._food_plan(s)
        for pet in s["pets"]:
            if not pet:
                continue
            species = pet.get("petSpecies")
            info = eco.PETS.get(species)
            if not info:
                continue
            cap = info["hungerCap"]
            hunger = float(pet.get("hunger") or 0)
            deficit = cap - hunger
            starving = hunger < cap * 0.2
            diet = set(info["diet"])

            # 1) food already in the bag
            options = []
            for it in self._produce(s):
                if it.get("species") in diet:
                    v = eco.crop_value(it["species"], it.get("size", 50), it.get("mutations"))
                    options.append((v, "inv", it))
            # 2) ripe diet crops in the garden (cheap ones only; never stamped ones)
            for tile_id, obj in s["garden"].items():
                if (obj or {}).get("objectType") != "plant":
                    continue
                for idx, sl in enumerate(obj.get("slots") or []):
                    if not sl or sl.get("species") not in diet or s["now"] < sl.get("endTime", 0):
                        continue
                    if (int(tile_id), idx) in self._pending_harvest or eco.has_growth_mutation(sl.get("mutations")):
                        continue
                    v = eco.crop_value(sl["species"], sl.get("size", 50), sl.get("mutations"))
                    options.append((v, "garden", (int(tile_id), idx)))

            # Never feed something worth far more than a full bar.
            options = [o for o in options if o[0] <= max(cap * 2, 1)]
            if not options:
                continue
            fitting = [o for o in options if o[0] <= deficit]
            if fitting:
                choice = max(fitting, key=lambda o: o[0])
                # Only bother when a feed fills a meaningful chunk (or pet is starving).
                if not starving and choice[0] < min(deficit, cap) * 0.5:
                    continue
            elif starving:
                choice = min(options, key=lambda o: o[0])
            else:
                continue

            value, where, ref = choice
            if where == "inv":
                await self._select(s, ref["id"])
                crop_id = ref["id"]
            else:
                crop_id = await self._harvest_slot(s, *ref)
                if not crop_id:
                    return False
                await asyncio.sleep(random.uniform(0.6, 1.4))
            await self.client.send_command(
                {"type": "FeedPet", "petItemId": pet["id"], "cropItemId": crop_id},
                **({"successorItemId": nxt} if (nxt := self._next_item_id(s, crop_id)) else {}),
            )
            print(f"[brain] fed {species} ({int(hunger)}/{cap}) with {ref['species'] if where == 'inv' else 'fresh ' + plan.get(pet['id'], 'crop')} worth {value:,}")
            await asyncio.sleep(random.uniform(0.8, 2.0))
            return True
        return False

    # ------------------------------------------------------------------ shop
    def _tool_needed(self, s, tool_id) -> bool:
        """Tool shop: only what the bot actually uses (config tools_to_buy), plus
        a Shovel if the account somehow has none."""
        if tool_id in self.tools_to_buy:
            return True
        if tool_id == "Shovel":
            return not any(i.get("toolId") == "Shovel" for i in s["items"])
        return False

    @staticmethod
    def _owned_decor(s) -> set:
        owned = {i.get("decorId") for i in s["items"] if i.get("decorId")}
        garden = (s["data"].get("garden") or {})
        for objs in (garden.get("tileObjects") or {}, garden.get("boardwalkTileObjects") or {}):
            owned |= {o.get("decorId") for o in objs.values() if o and o.get("decorId")}
        return owned

    def _shopping_list(self, s) -> Dict[str, List[Tuple[dict, int]]]:
        wanted: Dict[str, List[Tuple[dict, int]]] = {}
        coins = s["coins"]
        for shop_key in self.shops:
            shop = s["shops"].get(shop_key) or {}
            restock = shop.get("restockId")
            if not restock:
                continue
            mine = s["purchases"].get(shop_key) or {}
            bought = (mine.get("purchases") or {}) if mine.get("restockId") == restock else {}
            for entry in shop.get("inventory") or []:
                if not entry:
                    continue
                key = entry.get("species") or entry.get("eggId") or entry.get("toolId") or entry.get("decorId")
                left = int(entry.get("initialStock", 0)) - int(bought.get(key, 0))
                if left <= 0:
                    continue
                if entry.get("itemType") == "Decor":
                    continue  # buildings: one-time purchases, never bought automatically
                if shop_key == "tool" and not self._tool_needed(s, key):
                    continue
                if (shop_key, key) in self._unbuyable or (shop_key, restock) in self._bought_restocks:
                    continue
                if shop_key == "seed":
                    price = eco.CROPS.get(key, {}).get("seedPrice", 0)
                    affordable = int((coins - self.min_coins) // price) if price else left
                    left = min(left, max(0, affordable))
                    if left <= 0:
                        continue
                    coins -= price * left
                elif coins < max(self.min_coins, 1_000_000):
                    continue  # eggs/tools only once the account has some money
                item = {k: v for k, v in entry.items() if k != "initialStock"}
                wanted.setdefault(shop_key, []).append((item, left))
        return wanted

    @staticmethod
    def _load_unbuyable() -> set:
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                saved = json.load(f).get("unbuyable", [])
        except (OSError, ValueError):
            return set()
        now = time.time()
        return {(shop, key) for shop, key, at in saved if now - at < REJECTION_TTL_S}

    def _learn_rejections(self):
        learned = False
        while self.client.rejected_commands:
            cmd = self.client.rejected_commands.pop()
            if cmd.get("type") == "PurchaseShopItem":
                item = cmd.get("item") or {}
                key = item.get("species") or item.get("eggId") or item.get("toolId") or item.get("decorId")
                if (cmd.get("shop"), key) not in self._unbuyable:
                    self._unbuyable.add((cmd.get("shop"), key))
                    learned = True
        if learned:
            try:
                try:
                    with open(STATE_FILE, encoding="utf-8") as f:
                        state = json.load(f)
                except (OSError, ValueError):
                    state = {}
                known = {(s_, k) for s_, k, _ in state.get("unbuyable", [])}
                now = time.time()
                state["unbuyable"] = [x for x in state.get("unbuyable", []) if now - x[2] < REJECTION_TTL_S] + [
                    [s_, k, now] for s_, k in self._unbuyable if (s_, k) not in known
                ]
                with open(STATE_FILE, "w", encoding="utf-8") as f:
                    json.dump(state, f, indent=2)
            except OSError:
                pass

    async def shop_if_restocked(self, s) -> bool:
        if not self.shops:
            return False
        self._learn_rejections()
        wanted = self._shopping_list(s)
        if not wanted:
            return False
        for k in wanted:  # one trip per restock per stall, even if the server lags
            self._bought_restocks.add((k, (s["shops"].get(k) or {}).get("restockId")))

        stall_seed = eco.STALLS["seed"]["stand"]
        await teleport(self.client, self.gs,
                       random.randint(*stall_seed["x"]), random.randint(*stall_seed["y"]))
        order = [k for k in ("seed", "egg", "tool", "decor") if k in wanted]
        total = 0
        for shop_key in order:
            stand = eco.STALLS[shop_key]["stand"]
            here = current_position(self.gs)
            if not (here and stand["x"][0] <= here[0] <= stand["x"][1] and stand["y"][0] <= here[1] <= stand["y"][1]):
                await walk_to(self.client, self.gs, random.randint(*stand["x"]), random.randint(*stand["y"]))
                await asyncio.sleep(random.uniform(0.3, 0.8))
            await self._send({"scopePath": SCOPE, "type": "SetPlayerInteraction", "interaction": shop_key})
            await asyncio.sleep(random.uniform(0.9, 1.8))
            for item, count in wanted[shop_key]:
                for _ in range(count):
                    if not self.client.is_connected:
                        return True
                    await self.client.send_command(
                        {"type": "PurchaseShopItem", "shop": shop_key, "viewMode": "grid", "item": item}
                    )
                    total += 1
                    await asyncio.sleep(random.uniform(0.25, 0.75))
                await asyncio.sleep(random.uniform(0.3, 0.9))
            await self._send({"scopePath": SCOPE, "type": "SetPlayerInteraction", "interaction": None})
            await asyncio.sleep(random.uniform(0.4, 1.0))
        print(f"[brain] restock: bought {total} item(s) from {', '.join(order)}")
        await go_home(self.client, self.gs)
        return True

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
        print(f"[brain] sold {len(produce)} crop(s), ~{value:,} coins")
        await asyncio.sleep(random.uniform(0.8, 1.8))
        await go_home(self.client, self.gs)
        await asyncio.sleep(random.uniform(1.0, 2.0))  # let the emptied bag arrive
        return True

    # --------------------------------------------------------------- harvest
    def _harvest_targets(self, s) -> List[Tuple[int, int, int]]:
        food_species = set(self._food_plan(s).values())
        hold = self._granters_working(s)
        out = []
        for tile_id, obj in s["garden"].items():
            if (obj or {}).get("objectType") != "plant":
                continue
            for idx, sl in enumerate(obj.get("slots") or []):
                if not sl or s["now"] < sl.get("endTime", 0):
                    continue
                sp = sl.get("species")
                key = (int(tile_id), idx)
                if key in self._pending_harvest or sp in self.never_harvest or sp in food_species:
                    continue
                muts = sl.get("mutations") or []
                if hold and eco.base_price(sp) >= self.hold_min_base and not eco.has_growth_mutation(muts):
                    continue  # wait for a Gold/Rainbow stamp
                out.append((int(tile_id), idx, eco.crop_value(sp, sl.get("size", 50), muts)))
        return out

    async def harvest_batch_step(self, s) -> bool:
        targets = self._harvest_targets(s)
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
            print(f"[brain] harvested {done} crop(s)")
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

    async def plant_step(self, s) -> bool:
        empties = self._empty_tiles(s)
        if not empties:
            return False
        species = self._choose_seed(s)
        if not species:
            return False
        slot_index = self.gs.get_user_slot_index()
        here = current_position(self.gs)
        empties.sort(key=lambda t: distance(here, tile_to_server(t, slot_index)) if here else t)
        planted = 0
        for tile in empties[: random.randint(3, 8)]:
            species = self._choose_seed(s)
            if not species:
                break
            if not await walk_to_tile(self.client, self.gs, tile):
                break
            await self._select(s, species)
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
            print(f"[brain] planted {planted} tile(s)")
        return planted > 0

    # ------------------------------------------------------------------ loop
    async def tick(self) -> bool:
        s = self._snapshot()
        if not s:
            return False
        # Forget pending harvests the server has now removed or regrown.
        still = set()
        for tile, idx in self._pending_harvest:
            obj = s["garden"].get(str(tile))
            sl = ((obj or {}).get("slots") or [None] * (idx + 1))
            sl = sl[idx] if idx < len(sl) else None
            if sl and s["now"] >= sl.get("endTime", 0):
                still.add((tile, idx))
        self._pending_harvest = still

        for step in (self.care_for_pets, self.shop_if_restocked, self.sell_if_needed,
                     self.harvest_batch_step, self.plant_step):
            if await step(s):
                return True
        return False

    async def run(self):
        try:
            await asyncio.sleep(random.uniform(14, 22))  # page load + look around
            while True:
                did = False
                try:
                    async with self.client.body_lock:
                        did = await self.tick()
                except RuntimeError:
                    break  # connection lost
                except Exception as e:  # keep playing; log and carry on
                    print(f"[brain] error: {e!r}")
                await asyncio.sleep(random.uniform(1.5, 4.0) if did else random.uniform(8, 20))
        except asyncio.CancelledError:
            pass
