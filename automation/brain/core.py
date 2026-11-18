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
        self.cfg = dict(cfg)
        self._apply_cfg(self.cfg)
        # Read by the UI (another thread): plain attributes, replaced not mutated.
        self.paused = False
        self.action = "starting"
        self.events = collections.deque(maxlen=200)  # (epoch seconds, text)
        self.counters = collections.Counter()
        self.last_plan: Dict[str, Any] = {}
        self.requests = collections.deque()  # one-off actions queued by the UI ("sell", "shop")
        self._pending_harvest = set()  # (tile, slotIndex) sent, not yet removed by server
        self._bought_restocks = set()  # (shop, restockId) we already shopped
        self._original_pets = None  # ids of pets the account had when the bot started
        self._journal_pending = set()  # (species, variant) logged, not yet in server state
        self._camera_asked_at = 0.0
        self._rejections_seen = 0.0  # time of the newest rejection already logged
        self._journal_done = False
        self._camera_accepted = False
        self._data_build = str(eco.GAME.get("build"))
        self._unbuyable = self._load_unbuyable()  # (shop, item key) the server rejected

    # ------------------------------------------------------------- settings
    # Every setting the UI can edit: config key -> (attribute, type).
    SETTINGS = {
        "min_coins_to_keep": ("min_coins", int),
        "buy_shops": ("shops", list),
        "hold_for_gold_min_base_price": ("hold_min_base", int),
        "food_tiles_per_pet": ("food_tiles_per_pet", int),
        "sell_when_produce_count": ("sell_at_produce", int),
        "sell_when_value_over": ("sell_at_value", int),
        "harvest_batch": ("harvest_batch", int),
        "never_plant": ("never_plant", set),
        "never_harvest": ("never_harvest", set),
        "tools_to_buy": ("tools_to_buy", set),
        "egg_tiles": ("egg_tiles", int),
        "big_egg_share": ("big_egg_share", float),
        "cheap_crop_value": ("cheap_crop_value", int),
        "never_hatch": ("never_hatch", set),
        "sell_original_pets": ("sell_original_pets", bool),
        "spare_granters_to_keep": ("spare_granters", int),
        "sell_pets_when_count": ("sell_pets_at", int),
        "upgrade_when_better_by": ("upgrade_factor", float),
        "upgrades_per_tick": ("upgrade_per_tick", int),
        "journal": ("journal_enabled", bool),
        "journal_tiles": ("journal_tiles", int),
        "focus": ("focus", str),
    }
    DEFAULTS = {
        "min_coins_to_keep": 0, "buy_shops": ["seed", "egg"], "hold_for_gold_min_base_price": 100_000,
        "food_tiles_per_pet": 2, "sell_when_produce_count": 20, "sell_when_value_over": 5_000_000,
        "harvest_batch": 12, "never_plant": [], "never_harvest": [], "tools_to_buy": [], "egg_tiles": 8,
        "big_egg_share": 0.25, "cheap_crop_value": 10_000, "never_hatch": [], "sell_original_pets": False,
        "spare_granters_to_keep": 2, "sell_pets_when_count": 4, "upgrade_when_better_by": 10,
        "upgrades_per_tick": 3, "journal": True, "journal_tiles": 6, "focus": "journal_then_profit",
    }

    def _apply_cfg(self, cfg: Dict[str, Any]):
        for key, (attr, kind) in self.SETTINGS.items():
            value = cfg.get(key, self.DEFAULTS[key])
            setattr(self, attr, kind(value))

    def settings(self) -> Dict[str, Any]:
        """Current value of every editable setting (for the UI)."""
        return {key: self.cfg.get(key, self.DEFAULTS[key]) for key in self.SETTINGS}

    def apply_settings(self, updates: Dict[str, Any], save: bool = True):
        """Change settings live (UI thread safe: plain attribute swaps) and
        persist them to the brain section of bot_config.json."""
        updates = {k: v for k, v in updates.items() if k in self.SETTINGS}
        if not updates:
            return
        cfg = dict(self.cfg)
        cfg.update(updates)
        self.cfg = cfg
        self._apply_cfg(cfg)
        self._log("settings: " + ", ".join(f"{k}={v}" for k, v in updates.items()))
        if save:
            from config import save_brain_settings
            save_brain_settings(updates)

    @staticmethod
    def _describe_command(cmd: Dict[str, Any]) -> str:
        kind = cmd.get("type", "command")
        if kind == "PurchaseShopItem":
            item = cmd.get("item") or {}
            name = item.get("species") or item.get("eggId") or item.get("toolId") or item.get("decorId") or "item"
            noun = {"Seed": " seed", "Egg": "", "Tool": "", "Decor": ""}.get(item.get("itemType"), "")
            return f"buy {name}{noun}"
        if kind == "HarvestCrop":
            return f"harvest tile {cmd.get('slot')}"
        if kind == "PlantSeed":
            return f"plant {cmd.get('species')} on tile {cmd.get('slot')}"
        if kind == "FeedPet":
            return "feed a pet"
        if kind == "LogItem":
            return "log a Journal entry"
        return kind

    def _log_rejections(self):
        """Every server rejection becomes a readable Activity line (what + why)."""
        for r in list(getattr(self.client, "rejection_log", []) or []):
            if r["t"] <= self._rejections_seen:
                continue
            self._rejections_seen = r["t"]
            self._log(f"rejected by server: {self._describe_command(r['command'])} ({r['code']})")

    def request(self, action: str):
        """Queue a one-off action from the UI: "sell" or "shop"."""
        if action in ("sell", "shop"):
            self.requests.append(action)

    def request_unlock(self, item_ids):
        """Queue unlocking items (the in-game lock that keeps them from being
        sold or fed). Only items that are currently locked get toggled."""
        ids = [str(i) for i in item_ids or [] if i]
        if ids:
            self.requests.append(("unlock", ids))

    async def _handle_requests(self, s) -> bool:
        if not self.requests:
            return False
        action = self.requests.popleft()
        if isinstance(action, tuple) and action[0] == "unlock":
            self.action = "unlocking items (requested)"
            done = 0
            for item_id in action[1]:
                if item_id in s["locked"]:  # ToggleLockItem flips: never lock by mistake
                    await self.client.send_command({"type": "ToggleLockItem", "itemId": item_id})
                    s["locked"].discard(item_id)
                    done += 1
                    await asyncio.sleep(random.uniform(0.4, 0.9))
            self._log(f"unlocked {done} item(s)" if done else "unlock: those items weren't locked")
            return True
        if action == "sell":
            self.action = "selling (requested)"
            if not await self.sell_if_needed(s, force=True):
                self._log("sell now: nothing to sell")
            return True
        if action == "shop":
            self.action = "shopping (requested)"
            self._bought_restocks.clear()
            if not await self.shop_if_restocked(s):
                self._log("shop now: nothing left to buy this restock")
            return True
        return False

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

    def _has_granters(self, s) -> bool:
        """A Gold/Rainbow pet is on the team (fed or not: the bot feeds it).
        This, not current hunger, decides whether valuable crops are held
        for a stamp; a hungry moment must not trigger a sell-everything."""
        return any(eco.GRANTER_ABILITIES & set(p.get("abilities") or []) for p in s["pets"] if p)

    FOCUSES = ("journal_then_profit", "profit", "journal", "pets")

    @property
    def journal_first_active(self) -> bool:
        if not self.journal_enabled:
            return False
        if self.focus == "journal":
            return True
        return self.focus == "journal_then_profit" and not self._journal_done

    @property
    def effective_egg_tiles(self) -> int:
        """Pets focus: many more hatch rolls for Gold/Rainbow pets."""
        return max(self.egg_tiles, 30) if self.focus == "pets" else self.egg_tiles

    def _update_journal_goal(self, s):
        """Journal-first ends by itself once nothing loggable is left."""
        if self.focus != "journal_then_profit" or not self.journal_enabled or not self._has_camera(s):
            return
        unlogged_eggs = False
        logged_pets = set((s["data"].get("journal") or {}).get("pets") or {})
        for egg in self._usable_eggs(s):
            if any(p not in logged_pets for p in (eco.EGGS.get(egg) or {}).get("weights") or {}):
                unlogged_eggs = True
                break
        growing_unlogged = any((o or {}).get("species") in self._journal_wanted_species(s)
                               for o in s["garden"].values())
        done = not self._journal_wanted_species(s) and not unlogged_eggs and not growing_unlogged \
            and not self._journal_targets(s)
        if done and not self._journal_done:
            self._log("journal: nothing left the bot can log, switching to profit")
        self._journal_done = done

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
            "goal": "journal" if self.journal_first_active else ("pets" if self.focus == "pets" else "profit"),
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

        self._log_rejections()
        try:
            self._update_journal_goal(s)
        except Exception as e:
            print(f"[brain] journal goal check failed: {e!r}")
        try:
            self.last_plan = self._summarize(s)
        except Exception:
            pass
        names = {"care_for_pets": "feeding pets", "improve_team_step": "improving team",
                 "shop_if_restocked": "shopping", "sell_if_needed": "selling",
                 "sell_pets_step": "selling pets", "hatch_step": "hatching eggs",
                 "harvest_valuable_step": "harvesting", "plant_step": "planting",
                 "upgrade_step": "upgrading tiles", "harvest_cheap_step": "harvesting cheap crops",
                 "journal_step": "logging journal", "camera_step": "getting the Camera"}
        if await self._handle_requests(s):
            return True
        for step in (self.care_for_pets, self.improve_team_step, self.camera_step, self.journal_step,
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
