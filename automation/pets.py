"""
Pet automation for Magic Garden bot.

Handles pet feeding, movement, and initialization.
"""

import asyncio
import random
from copy import deepcopy
from typing import Optional, Dict, Any

from game_state import GameState
from config import PetFoodConfig
from utils.coordinates import (
    convert_local_to_server_coords,
    convert_server_to_local_coords,
)
from automation.harvest import find_and_harvest


# ========== Helper Functions ==========


def find_player_user_slot(game_state: GameState) -> Optional[Dict[str, Any]]:
    """
    Return the userSlot entry for our player if it exists.

    Returns the full slot object which contains both 'data' and 'petSlotInfos'
    at the slot level.

    Args:
        game_state: Global game state

    Returns:
        Player's user slot or None
    """
    # Use GameState's built-in method which handles locking internally
    return game_state.get_player_slot()


async def wait_for_user_slot(
    game_state: GameState,
    require_data: bool = False,
    timeout: float = 10.0,
    check_interval: float = 0.2,
) -> Optional[Dict[str, Any]]:
    """
    Wait until our user slot (and optional data block) is populated.

    Args:
        game_state: Global game state
        require_data: If True, wait for slot data to be populated
        timeout: Maximum time to wait in seconds
        check_interval: How often to check in seconds

    Returns:
        Player's user slot or None if timeout
    """
    loop = asyncio.get_running_loop()
    start_time = loop.time() if timeout is not None else None
    notified = False

    while True:
        slot = find_player_user_slot(game_state)
        if slot:
            slot_data = slot.get("data")
            if not require_data or isinstance(slot_data, dict):
                return slot

        if timeout is not None and start_time is not None:
            if loop.time() - start_time >= timeout:
                return None

        if not notified:
            if require_data:
                print("Waiting for user slot data to become available...")
            else:
                print("Waiting for user slot to become available...")
            notified = True

        await asyncio.sleep(check_interval)


def get_player_slot_data_for_pets(game_state: GameState) -> Optional[Dict[str, Any]]:
    """
    Return our player's slot data for the Quinoa game.

    Args:
        game_state: Global game state

    Returns:
        Player's slot data or None
    """
    slot = find_player_user_slot(game_state)
    if not slot:
        return None

    slot_data = slot.get("data")
    if isinstance(slot_data, dict):
        return slot_data
    return None


# ========== Pet Initialization ==========


async def initialize_pets(client, game_state: GameState, wait_timeout: float = 10.0):
    """
    Initialize pet positions from game state.

    Args:
        client: MagicGardenClient instance
        game_state: Global game state
        wait_timeout: Maximum time to wait for slot data
    """
    slot_data = get_player_slot_data_for_pets(game_state)
    if not slot_data:
        slot = await wait_for_user_slot(
            game_state, require_data=True, timeout=wait_timeout
        )
        if not slot:
            print("Timed out waiting for user slot data; skipping pet initialization.")
            return
        slot_data = slot.get("data", {})
        if not slot_data:
            return

    pet_slots = slot_data.get("petSlots", [])

    # Initialize positions for each active pet
    # Collect all pet positions to send in one message
    all_pet_positions = {}

    for i, pet_slot in enumerate(pet_slots):
        if pet_slot:
            pet_id = pet_slot.get("id")
            if pet_id:
                # NOTE: The server never provides initial pet positions in userSlots,
                # so we intentionally seed each pet at a random local coordinate.
                # This keeps pets visible immediately after login and avoids future
                # reviewers flagging the randomization as a bug.
                local_pos = {
                    "x": random.randint(0, 22),
                    "y": random.randint(0, 11),
                }

                server_pos = convert_local_to_server_coords(
                    local_pos["x"], local_pos["y"], game_state
                )
                if not server_pos:
                    continue

                # Add to collection
                all_pet_positions[pet_id] = server_pos

                print(
                    "Initialized pet {} at local ({}, {}) -> server ({}, {})".format(
                        pet_id[:8],
                        local_pos["x"],
                        local_pos["y"],
                        server_pos["x"],
                        server_pos["y"],
                    )
                )

    # Send a single PetPositions message with all pets
    if all_pet_positions:
        pet_positions_message = {
            "scopePath": ["Room", "Quinoa"],
            "type": "PetPositions",
            "petPositions": all_pet_positions,
        }
        await client.send(pet_positions_message)

        # Optimistically update petSlotInfos in _full_state so next read isn't stale
        def update_pet_positions(full_state):
            if not full_state:
                return
            child = full_state.get("child", {})
            if child.get("scope") != "Quinoa":
                return
            quinoa_data = child.get("data", {})
            user_slots = quinoa_data.get("userSlots", [])

            # Find player's slot
            for slot in user_slots:
                if slot and slot.get("playerId") == game_state.get_player_id():
                    pet_slot_infos = slot.setdefault("petSlotInfos", {})
                    # Update each pet's position in-place on the live dict
                    for pet_id, pos in all_pet_positions.items():
                        entry = pet_slot_infos.setdefault(pet_id, {})
                        entry["position"] = pos
                    break

        game_state.update_full_state_locked(update_pet_positions)


# ========== Pet Movement ==========


async def move_pets_randomly(
    client, game_state: GameState, wait_timeout: float = 10.0
):
    """
    Randomly move pets within garden bounds and send positions every update.

    Args:
        client: MagicGardenClient instance
        game_state: Global game state
        wait_timeout: Maximum time to wait for slot data
    """
    # Local coordinate bounds (0-indexed): 23 cols (0-22), 12 rows (0-11)
    MIN_X, MAX_X = 0, 22
    MIN_Y, MAX_Y = 0, 11

    slot_data = get_player_slot_data_for_pets(game_state)
    if not slot_data:
        slot = await wait_for_user_slot(
            game_state, require_data=True, timeout=wait_timeout
        )
        if not slot:
            return
        slot_data = slot.get("data", {})
        if not slot_data:
            return

    # petSlotInfos is at the slot level, not in slot['data']
    # Get it from the slot directly
    slot = find_player_user_slot(game_state)
    if not slot:
        return

    pet_slot_infos = slot.get("petSlotInfos", {})

    # If petSlotInfos is not a dict or is empty, nothing to send yet
    if not isinstance(pet_slot_infos, dict) or not pet_slot_infos:
        return

    pet_slots = slot_data.get("petSlots", [])
    active_ids = set(
        slot.get("id")
        for slot in pet_slots
        if isinstance(slot, dict) and slot.get("id")
    )

    all_pet_positions = {}  # Collect all pet positions (always send, even if not moved)
    for pet_id, pet_slot_info in pet_slot_infos.items():

        position = pet_slot_info.get("position")
        if not isinstance(position, dict):
            continue

        x = position.get("x")
        y = position.get("y")
        if x is None or y is None:
            continue

        server_pos = {"x": int(x), "y": int(y)}

        # Convert to local coordinates for movement logic
        local_coords = convert_server_to_local_coords(
            server_pos["x"], server_pos["y"], game_state
        )
        if not local_coords:
            # If we can't convert, just use the server position as-is
            all_pet_positions[pet_id] = server_pos
            continue

        pos = {"x": local_coords["x"], "y": local_coords["y"]}

        # Each pet has different movement probability
        move_chance = random.random()

        new_pos = pos.copy()

        if move_chance < 0.2:  # 20% chance to move per update
            # Build list of valid directions (away from walls)
            valid_directions = []
            if pos["y"] > MIN_Y:
                valid_directions.append("up")
            if pos["y"] < MAX_Y:
                valid_directions.append("down")
            if pos["x"] > MIN_X:
                valid_directions.append("left")
            if pos["x"] < MAX_X:
                valid_directions.append("right")

            # If there are valid directions, choose one and move
            if valid_directions:
                direction = random.choice(valid_directions)

                if direction == "up":
                    new_pos["y"] -= 1
                elif direction == "down":
                    new_pos["y"] += 1
                elif direction == "left":
                    new_pos["x"] -= 1
                elif direction == "right":
                    new_pos["x"] += 1

        # Convert to server coordinates
        new_server_pos = convert_local_to_server_coords(
            new_pos["x"], new_pos["y"], game_state
        )
        if not new_server_pos:
            # Fallback to original position if conversion fails
            all_pet_positions[pet_id] = server_pos
            continue

        # Always add this pet's position (moved or not)
        all_pet_positions[pet_id] = new_server_pos

    # Always send PetPositions message every update (even if positions didn't change)
    if all_pet_positions:
        pet_positions_message = {
            "scopePath": ["Room", "Quinoa"],
            "type": "PetPositions",
            "petPositions": all_pet_positions,
        }
        await client.send(pet_positions_message)

        # Optimistically update petSlotInfos in _full_state so next read isn't stale
        def update_pet_positions(full_state):
            if not full_state:
                return
            child = full_state.get("child", {})
            if child.get("scope") != "Quinoa":
                return
            quinoa_data = child.get("data", {})
            user_slots = quinoa_data.get("userSlots", [])

            # Find player's slot
            for slot in user_slots:
                if slot and slot.get("playerId") == game_state.get_player_id():
                    pet_slot_infos = slot.setdefault("petSlotInfos", {})
                    # Update each pet's position in-place on the live dict
                    for pet_id, pos in all_pet_positions.items():
                        entry = pet_slot_infos.setdefault(pet_id, {})
                        entry["position"] = pos
                    break

        game_state.update_full_state_locked(update_pet_positions)


# ========== Pet Feeding ==========


async def feed_hungry_pets(client, game_state: GameState, config: PetFoodConfig):
    """
    Check for hungry pets and feed them with appropriate produce.

    Args:
        client: MagicGardenClient instance
        game_state: Global game state
        config: Pet food configuration mapping
    """
    # Get player slot using GameState's method (handles locking internally)
    our_slot = game_state.get_player_slot()
    if not our_slot:
        return

    slot_data = our_slot.get("data", {})
    pet_slots = slot_data.get("petSlots", [])

    # Get inventory items
    inv_data = slot_data.get("inventory", {})
    items_list = inv_data.get("items", [])

    # Build produce lookup by species
    produce_by_species = {}
    for item in items_list:
        if item.get("itemType") == "Produce":
            species = item.get("species")
            item_id = item.get("id")
            if species and item_id:
                if species not in produce_by_species:
                    produce_by_species[species] = []
                produce_by_species[species].append(item_id)

    # Get pet food mappings from config (or use default if not set)
    pet_food_map = (
        config.mapping
        if config and config.mapping
        else {"Bee": "OrangeTulip", "Chicken": "Aloe", "Worm": "Aloe"}
    )

    # Check each active pet slot
    for pet_slot in pet_slots:
        if not pet_slot:
            continue

        pet_id = pet_slot.get("id")
        pet_species = pet_slot.get("petSpecies")
        hunger = pet_slot.get("hunger", 0)

        # Check if pet is hungry (hunger == 0)
        if hunger == 0 and pet_species in pet_food_map:
            required_food = pet_food_map[pet_species]

            # Check if we have the required produce
            if (
                required_food in produce_by_species
                and produce_by_species[required_food]
            ):
                crop_item_id = produce_by_species[required_food][0]

                # Send FeedPet action
                feed_message = {
                    "type": "FeedPet",
                    "petItemId": pet_id,
                    "cropItemId": crop_item_id,
                    "scopePath": ["Room", "Quinoa"],
                }
                await client.send(feed_message)
                print(f"Fed {pet_species} (ID: {pet_id[:8]}...) with {required_food}")

                # Remove the used produce from our lookup to avoid double-feeding
                produce_by_species[required_food].pop(0)
                if not produce_by_species[required_food]:
                    del produce_by_species[required_food]
            else:
                # No produce available - try to harvest and replant
                # Use mode="lowest" to prioritize plants with lowest mutation count for pet feeding
                # Use min_mutations=0 to accept any mature plant regardless of mutation count
                print(
                    f"{pet_species} is hungry but no {required_food} available in inventory"
                )
                print(
                    f"Searching for harvestable {required_food} (prioritizing lowest mutations for pet feeding)..."
                )

                success = await find_and_harvest(
                    client, slot_data, required_food, mode="lowest", min_mutations=0
                )

                if success:
                    print(f"Harvested and replanted {required_food} for {pet_species}")
                    # Wait for the harvest to be processed and added to inventory
                    await asyncio.sleep(1.0)
                else:
                    print(f"No harvestable {required_food} found in garden")


# ========== Pet Tasks ==========


async def run_pet_feeder(client, game_state: GameState, config: PetFoodConfig):
    """
    Pet feeding task that runs periodically.

    Args:
        client: MagicGardenClient instance
        game_state: Global game state
        config: Pet food configuration
    """
    # Wait a bit before starting to allow game state to load
    await asyncio.sleep(10)

    while True:
        await asyncio.sleep(5)  # Check every 5 seconds
        try:
            await feed_hungry_pets(client, game_state, config)
        except Exception as e:
            print(f"Error in pet feeding task: {e}")


async def run_pet_mover(client, game_state: GameState):
    """
    Pet movement task that runs periodically.

    Args:
        client: MagicGardenClient instance
        game_state: Global game state
    """
    # Wait for startup task to complete pet initialization
    await asyncio.sleep(8)

    while True:
        await asyncio.sleep(1)  # Send pet positions every second
        try:
            await move_pets_randomly(client, game_state)
        except Exception as e:
            print(f"Error in pet movement task: {e}")
