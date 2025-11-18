"""
Configuration management for Magic Garden bot.

Handles loading, saving, and validation of bot configuration from bot_config.json.
"""

import json
import os
import secrets
from copy import deepcopy
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

from utils.constants import CONFIG_FILE


@dataclass
class ShopConfig:
    """Shop auto-buy configuration"""
    enabled: bool
    check_interval_seconds: int
    min_coins_to_keep: int
    seeds_enabled: bool
    seeds_to_buy: List[str]
    eggs_enabled: bool
    eggs_to_buy: List[str]


@dataclass
class HarvestConfig:
    """Harvest configuration"""
    enabled: bool
    species_to_harvest: list
    species_to_replant: list  # Species that should be replanted after harvest (e.g., Carrot, Tomato)
    min_mutations: int
    check_interval_seconds: int


@dataclass
class PetFoodConfig:
    """Pet food mapping configuration"""
    feeding_enabled: bool  # Whether to enable automatic pet feeding
    movement_enabled: bool  # Whether to enable automatic pet movement
    mapping: Dict[str, List[str]]  # {pet_species: [food_species_priority_list]}


@dataclass
class ReconnectionConfig:
    """Reconnection configuration"""
    max_retries: int
    base_delay: int
    max_delay: int


@dataclass
class BotConfig:
    """Complete bot configuration"""
    player_id: str
    cookies: str
    last_room: Optional[str]
    search_main_rooms: bool  # Whether to search MG1-MG15 or only use specified room
    harvest: HarvestConfig
    shop: ShopConfig
    pet_food: PetFoodConfig
    reconnection: ReconnectionConfig


def get_default_shop_config():
    """Return a fresh copy of the default shop configuration."""
    return {
        "enabled": False,
        "check_interval_seconds": 10,
        "min_coins_to_keep": 0,
        "items_to_buy": {
            "seeds": {"enabled": False, "items": []},
            "eggs": {"enabled": False, "items": []},
        },
    }


def normalize_shop_config(raw_config):
    """Ensure the shop config has all expected keys and sane defaults."""
    default_config = get_default_shop_config()

    if not isinstance(raw_config, dict):
        return default_config

    normalized = deepcopy(default_config)

    for key in ("enabled", "check_interval_seconds", "min_coins_to_keep"):
        if key in raw_config:
            normalized[key] = raw_config[key]

    raw_items = raw_config.get("items_to_buy")
    if isinstance(raw_items, dict):
        for bucket in normalized["items_to_buy"].keys():
            bucket_data = raw_items.get(bucket)
            if isinstance(bucket_data, dict):
                if "enabled" in bucket_data:
                    normalized["items_to_buy"][bucket]["enabled"] = bucket_data[
                        "enabled"
                    ]

                bucket_items = bucket_data.get("items")
                if isinstance(bucket_items, list):
                    normalized["items_to_buy"][bucket]["items"] = bucket_items

    return normalized


def generate_id(alphabet, length):
    """Generate a random ID from the given alphabet."""
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_player_id():
    """Generate a unique player ID."""
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    return "p_" + generate_id(alphabet, 16)


def load_config() -> BotConfig:
    """Load bot configuration from file.

    Returns:
        BotConfig object with all configuration loaded and validated.

    Raises:
        RuntimeError: If cookies are missing from config.
    """
    config = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
        except Exception:
            config = {}

    config_dirty = False

    # Player ID
    player_id = config.get("player_id")
    if not player_id:
        player_id = generate_player_id()
        config["player_id"] = player_id
        config_dirty = True

    # Harvest config
    ready_config = config.get("ready_to_harvest")
    if isinstance(ready_config, dict):
        harvest_config = ready_config
    else:
        harvest_config = {
            "enabled": False,
            "species": [],
            "min_mutations": 3,
            "check_interval_seconds": 30
        }
        config["ready_to_harvest"] = harvest_config
        config_dirty = True

    # Ensure all harvest config keys exist with defaults
    if "enabled" not in harvest_config:
        harvest_config["enabled"] = False
        config_dirty = True
    if "species" not in harvest_config:
        harvest_config["species"] = []
        config_dirty = True
    if "species_to_replant" not in harvest_config:
        harvest_config["species_to_replant"] = []
        config_dirty = True
    if "min_mutations" not in harvest_config:
        harvest_config["min_mutations"] = 3
        config_dirty = True
    if "check_interval_seconds" not in harvest_config:
        harvest_config["check_interval_seconds"] = 30
        config_dirty = True

    print(f"Loaded harvest config: Auto-harvest enabled = {harvest_config.get('enabled', False)}")
    if harvest_config.get('enabled'):
        print(f"  Species to harvest: {harvest_config.get('species', [])}")
        print(f"  Species to replant: {harvest_config.get('species_to_replant', [])}")
        print(f"  Min mutations: {harvest_config.get('min_mutations', 3)}")
        print(f"  Check interval: {harvest_config.get('check_interval_seconds', 30)}s")

    # Shop config
    normalized_shop = normalize_shop_config(config.get("shop"))
    if normalized_shop != config.get("shop"):
        config["shop"] = normalized_shop
        config_dirty = True

    print(f"Loaded shop config: Auto-buy enabled = {normalized_shop.get('enabled', False)}")

    # Pet food mapping
    pet_food_raw = config.get("pet_food_mapping")

    # Get enable/disable flags (default to False for new installations, True for backwards compatibility)
    pet_feeding_enabled = config.get("pet_feeding_enabled")
    pet_movement_enabled = config.get("pet_movement_enabled")

    # If pet_food_mapping exists AND has content but enable flags don't exist,
    # default to enabled for backwards compatibility.
    # Empty mappings should default to disabled.
    has_pet_mapping = isinstance(pet_food_raw, dict) and len(pet_food_raw) > 0

    if has_pet_mapping and pet_feeding_enabled is None:
        # Backwards compatibility: existing non-empty mapping enables feeding
        pet_feeding_enabled = True
        config["pet_feeding_enabled"] = True
        config_dirty = True
    elif pet_feeding_enabled is None:
        # New installation or empty mapping - default to False
        pet_feeding_enabled = False
        config["pet_feeding_enabled"] = False
        config_dirty = True

    if has_pet_mapping and pet_movement_enabled is None:
        # Backwards compatibility: existing non-empty mapping enables movement
        pet_movement_enabled = True
        config["pet_movement_enabled"] = True
        config_dirty = True
    elif pet_movement_enabled is None:
        # New installation or empty mapping - default to False
        pet_movement_enabled = False
        config["pet_movement_enabled"] = False
        config_dirty = True

    if isinstance(pet_food_raw, dict):
        # Normalize pet food config to use lists
        # Convert old format {"Bee": "OrangeTulip"} to new format {"Bee": ["OrangeTulip"]}
        pet_food_config = {}
        for pet_species, food_value in pet_food_raw.items():
            if isinstance(food_value, list):
                # Already in new format
                pet_food_config[pet_species] = food_value
            elif isinstance(food_value, str):
                # Convert old format (single string) to new format (list)
                pet_food_config[pet_species] = [food_value]
            else:
                # Invalid format, skip this entry
                continue

        # Update config if normalization changed anything
        if pet_food_config != pet_food_raw:
            config["pet_food_mapping"] = pet_food_config
            config_dirty = True
    else:
        # No pet_food_mapping provided - honor empty config, don't force defaults
        pet_food_config = {}
        if "pet_food_mapping" not in config:
            config["pet_food_mapping"] = {}
            config_dirty = True

    print(f"Loaded pet automation config: feeding_enabled={pet_feeding_enabled}, movement_enabled={pet_movement_enabled}")
    if pet_food_config:
        print(f"  Pet food mapping: {pet_food_config}")
    else:
        print(f"  Pet food mapping: (empty - no automatic feeding)")


    # Reconnection config
    reconnection_config = config.get("reconnection")
    if isinstance(reconnection_config, dict):
        # Validate and normalize values
        max_retries = reconnection_config.get("max_retries", 5)
        base_delay = reconnection_config.get("base_delay", 5)
        max_delay = reconnection_config.get("max_delay", 60)

        # Ensure values are within reasonable bounds
        max_retries = max(0, min(max_retries, 100))  # 0-100 retries
        base_delay = max(1, min(base_delay, 60))  # 1-60 seconds
        max_delay = max(base_delay, min(max_delay, 300))  # base_delay to 5 minutes

        reconnection_config_normalized = {
            "max_retries": max_retries,
            "base_delay": base_delay,
            "max_delay": max_delay
        }
    else:
        # Default reconnection config
        reconnection_config_normalized = {
            "max_retries": 5,
            "base_delay": 5,
            "max_delay": 60
        }
        config["reconnection"] = reconnection_config_normalized
        config_dirty = True

    print(f"Loaded reconnection config: max_retries={reconnection_config_normalized['max_retries']}, "
          f"base_delay={reconnection_config_normalized['base_delay']}s, "
          f"max_delay={reconnection_config_normalized['max_delay']}s")

    # Cookies
    cookies = config.get("cookies")
    missing_cookie_error = None
    if cookies:
        cookies = cookies.strip()
    else:
        cookies = ""
        if "cookies" not in config:
            config["cookies"] = ""
            config_dirty = True
        missing_cookie_error = (
            "No cookies found in bot_config.json. Please add your Magic Garden "
            'cookie string to the "cookies" entry.'
        )

    # Last room
    last_room = config.get("room_id")

    # Room search configuration
    search_main_rooms = config.get("search_main_rooms")
    if search_main_rooms is None:
        # Default to True for searching main rooms
        search_main_rooms = True
        config["search_main_rooms"] = True
        config_dirty = True

    print(f"Loaded room search config: search_main_rooms={search_main_rooms}")

    # Save if modified
    if config_dirty:
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=2)
        except Exception:
            pass

    if missing_cookie_error:
        raise RuntimeError(missing_cookie_error)

    # Build structured config objects
    shop_config_obj = ShopConfig(
        enabled=normalized_shop.get("enabled", False),
        check_interval_seconds=normalized_shop.get("check_interval_seconds", 10),
        min_coins_to_keep=normalized_shop.get("min_coins_to_keep", 0),
        seeds_enabled=normalized_shop["items_to_buy"]["seeds"]["enabled"],
        seeds_to_buy=normalized_shop["items_to_buy"]["seeds"]["items"],
        eggs_enabled=normalized_shop["items_to_buy"]["eggs"]["enabled"],
        eggs_to_buy=normalized_shop["items_to_buy"]["eggs"]["items"],
    )

    harvest_config_obj = HarvestConfig(
        enabled=harvest_config.get("enabled", False),
        species_to_harvest=harvest_config.get("species", []),
        species_to_replant=harvest_config.get("species_to_replant", []),
        min_mutations=harvest_config.get("min_mutations", 3),
        check_interval_seconds=harvest_config.get("check_interval_seconds", 30)
    )

    pet_food_config_obj = PetFoodConfig(
        feeding_enabled=pet_feeding_enabled,
        movement_enabled=pet_movement_enabled,
        mapping=pet_food_config
    )

    reconnection_config_obj = ReconnectionConfig(
        max_retries=reconnection_config_normalized["max_retries"],
        base_delay=reconnection_config_normalized["base_delay"],
        max_delay=reconnection_config_normalized["max_delay"]
    )

    return BotConfig(
        player_id=player_id,
        cookies=cookies,
        last_room=last_room,
        search_main_rooms=search_main_rooms,
        harvest=harvest_config_obj,
        shop=shop_config_obj,
        pet_food=pet_food_config_obj,
        reconnection=reconnection_config_obj,
    )


def save_last_room(room_id: str):
    """Save the last connected room to config."""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
        else:
            config = {}

        config["room_id"] = room_id

        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
    except Exception:
        pass


def save_cookies(cookies: str):
    """Persist the latest cookie string to the config."""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
        else:
            config = {}

        # Avoid rewriting the file if nothing changed
        if config.get("cookies") == cookies:
            return

        config["cookies"] = cookies

        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
    except Exception:
        pass
