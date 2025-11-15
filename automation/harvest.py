"""
Harvest automation for Magic Garden bot.

Handles finding, harvesting, and replanting crops automatically.
"""

import asyncio
import time
from typing import Optional, Tuple, Dict, Any

from game_state import GameState
from config import HarvestConfig


async def find_harvestable_plant(
    slot_data: Dict[str, Any], species: str, min_mutations: int = 3
) -> Tuple[Optional[int], Optional[int]]:
    """
    Find a ready-to-harvest plant of the specified species.

    Args:
        slot_data: Player's slot data containing garden
        species: Plant species to find
        min_mutations: Minimum mutation count required (default: 3)

    Returns:
        Tuple of (tile_id, slot_index) if found, else (None, None)
    """
    current_time = int(time.time() * 1000)

    garden_data = slot_data.get("garden", {})
    tile_objects = garden_data.get("tileObjects", {})

    for tile_id, tile_obj in tile_objects.items():
        if not tile_obj or tile_obj.get("objectType") != "plant":
            continue

        slots = tile_obj.get("slots", [])
        for slot_index, plant_slot in enumerate(slots):
            if not plant_slot:
                continue

            plant_species = plant_slot.get("species")
            end_time = plant_slot.get("endTime", 0)
            mutations = plant_slot.get("mutations", [])

            # Check if this plant matches species and is ready to harvest
            if (
                plant_species == species
                and current_time >= end_time
                and len(mutations) >= min_mutations
            ):
                return int(tile_id), slot_index

    return None, None


async def harvest_and_replant(
    client, slot_data: Dict[str, Any], species: str, min_mutations: int = 3
) -> bool:
    """
    Harvest a plant of the specified species and replant it.

    Args:
        client: MagicGardenClient instance
        slot_data: Player's slot data containing garden
        species: Plant species to harvest
        min_mutations: Minimum mutation count required

    Returns:
        True if successful, False otherwise
    """
    tile_slot, slots_index = await find_harvestable_plant(
        slot_data, species, min_mutations
    )

    if tile_slot is None:
        return False

    print(f"Found harvestable {species} at slot {tile_slot}")

    # Harvest the crop
    harvest_message = {
        "scopePath": ["Room", "Quinoa"],
        "type": "HarvestCrop",
        "slot": tile_slot,
        "slotsIndex": slots_index,
    }
    await client.send(harvest_message)
    print(f"Harvested {species} from slot {tile_slot}")

    # Wait a moment for the harvest to process
    await asyncio.sleep(0.3)

    # Replant the same species
    plant_message = {
        "scopePath": ["Room", "Quinoa"],
        "type": "PlantSeed",
        "slot": tile_slot,
        "species": species,
    }
    await client.send(plant_message)
    print(f"Replanted {species} in slot {tile_slot}")

    return True


async def find_and_harvest(
    client,
    slot_data: Dict[str, Any],
    species: str,
    mode: str = "highest",
    min_mutations: Optional[int] = None,
) -> bool:
    """
    Find and harvest a plant of the specified species based on mutation priority.

    Args:
        client: MagicGardenClient instance
        slot_data: Player's slot data containing garden and inventory
        species: Plant species to find and harvest
        mode: "lowest" to prioritize lowest mutation count (for pet feeding)
              "highest" to prioritize highest mutation count (for auto-harvesting/selling)
        min_mutations: Minimum mutation count required to harvest (default: 3)
                      Set to 0 for pet feeding to harvest any mature plant

    Returns:
        True if successful, False otherwise
    """
    current_time = int(time.time() * 1000)

    garden_data = slot_data.get("garden", {})
    tile_objects = garden_data.get("tileObjects", {})

    # Default min mutations if not specified
    if min_mutations is None:
        min_mutations = 3

    # Find ALL harvestable plants of the specified species
    harvestable_plants = []

    for tile_id, tile_obj in tile_objects.items():
        if not tile_obj or tile_obj.get("objectType") != "plant":
            continue

        slots = tile_obj.get("slots", [])
        for slot_index, plant_slot in enumerate(slots):
            if not plant_slot:
                continue

            plant_species = plant_slot.get("species")
            end_time = plant_slot.get("endTime", 0)
            mutations = plant_slot.get("mutations", [])

            # Check if this plant matches species and is ready to harvest
            if (
                plant_species == species
                and current_time >= end_time
                and len(mutations) >= min_mutations
            ):
                harvestable_plants.append(
                    {
                        "tile_id": int(tile_id),
                        "slot_index": slot_index,
                        "mutation_count": len(mutations),
                        "mutations": mutations,
                    }
                )

    if not harvestable_plants:
        return False

    # Sort based on mode
    if mode == "lowest":
        # Sort by lowest mutation count first (for pet feeding)
        harvestable_plants.sort(key=lambda x: x["mutation_count"])
        priority_msg = "lowest"
    else:
        # Sort by highest mutation count first (for auto-harvesting/selling)
        harvestable_plants.sort(key=lambda x: x["mutation_count"], reverse=True)
        priority_msg = "highest"

    # Get the best match based on priority
    chosen_plant = harvestable_plants[0]
    tile_slot = chosen_plant["tile_id"]
    slots_index = chosen_plant["slot_index"]
    mutation_count = chosen_plant["mutation_count"]

    print(
        f"Found harvestable {species} at slot {tile_slot} (mutations: {mutation_count}, priority: {priority_msg})"
    )

    # Harvest the crop
    harvest_message = {
        "scopePath": ["Room", "Quinoa"],
        "type": "HarvestCrop",
        "slot": tile_slot,
        "slotsIndex": slots_index,
    }
    await client.send(harvest_message)
    print(f"Harvested {species} from slot {tile_slot}")

    # Wait a moment for the harvest to process
    await asyncio.sleep(0.3)

    # Replant the same species
    plant_message = {
        "scopePath": ["Room", "Quinoa"],
        "type": "PlantSeed",
        "slot": tile_slot,
        "species": species,
    }
    await client.send(plant_message)
    print(f"Replanted {species} in slot {tile_slot}")

    return True


async def run_auto_harvest(client, game_state: GameState, config: HarvestConfig):
    """
    Auto-harvest task that runs periodically.

    Monitors the garden and automatically harvests/replants crops
    that meet the minimum mutation requirements.

    Args:
        client: MagicGardenClient instance
        game_state: Global game state
        config: Harvest configuration
    """
    # Wait a bit before starting to allow game state to load
    await asyncio.sleep(15)

    while True:
        try:
            # Get player slot data
            player_slot = game_state.get_player_slot()
            if not player_slot:
                await asyncio.sleep(10)
                continue

            # NOTE: Placeholder for future auto-harvest logic.
            # Pet feeding invokes find_and_harvest directly, so this task
            # intentionally idles until we implement crop selection rules.

            await asyncio.sleep(30)  # Check every 30 seconds

        except Exception as e:
            print(f"Error in auto-harvest task: {e}")
            await asyncio.sleep(10)
