"""
Network protocol handling for Magic Garden bot.

Handles JSON Patch operations, message serialization/deserialization,
and message processing that updates GameState.
"""

import json
from datetime import datetime
from typing import Dict, Any, Optional
from copy import deepcopy

from game_state import GameState
from utils.constants import MESSAGE_LOG_FILE, SPAWN_POSITIONS


# ========== Custom Exceptions ==========

class GardenFullError(Exception):
    """Raised when the garden has all 6 slots occupied by other players."""
    pass


# ========== JSON Patch Implementation (RFC 6901) ==========

def parse_json_pointer(pointer):
    """Parse a JSON Pointer (RFC 6901) into path components"""
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise ValueError(f"Invalid JSON Pointer: {pointer}")

    # Split by / and unescape
    parts = pointer[1:].split("/")
    return [part.replace("~1", "/").replace("~0", "~") for part in parts]


def get_by_pointer(obj, pointer):
    """Get value at JSON Pointer path"""
    parts = parse_json_pointer(pointer)
    current = obj
    for part in parts:
        if isinstance(current, dict):
            current = current[part]
        elif isinstance(current, list):
            current = current[int(part)]
        else:
            raise ValueError(f"Cannot navigate to {pointer}")
    return current


def set_by_pointer(obj, pointer, value):
    """Set value at JSON Pointer path"""
    parts = parse_json_pointer(pointer)
    if not parts:
        raise ValueError("Cannot replace root")

    current = obj
    for part in parts[:-1]:
        if isinstance(current, dict):
            current = current[part]
        elif isinstance(current, list):
            current = current[int(part)]
        else:
            raise ValueError(f"Cannot navigate to {pointer}")

    last_part = parts[-1]
    if isinstance(current, dict):
        current[last_part] = value
    elif isinstance(current, list):
        current[int(last_part)] = value
    else:
        raise ValueError(f"Cannot set value at {pointer}")


def add_by_pointer(obj, pointer, value):
    """Add value at JSON Pointer path"""
    parts = parse_json_pointer(pointer)
    if not parts:
        raise ValueError("Cannot add to root")

    current = obj
    for part in parts[:-1]:
        if isinstance(current, dict):
            # If key doesn't exist, create empty dict for nested structure
            if part not in current:
                current[part] = {}
            current = current[part]
        elif isinstance(current, list):
            current = current[int(part)]
        else:
            raise ValueError(f"Cannot navigate to {pointer}")

    last_part = parts[-1]
    if isinstance(current, dict):
        current[last_part] = value
    elif isinstance(current, list):
        # For arrays, can use "-" to append or index to insert
        if last_part == "-":
            current.append(value)
        else:
            current.insert(int(last_part), value)
    else:
        raise ValueError(f"Cannot add value at {pointer}")


def remove_by_pointer(obj, pointer):
    """Remove value at JSON Pointer path"""
    parts = parse_json_pointer(pointer)
    if not parts:
        raise ValueError("Cannot remove root")

    current = obj
    for part in parts[:-1]:
        if isinstance(current, dict):
            current = current[part]
        elif isinstance(current, list):
            current = current[int(part)]
        else:
            raise ValueError(f"Cannot navigate to {pointer}")

    last_part = parts[-1]
    if isinstance(current, dict):
        del current[last_part]
    elif isinstance(current, list):
        del current[int(last_part)]
    else:
        raise ValueError(f"Cannot remove value at {pointer}")


def apply_json_patch(obj, patch):
    """Apply a single JSON Patch operation to obj"""
    op = patch["op"]
    path = patch["path"]

    if op == "replace":
        set_by_pointer(obj, path, patch["value"])
    elif op == "add":
        add_by_pointer(obj, path, patch["value"])
    elif op == "remove":
        remove_by_pointer(obj, path)
    else:
        raise ValueError(f"Unsupported operation: {op}")


# ========== Message Logging ==========

def log_message_to_file(direction: str, message, timestamp=None):
    """Log all messages to file"""
    if timestamp is None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    try:
        with open(MESSAGE_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"[{timestamp}] {direction}\n")
            f.write(f"{'='*80}\n")
            if isinstance(message, str):
                # Try to parse as JSON, but if it fails, log as raw text
                try:
                    parsed = json.loads(message)
                    f.write(json.dumps(parsed, indent=2))
                except json.JSONDecodeError:
                    # Not JSON - log as plain text
                    f.write(message)
            else:
                f.write(json.dumps(message, indent=2))
            f.write("\n")
    except Exception as e:
        # Only suppress file I/O errors, not JSON parsing errors
        print(f"Warning: Failed to log message to file: {e}")


# ========== Message Processing ==========

def process_welcome_message(data: Dict[str, Any], game_state: GameState) -> Optional[Dict[str, int]]:
    """Process Welcome message and update game state.

    Args:
        data: Welcome message data
        game_state: Game state to update

    Returns:
        Server spawn position dict or None
    """
    log_message_to_file("RECEIVED (Welcome)", data)

    print("\n" + "=" * 60)
    print("PROCESSING WELCOME MESSAGE")
    print("=" * 60)

    our_player_id = game_state.get_player_id()
    print(f"Looking for player: {our_player_id}")

    # Navigate to Quinoa game state
    if "fullState" not in data:
        print("ERROR: No fullState in welcome message")
        return None

    full_state = data["fullState"]

    # Store the entire fullState
    game_state.set_full_state(full_state)
    game_state.refresh_player_metadata()

    # Get room data for player names
    room_data = full_state.get("data", {})

    # Get Quinoa game state
    if "child" not in full_state or full_state["child"].get("scope") != "Quinoa":
        print("ERROR: No Quinoa game state found")
        return None

    quinoa_state = full_state["child"].get("data", {})
    user_slots = quinoa_state.get("userSlots", [])

    print(f"Found {len(user_slots)} user slots")

    # Check if we are the host
    host_player_id = room_data.get("hostPlayerId")
    is_host = host_player_id == our_player_id
    print(f"Host Player ID: {host_player_id}")
    print(f"Are we the host? {is_host}")

    # List all players in the room and find our slot
    print("\nPlayers in room:")
    occupied_slots = []
    our_slot_found = False
    for slot_idx, slot in enumerate(user_slots):
        if slot:
            player_id = slot.get("playerId")
            player_name = "Unknown"

            # Get player name from room data
            if "players" in room_data:
                for room_player in room_data["players"]:
                    if room_player.get("id") == player_id:
                        player_name = room_player.get("name", "Unknown")
                        break

            print(f"  • Slot {slot_idx}: ID: {player_id} | Name: {player_name}")
            occupied_slots.append(slot_idx)

            # Store our player's name and slot index (already done by refresh_player_metadata)
            if player_id == our_player_id:
                print(f"  → We are in slot {slot_idx}")
                our_slot_found = True

    # Check if garden is full (all 6 slots occupied by other players)
    if len(occupied_slots) == 6 and not our_slot_found:
        print("\n" + "!" * 60)
        print("GARDEN FULL: All 6 slots occupied by other players")
        print("!" * 60)
        raise GardenFullError("Garden has all 6 slots occupied by other players")

    # Get spawn position for our detected slot
    user_slot_index = game_state.get_user_slot_index()
    if user_slot_index is not None:
        server_spawn_pos = SPAWN_POSITIONS[user_slot_index].copy()
        print(f"\nUsing spawn position for slot {user_slot_index}")
    else:
        # Don't assume - will wait for server to tell us which slot we're in
        server_spawn_pos = None
        print("\nSlot not yet assigned, will wait for server update")

    if server_spawn_pos:
        print(
            f"Will send spawn position: ({server_spawn_pos['x']}, {server_spawn_pos['y']})"
        )
    else:
        print("Will wait to send spawn position until slot is assigned")

    if is_host:
        print("We are the host")
    else:
        print("We are NOT the host")
    print("WELCOME MESSAGE PROCESSED")
    print(f"Player: {game_state.get_player_name() or game_state.get_player_id()}")
    print("=" * 60 + "\n")

    game_state.set_stat("last_update", datetime.now().strftime("%H:%M:%S"))

    # Return the server spawn position
    return server_spawn_pos


def process_partial_state_message(data: Dict[str, Any], game_state: GameState):
    """Process PartialState message by applying JSON patches.

    Args:
        data: PartialState message data
        game_state: Game state to update
    """
    log_message_to_file("RECEIVED (PartialState)", data)

    # Check if we have full state (use unsafe accessor to avoid expensive deepcopy)
    if not game_state.get_full_state_unsafe():
        print("WARNING: Received PartialState before Welcome message")
        return

    if "patches" not in data:
        print("WARNING: PartialState message has no patches")
        return

    patches = data["patches"]

    # Apply each patch to the fullState
    for patch in patches:
        try:
            def apply_patch(fs):
                apply_json_patch(fs, patch)
            game_state.update_full_state_locked(apply_patch)
            game_state.increment_stat("patches_applied")
        except Exception as e:
            print(f"ERROR applying patch: {e}")
            print(f"Patch: {patch}")

    game_state.set_stat("last_update", datetime.now().strftime("%H:%M:%S"))
    game_state.refresh_player_metadata()


def is_player_in_room_state(full_state: Dict[str, Any], player_id: str) -> bool:
    """Return True if the provided full_state shows the player in the room."""
    if not full_state or not player_id:
        return False

    room_data = full_state.get("data") or {}
    players = room_data.get("players") or []

    for slot in players:
        if slot and slot.get("id") == player_id:
            return True
    return False


def process_message(message: str, game_state: GameState) -> Optional[Dict[str, Any]]:
    """Process incoming websocket message.

    Args:
        message: Raw message string
        game_state: Game state to update

    Returns:
        Parsed message data or None if parse failed
    """
    try:
        game_state.increment_stat("messages_received")
        data = json.loads(message)
        msg_type = data.get("type")

        if msg_type == "Welcome":
            process_welcome_message(data, game_state)
        elif msg_type == "PartialState":
            process_partial_state_message(data, game_state)
        elif msg_type == "Ping":
            game_state.increment_stat("pings_received")
            log_message_to_file(f"RECEIVED ({msg_type})", data)
        elif msg_type == "Pong":
            game_state.increment_stat("pongs_received")
            log_message_to_file(f"RECEIVED ({msg_type})", data)
        else:
            log_message_to_file(f"RECEIVED ({msg_type})", data)

        return data
    except json.JSONDecodeError:
        log_message_to_file("RECEIVED (RAW)", message)
        return None
