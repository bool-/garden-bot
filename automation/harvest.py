"""
Harvest automation for Magic Garden bot.

Handles finding, harvesting, and replanting crops automatically.
"""

import asyncio
import random
import time
import uuid
from typing import Optional, Tuple, Dict, Any

from game_state import GameState
from config import HarvestConfig
from utils.constants import INVENTORY_CAPACITY
from automation.movement import walk_to_tile, tile_to_server, current_position, distance, go_to_sell, go_home


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

    if not await walk_to_tile(client, client.game_state, tile_slot):
        return False

    # Harvest the crop. The current protocol (v2036) wraps the action in a
    # QuinoaCommand, requires a client-generated cropItemId, and carries the
    # auto-replant species as the top-level successorItemId (matching how the
    # real client harvests-and-replants in a single command).
    await client.send_command(
        {
            "type": "HarvestCrop",
            "slot": tile_slot,
            "slotsIndex": slots_index,
            "cropItemId": str(uuid.uuid4()),
        },
        successorItemId=species,
    )
    print(f"Harvested and replanted {species} at slot {tile_slot}")

    return True


async def find_and_harvest(
    client,
    slot_data: Dict[str, Any],
    species: str,
    mode: str = "highest",
    min_mutations: Optional[int] = None,
    should_replant: bool = True,
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
        should_replant: Whether to replant after harvesting (False for perennial plants)

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

    # Skip plants we already harvested whose removal the server hasn't sent yet.
    recent = getattr(client, "_recent_harvests", set())
    harvestable_plants = [
        p for p in harvestable_plants if (p["tile_id"], p["slot_index"]) not in recent
    ]
    if not harvestable_plants:
        return False

    # A person harvests whatever is closest next; walk order follows position.
    here = current_position(client.game_state)
    slot_index = client.game_state.get_user_slot_index()

    def walk_cost(p):
        there = tile_to_server(p["tile_id"], slot_index)
        return distance(here, there) if here and there else 0

    # Sort based on mode
    if mode == "lowest":
        # Sort by lowest mutation count first (for pet feeding)
        harvestable_plants.sort(key=lambda x: (x["mutation_count"], walk_cost(x)))
        priority_msg = "lowest"
    else:
        # Sort by highest mutation count first (for auto-harvesting/selling)
        # Every eligible plant gets harvested this pass, so go nearest-first.
        harvestable_plants.sort(key=lambda x: (walk_cost(x), -x["mutation_count"]))
        priority_msg = "nearest"

    # Get the best match based on priority
    chosen_plant = harvestable_plants[0]
    tile_slot = chosen_plant["tile_id"]
    slots_index = chosen_plant["slot_index"]
    mutation_count = chosen_plant["mutation_count"]

    print(
        f"Found harvestable {species} at tile {tile_slot}, slot {slots_index} (mutations: {mutation_count}, priority: {priority_msg})"
    )

    if inventory_full(client.game_state):
        return False

    # Walk onto the plant first, like a player using click-to-move.
    if not await walk_to_tile(client, client.game_state, tile_slot):
        return False

    # Harvest the crop (QuinoaCommand envelope). The replant species is carried
    # as the top-level successorItemId; omit it entirely to not replant
    # (perennial plants like Bamboo/Sunflower).
    harvest_extra = {"successorItemId": species} if should_replant else {}
    await client.send_command(
        {
            "type": "HarvestCrop",
            "slot": tile_slot,
            "slotsIndex": slots_index,
            "cropItemId": str(uuid.uuid4()),
        },
        **harvest_extra,
    )
    if not hasattr(client, "_recent_harvests"):
        client._recent_harvests = set()
    client._recent_harvests.add((tile_slot, slots_index))
    print(
        f"Harvested {species} from tile {tile_slot}, slot {slots_index}"
        + (" (replanting)" if should_replant else "")
    )

    return True


def inventory_full(game_state) -> bool:
    slot = game_state.get_player_slot() or {}
    items = (((slot.get("data") or {}).get("inventory") or {}).get("items")) or []
    return len(items) >= INVENTORY_CAPACITY


async def _sell_crops(client, game_state):
    # "Sell" button -> crop stand -> "Sell crops" -> "Garden"
    await go_to_sell(client, game_state)
    await asyncio.sleep(random.uniform(0.6, 1.5))
    await client.send_command({"type": "SellAllCrops"})
    print("Sold all crops")
    await asyncio.sleep(random.uniform(0.8, 1.8))
    await go_home(client, game_state)
    # give the server a moment to push the emptied inventory
    await asyncio.sleep(random.uniform(1.0, 2.0))


async def _harvest_pass(client, game_state: GameState, config: HarvestConfig, slot_data) -> bool:
    """One pass: walk to and harvest every eligible plant, then (optionally) sell."""
    harvested_any = False
    for species in config.species_to_harvest:
        should_replant = species in config.species_to_replant

        # Keep harvesting this species until no more are ready
        while True:
            try:
                success = await find_and_harvest(
                    client,
                    slot_data,
                    species,
                    mode="highest",
                    min_mutations=config.min_mutations,
                    should_replant=should_replant,
                )
            except Exception as e:
                print(f"Error harvesting {species}: {e}")
                break  # Move to next species on error

            if not success:
                if inventory_full(game_state):
                    if config.sell_after_harvest:
                        await _sell_crops(client, game_state)
                        player_slot = game_state.get_player_slot()
                        slot_data = (player_slot or {}).get("data") or {}
                        if slot_data and not inventory_full(game_state):
                            continue
                    print("Inventory full (100/100); stopping harvest until there's room")
                    return harvested_any
                break  # No more plants of this species ready
            harvested_any = True
            # Short, uneven pause before heading to the next plant
            await asyncio.sleep(random.uniform(0.2, 0.9))
            player_slot = game_state.get_player_slot()
            if not player_slot:
                break
            slot_data = player_slot.get("data", {})

    # New pass next time: the server state has caught up by then.
    if hasattr(client, "_recent_harvests"):
        client._recent_harvests.clear()

    if harvested_any and config.sell_after_harvest:
        try:
            await _sell_crops(client, game_state)
        except Exception as e:
            print(f"Error selling crops: {e}")
    return harvested_any


async def run_auto_harvest(client, game_state: GameState, config: HarvestConfig):
    """
    Auto-harvest task that runs periodically.

    Monitors the garden and walks to and harvests crops that meet the
    minimum mutation requirements. Holds client.body_lock for each pass so
    shop trips and pet feeding never interleave with a walk.
    """
    try:
        # Wait a bit before starting to allow game state to load
        await asyncio.sleep(15)

        while True:
            player_slot = game_state.get_player_slot() if config.enabled else None
            slot_data = (player_slot or {}).get("data") or {}
            if slot_data:
                async with client.body_lock:
                    await _harvest_pass(client, game_state, config, slot_data)
            await asyncio.sleep(config.check_interval_seconds)

    except asyncio.CancelledError:
        # Task cancelled due to disconnection
        pass
    except Exception as e:
        print(f"Error in auto-harvest task: {e}")
        raise
