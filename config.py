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
    min_mutations: int


@dataclass
class PetFoodConfig:
    """Pet food mapping configuration"""
    mapping: Dict[str, List[str]]  # {pet_species: [food_species_priority_list]}


@dataclass
class BotConfig:
    """Complete bot configuration"""
    player_id: str
    cookies: str
    last_room: Optional[str]
    harvest: HarvestConfig
    shop: ShopConfig
    pet_food: PetFoodConfig


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
    player_id = config.get("playerId")
    if not player_id:
        player_id = generate_player_id()
        config["playerId"] = player_id
        config_dirty = True

    # Harvest config
    ready_config = config.get("ready_to_harvest")
    if isinstance(ready_config, dict):
        harvest_config = ready_config
    else:
        harvest_config = {"min_mutations": 3}
        config["ready_to_harvest"] = harvest_config
        config_dirty = True

    # Shop config
    normalized_shop = normalize_shop_config(config.get("shop"))
    if normalized_shop != config.get("shop"):
        config["shop"] = normalized_shop
        config_dirty = True

    print(f"Loaded shop config: Auto-buy enabled = {normalized_shop.get('enabled', False)}")

    # Pet food mapping
    pet_food_mapping = config.get("pet_food_mapping")
    if isinstance(pet_food_mapping, dict):
        # Normalize pet food config to use lists
        # Convert old format {"Bee": "OrangeTulip"} to new format {"Bee": ["OrangeTulip"]}
        pet_food_config = {}
        for pet_species, food_value in pet_food_mapping.items():
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
        if pet_food_config != pet_food_mapping:
            config["pet_food_mapping"] = pet_food_config
            config_dirty = True
    else:
        # Default pet food mapping (using new list format)
        pet_food_config = {
            "Bee": ["OrangeTulip"],
            "Chicken": ["Aloe"],
            "Worm": ["Aloe"]
        }
        config["pet_food_mapping"] = pet_food_config
        config_dirty = True

    print(f"Loaded pet food mapping: {pet_food_config}")

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
    last_room = config.get("lastRoom")

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
        min_mutations=harvest_config.get("min_mutations", 3)
    )

    pet_food_config_obj = PetFoodConfig(
        mapping=pet_food_config
    )

    return BotConfig(
        player_id=player_id,
        cookies=cookies,
        last_room=last_room,
        harvest=harvest_config_obj,
        shop=shop_config_obj,
        pet_food=pet_food_config_obj,
    )


def save_last_room(room_id: str):
    """Save the last connected room to config."""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
        else:
            config = {}

        config["lastRoom"] = room_id

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
