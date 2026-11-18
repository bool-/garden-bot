"""
Game economics, straight from the web client's own tables (data/game_data.json).

Crop price (client function, build 2071):
    base * sizeMultiplier * growthMultiplier * (1 + sum(other multipliers) - count(other))
where size (50..100) maps linearly onto 1..maxSizeMultiplier, the Growth group
is Gold (x25) / Rainbow (x50), and the rest are weather/lunar mutations.

Pet hunger is measured in coins: feeding a crop adds its sell value, capped at
the pet's coinsToFullyReplenishHunger.
"""

import json
import os
from typing import Dict, List, Optional

_DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "game_data.json")

with open(_DATA_PATH, encoding="utf-8") as _f:
    GAME = json.load(_f)

CROPS: Dict[str, dict] = GAME["crops"]
PETS: Dict[str, dict] = GAME["pets"]
MUTATIONS: Dict[str, dict] = GAME["mutations"]
STALLS: Dict[str, dict] = GAME["stalls"]

GROWTH_MUTATIONS = {name for name, m in MUTATIONS.items() if m["group"] == "Growth"}
GRANTER_ABILITIES = {"GoldGranter", "RainbowGranter"}


def size_multiplier(species: str, size) -> float:
    crop = CROPS.get(species)
    if not crop:
        return 1.0
    try:
        s = min(100, max(50, round(float(size))))
    except (TypeError, ValueError):
        s = 50
    return 1 + (crop["maxSizeMultiplier"] - 1) * (s - 50) / 50


def mutation_multiplier(mutations: List[str]) -> float:
    growth = next((m for m in mutations if m in GROWTH_MUTATIONS), None)
    others = [m for m in mutations if m in MUTATIONS and m not in GROWTH_MUTATIONS]
    g = MUTATIONS[growth]["coinMultiplier"] if growth else 1
    return g * (1 + sum(MUTATIONS[m]["coinMultiplier"] for m in others) - len(others))


def crop_value(species: str, size=50, mutations: Optional[List[str]] = None) -> int:
    crop = CROPS.get(species)
    if not crop:
        return 0
    return round(crop["baseSellPrice"] * size_multiplier(species, size) * mutation_multiplier(mutations or []))


def base_price(species: str) -> int:
    return (CROPS.get(species) or {}).get("baseSellPrice", 0)


def has_growth_mutation(mutations: List[str]) -> bool:
    return any(m in GROWTH_MUTATIONS for m in mutations or [])


def is_multi_harvest(species: str) -> bool:
    return (CROPS.get(species) or {}).get("harvestType") == "Multiple"


def planting_score(species: str) -> float:
    """Rough long-run value of a tile planted with this seed. Multi-harvest
    plants keep producing (and keep catching Gold/Rainbow stamps)."""
    base = base_price(species)
    return base * (3 if is_multi_harvest(species) else 1)


def best_food_species(pet_species: str, available: List[str]) -> Optional[str]:
    """Diet crop to farm for this pet: the most valuable one that still fits in
    a full hunger bar (fewest feeds, no waste); else the cheapest."""
    pet = PETS.get(pet_species)
    if not pet:
        return None
    options = [s for s in pet["diet"] if s in available and s in CROPS]
    if not options:
        return None
    cap = pet["hungerCap"]
    fitting = [s for s in options if base_price(s) <= cap]
    if fitting:
        return max(fitting, key=base_price)
    return min(options, key=base_price)
