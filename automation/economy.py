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

GAME: Dict[str, dict] = {}
CROPS: Dict[str, dict] = {}
PETS: Dict[str, dict] = {}
MUTATIONS: Dict[str, dict] = {}
STALLS: Dict[str, dict] = {}
EGGS: Dict[str, dict] = {}
GROWTH_MUTATIONS: set = set()


def reload() -> str:
    """(Re)load data/game_data.json in place, so every module holding these
    dicts sees the new build's numbers. Returns the build id."""
    with open(_DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    GAME.clear(); GAME.update(data)
    for target, key in ((CROPS, "crops"), (PETS, "pets"), (MUTATIONS, "mutations"),
                        (STALLS, "stalls"), (EGGS, "eggs")):
        target.clear()
        target.update(data.get(key) or {})
    GROWTH_MUTATIONS.clear()
    GROWTH_MUTATIONS.update(n for n, m in MUTATIONS.items() if m.get("group") == "Growth")
    return str(data.get("build"))


reload()
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


# ----------------------------------------------------------------- pets/eggs


def pet_max_strength(species: str, scale) -> int:
    """Client formula: 80 at scale <= 1, 100 at the species' maxScale."""
    max_scale = (PETS.get(species) or {}).get("maxScale", 2)
    try:
        s = float(scale)
    except (TypeError, ValueError):
        return 80
    if s <= 1:
        return 80
    if s >= max_scale:
        return 100
    return int(80 + 20 * (s - 1) / (max_scale - 1))


def pet_growth_multiplier(pet: dict) -> int:
    """Gold/Rainbow pets carry GoldGranter/RainbowGranter: their stamp is the
    crop multiplier they hand out."""
    abilities = set(pet.get("abilities") or [])
    muts = set(pet.get("mutations") or [])
    if "RainbowGranter" in abilities or "Rainbow" in muts:
        return 50
    if "GoldGranter" in abilities or "Gold" in muts:
        return 25
    return 1


# Rough worth of non-granter abilities for a money garden (relative units; a
# Gold stamp is 25). Weather granters/boosts stack under Gold/Rainbow, sell
# boosts and coin finders pay directly, pet-mutation/size boosts make better
# hatches. Taken from the client's ability table (build 2071).
ABILITY_VALUE = {
    "SellBoostIV": 6, "SellBoostIII": 5, "SellBoostII": 4, "SellBoostI": 3,
    "CoinFinderIV": 5, "CoinFinderIII": 4, "CoinFinderII": 2, "CoinFinderI": 1,
    "DoubleHarvest": 4, "ProduceRefund": 2,
    "FrostGranter": 5, "AmberlitGranter": 5, "ThunderstruckGranter": 4, "DawnlitGranter": 3,
    "SnowGranter": 1.5, "RainDance": 1.5,
    "ProduceMutationBoostII": 3, "ProduceMutationBoost": 2, "ProduceScaleBoostII": 3, "ProduceScaleBoost": 2,
    "PetMutationBoostIII": 4, "PetMutationBoostII": 3, "PetMutationBoost": 2,
    "PetHatchSizeBoostII": 2, "PetHatchSizeBoost": 1.5, "DoubleHatchII": 2, "DoubleHatch": 1.5,
    "EggGrowthBoostII": 1.5, "EggGrowthBoostII_NEW": 1.2, "EggGrowthBoost": 1,
}


def pet_score(pet: dict) -> float:
    """How much a pet is worth having active. Gold/Rainbow stamping (x25/x50
    on every stamped crop) dominates; the pet's other money abilities add on
    top; size (max strength = how often abilities hit) scales it all."""
    growth = pet_growth_multiplier(pet)
    strength = pet_max_strength(pet.get("petSpecies"), pet.get("targetScale"))
    extras = sum(ABILITY_VALUE.get(a, 0) for a in pet.get("abilities") or [])
    return (growth + extras) * strength


def is_granter(pet: dict) -> bool:
    return pet_growth_multiplier(pet) > 1


def egg_hatch_seconds(egg_id: str) -> int:
    return int((EGGS.get(egg_id) or {}).get("hatchS", 10 ** 9))
