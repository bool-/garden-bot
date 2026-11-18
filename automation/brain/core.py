"""The Brain: one loop that plays the whole game (see common.py for the overview)."""

from .common import *  # noqa: F401,F403
from .common import _now_ms  # noqa: F401
from .eggs import EggsMixin
from .garden import GardenMixin
from .journal import JournalMixin
from .pets import PetsMixin
from .selling import SellingMixin
from .shopping import ShoppingMixin


class Brain(PetsMixin, ShoppingMixin, SellingMixin, GardenMixin, EggsMixin, JournalMixin):
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
        # Read by the UI (another thread): plain attributes, replaced not mutated.
        self.paused = False
        self.action = "starting"
        self.events = collections.deque(maxlen=200)  # (epoch seconds, text)
        self.counters = collections.Counter()
        self.last_plan: Dict[str, Any] = {}
        self._pending_harvest = set()  # (tile, slotIndex) sent, not yet removed by server
        self._bought_restocks = set()  # (shop, restockId) we already shopped
        self.tools_to_buy = set(cfg.get("tools_to_buy", []))
        self.egg_tiles = int(cfg.get("egg_tiles", 8))
        self.big_egg_share = float(cfg.get("big_egg_share", 0.25))
        self.cheap_crop_value = int(cfg.get("cheap_crop_value", 10_000))
        self.never_hatch = set(cfg.get("never_hatch", []))
        self.sell_original_pets = bool(cfg.get("sell_original_pets", False))
        self.spare_granters = int(cfg.get("spare_granters_to_keep", 2))
        self.sell_pets_at = int(cfg.get("sell_pets_when_count", 4))
        self.upgrade_factor = float(cfg.get("upgrade_when_better_by", 10))
        self.upgrade_per_tick = int(cfg.get("upgrades_per_tick", 3))
        self._original_pets = None
        self.journal_enabled = bool(cfg.get("journal", True))
        self.journal_tiles = int(cfg.get("journal_tiles", 6))
        self._journal_pending = set()  # (species, variant) logged, not yet in server state
        self._data_build = str(eco.GAME.get("build"))  # ids of pets the account had when the bot started
        self._unbuyable = self._load_unbuyable()  # (shop, item key) the server rejected

    # ------------------------------------------------------------------ state
    def _snapshot(self):
        slot = self.gs.get_player_slot()
        full = self.gs.get_full_state()
        if not slot or not full:
            return None
        data = slot.get("data") or {}
        inv = data.get("inventory") or {}
        if self._original_pets is None:
            self._original_pets = {p.get("id") for p in (data.get("petSlots") or []) if p} | {
                i.get("id") for i in (inv.get("items") or []) if i.get("itemType") == "Pet"
            }
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

    def _log(self, text: str):
        self.events.append((time.time(), text))
        print(f"[brain] {text}")

    def _summarize(self, s) -> Dict[str, Any]:
        """Snapshot of the brain's view for the UI."""
        held = 0
        for obj in s["garden"].values():
            if (obj or {}).get("objectType") != "plant":
                continue
            for sl in obj.get("slots") or []:
                if (sl and s["now"] >= sl.get("endTime", 0)
                        and eco.base_price(sl.get("species")) >= self.hold_min_base
                        and not eco.has_growth_mutation(sl.get("mutations"))):
                    held += 1
        pets = {p.get("petSpecies"): self._food_plan(s).get(p["id"]) for p in s["pets"] if p}
        return {
            "coins": s["coins"],
            "granters_working": self._granters_working(s),
            "held_for_stamp": held,
            "ready_to_harvest": len(self._harvest_targets(s)),
            "egg_tiles": len(self._egg_tiles(s)),
            "journal_crops": len((s["data"].get("journal") or {}).get("produce") or {}),
            "journal_pets": len((s["data"].get("journal") or {}).get("pets") or {}),
            "journal_total_crops": len(eco.CROPS),
            "journal_total_pets": len(eco.PETS),
            "empty_tiles": len(self._empty_tiles(s)),
            "food_plan": pets,
            "inventory": f"{len(s['items'])}/{INVENTORY_CAPACITY}",
        }

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

        try:
            self.last_plan = self._summarize(s)
        except Exception:
            pass
        names = {"care_for_pets": "feeding pets", "improve_team_step": "improving team",
                 "shop_if_restocked": "shopping", "sell_if_needed": "selling",
                 "sell_pets_step": "selling pets", "hatch_step": "hatching eggs",
                 "harvest_valuable_step": "harvesting", "plant_step": "planting",
                 "upgrade_step": "upgrading tiles", "harvest_cheap_step": "harvesting cheap crops",
                 "journal_step": "logging journal"}
        for step in (self.care_for_pets, self.improve_team_step, self.journal_step,
                     self.shop_if_restocked, self.sell_if_needed, self.sell_pets_step, self.hatch_step,
                     self.harvest_valuable_step, self.plant_step, self.upgrade_step,
                     self.harvest_cheap_step):
            self.action = names.get(step.__name__, step.__name__)
            if await step(s):
                self.counters[self.action] += 1
                return True
        self.action = "idle"
        return False

    async def _refresh_game_data_if_needed(self):
        """New game build -> re-extract the tables from the client and reload."""
        build = str(getattr(self.client, "version", "") or "")
        if not build or build == self._data_build:
            return
        from automation import gamedata
        room = self.gs.get("room_id") or "MG1"
        self._data_build = build  # don't retry every tick if extraction fails
        await asyncio.to_thread(gamedata.ensure_current, room)
        self._log(f"game data reloaded for build {eco.reload()}")

    async def run(self):
        try:
            await asyncio.sleep(random.uniform(14, 22))  # page load + look around
            while True:
                did = False
                await self._refresh_game_data_if_needed()
                if self.paused:
                    self.action = "paused"
                    await asyncio.sleep(1.0)
                    continue
                try:
                    async with self.client.body_lock:
                        did = await self.tick()
                except RuntimeError:
                    break  # connection lost
                except Exception as e:  # keep playing; log and carry on
                    self._log(f"error: {e!r}")
                await asyncio.sleep(random.uniform(1.5, 4.0) if did else random.uniform(8, 20))
        except asyncio.CancelledError:
            pass
