"""
Read-only view of the game and the brain for the UI.

One Snapshot is built per UI tick from a single deep copy of the full state,
so every page renders the same moment. The brain and client live on the bot
thread: only plain attributes are read here, nothing blocks.
"""

import re
import time
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from automation import economy as eco
from utils.constants import INVENTORY_CAPACITY

from .theme import Carbon as C, duration, short_number, spaced

DEFAULT_HOLD_MIN_BASE = 100_000
BRAIN_DEFAULTS = {
    "min_coins_to_keep": 0, "buy_shops": ["seed", "egg"], "hold_for_gold_min_base_price": 100_000,
    "food_tiles_per_pet": 2, "sell_when_produce_count": 20, "egg_tiles": 8, "big_egg_share": 0.25,
    "cheap_crop_value": 10_000, "sell_original_pets": False, "spare_granters_to_keep": 2,
    "upgrade_when_better_by": 10, "journal": True, "journal_tiles": 6,
}


class ServerClock:
    """Server time between state patches: currentTime plus local time elapsed
    since it last changed."""

    def __init__(self):
        self._offset = None
        self._last = None

    def now_ms(self, full_state) -> int:
        local = int(time.time() * 1000)
        try:
            server = int(full_state["child"]["data"]["currentTime"])
        except Exception:
            return local if self._offset is None else local + self._offset
        if server != self._last:
            self._last = server
            self._offset = server - local
        return local + self._offset


class Snapshot:
    def __init__(self, game_state, holder: Dict[str, Any], clock: ServerClock):
        self.gs = game_state
        self.holder = holder or {}
        self.client = self.holder.get("client")
        self.brain = self.holder.get("brain")
        self.full = game_state.get_full_state()
        self.now_ms = clock.now_ms(self.full)
        self.player_id = game_state.get_player_id()
        self.player_name = game_state.get_player_name() or self.player_id or ""
        self.room_id = game_state.get_room_id() or ""
        self.slot_index = game_state.get_user_slot_index()
        child = (self.full or {}).get("child") or {}
        self.quinoa = (child.get("data") or {}) if child.get("scope") == "Quinoa" else {}
        self.user_slots = self.quinoa.get("userSlots") or []
        self.slot = None
        for i, s in enumerate(self.user_slots):
            if s and (s.get("userId") or s.get("playerId")) == self.player_id:
                self.slot = s
                if self.slot_index is None:
                    self.slot_index = i
                break
        self.data = (self.slot or {}).get("data") or {}
        inv = self.data.get("inventory") or {}
        self.inventory = inv
        self.items: List[dict] = inv.get("items") or []
        self.locked = set(inv.get("favoritedItemIds") or [])
        self.garden: Dict[str, dict] = (self.data.get("garden") or {}).get("tileObjects") or {}
        self.pets: List[dict] = [p for p in (self.data.get("petSlots") or []) if p]
        self.coins = self.data.get("coinsCount")
        self.plan: Dict[str, Any] = dict(getattr(self.brain, "last_plan", None) or {}) if self.brain else {}
        self.cfg = dict(BRAIN_DEFAULTS)
        if self.brain is not None:
            try:
                self.cfg.update(self.brain.settings())
            except Exception:
                self.cfg.update(getattr(self.brain, "cfg", None) or {})

    @property
    def ready(self) -> bool:
        return self.slot is not None

    @property
    def hold_min(self) -> int:
        try:
            return int(self.cfg.get("hold_for_gold_min_base_price", DEFAULT_HOLD_MIN_BASE))
        except (TypeError, ValueError):
            return DEFAULT_HOLD_MIN_BASE

    @property
    def food_crops(self) -> set:
        return {c for c in (self.plan.get("food_plan") or {}).values() if c}

    @property
    def bag(self) -> Tuple[int, int]:
        return len(self.items), INVENTORY_CAPACITY

    @property
    def paused(self) -> bool:
        return bool(getattr(self.brain, "paused", False)) if self.brain is not None else False


# ------------------------------------------------------------------ tiles

def classify_slot(sl: dict, now_ms: int, hold_min: int) -> str:
    if now_ms < (sl.get("endTime") or 0):
        return "growing"
    if eco.has_growth_mutation(sl.get("mutations")):
        return "stamped"
    if eco.base_price(sl.get("species")) >= hold_min:
        return "held"
    return "ripe"


RANK = {"growing": 0, "ripe": 1, "held": 2, "stamped": 3}


def classify_tile(obj: Optional[dict], now_ms: int, hold_min: int, food: set) -> str:
    """-> stamped | held | ripe | growing | food | egg | empty"""
    if not obj:
        return "empty"
    kind = obj.get("objectType")
    if kind == "egg":
        return "egg"
    if kind != "plant":
        return "empty"
    best = None
    for sl in obj.get("slots") or []:
        if not sl:
            continue
        st = classify_slot(sl, now_ms, hold_min)
        if best is None or RANK[st] > RANK[best]:
            best = st
    if best is None:
        return "empty"
    species = obj.get("species") or next((s.get("species") for s in obj.get("slots") or [] if s), None)
    if best in ("ripe", "growing") and species in food:
        return "food"
    return best


def garden_counts(garden: Dict[str, dict], now_ms: int, hold_min: int, food: set) -> Counter:
    counts = Counter()
    for tid in range(200):
        counts[classify_tile(garden.get(str(tid)), now_ms, hold_min, food)] += 1
    return counts


def egg_ready_at(obj: dict) -> Optional[int]:
    ready = obj.get("maturedAt")
    if ready is None and obj.get("plantedAt") is not None:
        ready = obj["plantedAt"] + eco.egg_hatch_seconds(obj.get("eggId")) * 1000
    return ready


def tile_tooltip(tile_id: int, obj: Optional[dict], now_ms: int, hold_min: int, food: set) -> str:
    if not obj:
        return f"Tile {tile_id}: empty"
    kind = obj.get("objectType")
    if kind == "egg":
        ready = egg_ready_at(obj)
        name = spaced(obj.get("eggId") or "Egg")
        if ready is None:
            return f"Tile {tile_id}: {name}"
        left = (ready - now_ms) / 1000
        return f"Tile {tile_id}: {name}, " + ("ready to hatch" if left <= 0 else f"hatches in {duration(left)}")
    if kind != "plant":
        return f"Tile {tile_id}: {spaced(kind)}"
    slots = [s for s in obj.get("slots") or [] if s]
    if not slots:
        return f"Tile {tile_id}: empty"
    species = obj.get("species") or slots[0].get("species") or "?"
    state = classify_tile(obj, now_ms, hold_min, food)
    best = max(slots, key=lambda s: (RANK[classify_slot(s, now_ms, hold_min)],
                                     eco.crop_value(s.get("species"), s.get("size", 50), s.get("mutations"))))
    muts = best.get("mutations") or []
    total = sum(eco.crop_value(s.get("species") or species, s.get("size", 50), s.get("mutations")) for s in slots)
    ripe = sum(1 for s in slots if now_ms >= (s.get("endTime") or 0))
    soonest = min((s.get("endTime") or 0 for s in slots if now_ms < (s.get("endTime") or 0)), default=None)
    status = {
        "stamped": "harvest next",
        "held": "held for stamp",
        "ripe": "ripe",
        "growing": f"ripe in {duration((soonest - now_ms) / 1000)}" if soonest else "growing",
        "food": "pet food, ripe" if ripe else (f"pet food, ripe in {duration((soonest - now_ms) / 1000)}" if soonest else "pet food"),
    }.get(state, state)
    parts = [f"Tile {tile_id}: {spaced(species)}", " + ".join(muts) if muts else "no mutations", short_number(total), status]
    if len(slots) > 1:
        parts.append(f"{ripe} of {len(slots)} ripe")
    return ", ".join(parts)


def held_and_stamped(snap: Snapshot):
    """(held count, held value if all stamped Gold, stamped count, stamped value, stamp names)"""
    held = held_gold = stamped = stamped_value = 0
    names = set()
    for obj in snap.garden.values():
        if (obj or {}).get("objectType") != "plant":
            continue
        for sl in obj.get("slots") or []:
            if not sl:
                continue
            st = classify_slot(sl, snap.now_ms, snap.hold_min)
            muts = sl.get("mutations") or []
            if st == "held":
                held += 1
                held_gold += eco.crop_value(sl.get("species"), sl.get("size", 50), list(muts) + ["Gold"])
            elif st == "stamped":
                stamped += 1
                stamped_value += eco.crop_value(sl.get("species"), sl.get("size", 50), muts)
                names.update(m for m in muts if m in eco.GROWTH_MUTATIONS)
    return held, held_gold, stamped, stamped_value, names


# ------------------------------------------------------------------ pets

def stamp_of(pet: dict) -> Tuple[str, str]:
    g = eco.pet_growth_multiplier(pet)
    if g >= 50:
        return "Rainbow ×50", C.RAINBOW
    if g >= 25:
        return "Gold ×25", C.MONEY
    return "None", C.TEXT_HELPER


def pet_name(pet: dict) -> str:
    return spaced(pet.get("name") or pet.get("petSpecies") or "Pet")


def hunger_of(pet: dict) -> Tuple[float, int, float]:
    cap = int((eco.PETS.get(pet.get("petSpecies")) or {}).get("hungerCap") or 0)
    hunger = float(pet.get("hunger") or 0)
    return hunger, cap, (hunger / cap if cap else 0.0)


def hunger_color(frac: float, hunger: float) -> str:
    if hunger <= 0:
        return C.ERROR
    if frac < 0.2:
        return C.WARNING
    return C.SUCCESS


def ability_name(a: str) -> str:
    info = (eco.GAME.get("abilities") or {}).get(a) or {}
    return info.get("name") or spaced(a)


def food_for(snap: Snapshot, pet: dict) -> Optional[str]:
    plan = snap.plan.get("food_plan") or {}
    return plan.get(pet.get("petSpecies"))


def next_meal(snap: Snapshot, pet: dict) -> Tuple[str, str]:
    """(detail, when) for a hungry pet: where its next meal comes from."""
    food = food_for(snap, pet)
    diet = set((eco.PETS.get(pet.get("petSpecies")) or {}).get("diet") or [])
    cap = (eco.PETS.get(pet.get("petSpecies")) or {}).get("hungerCap") or 0
    limit = max(cap * 2, 1)  # the brain never feeds a crop worth more than two full bars

    def worth(sp, size, muts):
        return eco.crop_value(sp, size if size is not None else 50, muts)

    in_bag = [i for i in snap.items if i.get("itemType") == "Produce" and i.get("species") in diet
              and worth(i.get("species"), i.get("size"), i.get("mutations")) <= limit]
    if in_bag:
        return f"{spaced(in_bag[0].get('species'))} in the bag, it eats next", "next"
    best = None  # (seconds left, tile, species)
    for tid, obj in snap.garden.items():
        if (obj or {}).get("objectType") != "plant":
            continue
        for sl in obj.get("slots") or []:
            if not sl or sl.get("species") not in diet or eco.has_growth_mutation(sl.get("mutations")):
                continue
            if worth(sl.get("species"), sl.get("size"), sl.get("mutations")) > limit:
                continue
            left = max(0, ((sl.get("endTime") or 0) - snap.now_ms) / 1000)
            if best is None or left < best[0]:
                best = (left, tid, sl.get("species"))
    if best:
        left, tid, species = best
        if left <= 0:
            return f"{spaced(species)} on tile {tid} is ripe, it eats next", "next"
        return f"{spaced(species)} on tile {tid} ripens in {duration(left)}, then it eats", f"in {duration(left)}"
    if food:
        return f"No {spaced(food)} growing yet; it is planted on the next free tile", ""
    return "Nothing from its diet in seeds or the garden", ""


def bench_pets(snap: Snapshot) -> List[dict]:
    return [i for i in snap.items if i.get("itemType") == "Pet"]


def bench_plan(snap: Snapshot) -> Dict[str, str]:
    """pet id -> what the brain will do with it (mirrors PetsMixin._pets_to_sell)."""
    bag = bench_pets(snap)
    if snap.brain is None:
        return {p.get("id"): "Brain disabled" for p in bag}
    floor = min((eco.pet_score(p) for p in snap.pets), default=0)
    spares_n = int(snap.cfg.get("spare_granters_to_keep", 2) or 0)
    spares = sorted((p for p in bag if eco.is_granter(p) and p.get("id") not in snap.locked),
                    key=eco.pet_score, reverse=True)
    keep = {p.get("id") for p in spares[:spares_n]}
    originals = getattr(snap.brain, "_original_pets", None) or set()
    sell_orig = bool(snap.cfg.get("sell_original_pets", False))
    best = max(bag, key=eco.pet_score) if bag else None
    out = {}
    for p in bag:
        pid = p.get("id")
        if pid in snap.locked:
            out[pid] = "Locked in game"
        elif best is p and snap.pets and eco.pet_score(p) > floor * 1.05:
            out[pid] = "Swaps in next"
        elif pid in keep:
            out[pid] = "Spare granter"
        elif not sell_orig and pid in originals:
            out[pid] = "Kept, original pet"
        elif eco.pet_score(p) > floor:
            out[pid] = "Kept, better than the team"
        else:
            out[pid] = "Sell on next trip"
    return out


# ------------------------------------------------------------------ eggs

def egg_groups(snap: Snapshot) -> List[dict]:
    """Eggs growing on tiles, by type: tiles, progress of the soonest, seconds left."""
    groups: Dict[str, dict] = {}
    for obj in snap.garden.values():
        if (obj or {}).get("objectType") != "egg":
            continue
        egg = obj.get("eggId") or "Egg"
        ready = egg_ready_at(obj)
        total = eco.egg_hatch_seconds(egg)
        left = max(0.0, (ready - snap.now_ms) / 1000) if ready is not None else None
        g = groups.setdefault(egg, {"egg": egg, "tiles": 0, "left": None, "frac": 0.0, "ready": 0})
        g["tiles"] += 1
        if left is not None and left <= 0:
            g["ready"] += 1
        if left is not None and (g["left"] is None or left < g["left"]):
            g["left"] = left
            g["frac"] = 1 - left / total if total and total < 10 ** 8 else 0.0
    return sorted(groups.values(), key=lambda g: (g["left"] if g["left"] is not None else 1e18))


def hatches_per_day(snap: Snapshot) -> float:
    total = 0.0
    for obj in snap.garden.values():
        if (obj or {}).get("objectType") == "egg":
            s = eco.egg_hatch_seconds(obj.get("eggId"))
            if 0 < s < 10 ** 8:
                total += 86400 / s
    return total


# ------------------------------------------------------------------ journal / camera

def has_camera(snap: Snapshot) -> bool:
    return any(i.get("toolId") == "Camera" for i in snap.items) or any(
        t.get("id") == "Camera" for t in snap.inventory.get("toolRing") or [])


def journal_counts(snap: Snapshot) -> Tuple[int, int, int, int]:
    j = snap.data.get("journal") or {}
    p = snap.plan
    crops = p.get("journal_crops", len(j.get("produce") or {}))
    pets = p.get("journal_pets", len(j.get("pets") or {}))
    return (int(crops or 0), int(p.get("journal_total_crops") or len(eco.CROPS)),
            int(pets or 0), int(p.get("journal_total_pets") or len(eco.PETS)))


# ------------------------------------------------------------------ activity

_PLURAL = re.compile(r"(\d+)((?: [\w-]+)*?) (\w+?)\(s\)")
_COINS = re.compile(r",?\s*~?([\d,]{4,}) coins")


def format_event(text: str) -> Tuple[str, str, str]:
    """Brain log line -> (display text, value, kind). kind: m money, g fed, p pets, '' other."""
    raw = str(text or "")
    t = _PLURAL.sub(lambda m: f"{m.group(1)}{m.group(2)} {m.group(3)}{'' if m.group(1) == '1' else 's'}", raw)
    t = re.sub(r"(\w)\(s\)", r"\1s", t)
    low = raw.lower()
    val, kind = "", ""
    m = re.match(r"fed (\S+) \((\d+)/(\d+)\) with (fresh )?(.+?) worth ([\d,]+)", raw)
    if m:
        return f"Fed {spaced(m.group(1))}: {spaced(m.group(5))}", "+" + m.group(6), "g"
    m = _COINS.search(t)
    if m:
        try:
            val = short_number(int(m.group(1).replace(",", "")), signed=True)
        except ValueError:
            val = ""
        t = _COINS.sub("", t).strip()
    if "sold" in low or m:
        kind = "m"
    elif any(w in low for w in ("hatched", "team", "pet", "fed ")):
        kind = "p"
    m2 = re.match(r"(hatched|harvested|planted|restock: bought) (\d+)", t)
    if m2 and not val:
        val = m2.group(2)
    t = t.replace("restock: bought", "Restock: bought")
    return (t[:1].upper() + t[1:]) if t else t, val, kind


def event_matches(kind: str, flt: str) -> bool:
    if flt == "Money":
        return kind == "m"
    if flt == "Pets":
        return kind in ("p", "g")
    return True
