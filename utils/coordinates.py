"""
Coordinate conversion utilities for Magic Garden bot.

Handles conversion between local garden coordinates (0-22 x, 0-11 y)
and server world coordinates.
"""

import random
from typing import Dict, Optional

from game_state import GameState
from utils.constants import SPAWN_POSITIONS


def get_random_spawn_position() -> Dict[str, int]:
    """Select a random spawn position to send to server (determines garden slot)."""
    return random.choice(SPAWN_POSITIONS).copy()


def get_local_spawn_position() -> Dict[str, int]:
    """Get the local position where player appears (bottom center of own garden).

    Returns:
        Dict with 'x' and 'y' keys for local spawn position
    """
    # Player spawns at bottom center in local coordinates
    # Local coords: x=0-22 (23 cols), y=0-11 (12 rows)
    # Bottom center: x=11 (middle of 23), y=11 (near bottom)
    return {"x": 11, "y": 11}


def get_slot_base_position(game_state: GameState) -> Dict[str, int]:
    """Get the base server coordinates for our user slot.

    Args:
        game_state: Game state to query

    Returns:
        Dict with 'x' and 'y' keys for slot base position
    """
    slot_idx = game_state.get_user_slot_index()
    if slot_idx is None or slot_idx >= len(SPAWN_POSITIONS):
        # Default to slot 0 if unknown
        return SPAWN_POSITIONS[0].copy()
    return SPAWN_POSITIONS[slot_idx].copy()


def convert_local_to_server_coords(
    local_x: int,
    local_y: int,
    game_state: GameState
) -> Optional[Dict[str, int]]:
    """Convert local garden coordinates to server world coordinates.

    Args:
        local_x: Local X coordinate (0-22)
        local_y: Local Y coordinate (0-11)
        game_state: Game state to query for slot position

    Returns:
        Dict with 'x' and 'y' server coordinates, or None if conversion fails
    """
    spawn_pos = get_slot_base_position(game_state)  # Where player spawns (bottom-center)
    local_spawn = get_local_spawn_position()  # Player local position (11, 11)

    if (
        spawn_pos is None
        or local_spawn is None
        or local_x is None
        or local_y is None
        or game_state.get_user_slot_index() is None
    ):
        return None

    # Spawn position is where local (11, 11) maps to in server coords
    # So: server = spawn_pos + (local - local_spawn)
    server_x = spawn_pos["x"] + (local_x - local_spawn["x"])
    server_y = spawn_pos["y"] + (local_y - local_spawn["y"])
    return {"x": int(server_x), "y": int(server_y)}


def convert_server_to_local_coords(
    server_x: int,
    server_y: int,
    game_state: GameState
) -> Optional[Dict[str, int]]:
    """Convert server world coordinates to local garden coordinates.

    Args:
        server_x: Server X coordinate
        server_y: Server Y coordinate
        game_state: Game state to query for slot position

    Returns:
        Dict with 'x' and 'y' local coordinates, or None if conversion fails
    """
    spawn_pos = get_slot_base_position(game_state)  # Where player spawns (bottom-center)
    local_spawn = get_local_spawn_position()  # Player local position (11, 11)

    if (
        spawn_pos is None
        or local_spawn is None
        or server_x is None
        or server_y is None
        or game_state.get_user_slot_index() is None
    ):
        return None

    # Spawn position is where local (11, 11) maps to in server coords
    # So: local = local_spawn + (server - spawn_pos)
    local_x = local_spawn["x"] + (server_x - spawn_pos["x"])
    local_y = local_spawn["y"] + (server_y - spawn_pos["y"])
    return {"x": int(local_x), "y": int(local_y)}
