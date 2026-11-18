"""
Walking, the way the real client does it.

Verified against the live web client (build 2071, 2026-11-17):
- Click-to-move walks one tile per step along an L-shaped path (no diagonals),
  sending one raw PlayerPosition per tile, about 133 ms apart.
- The server confirms each step with a QuinoaPlayerTimelineBatch "walk" entry
  (from -> to); protocol.py feeds those back into game_state, so our idea of
  where we stand follows the server's.
- A player who just connected stands on their garden's spawn tile without
  having sent any position.
- Harvesting is done standing on the plant's tile (the in-game Harvest button
  acts on the tile under you).
"""

import asyncio
import random
from typing import Optional, Tuple

from utils.constants import SPAWN_POSITIONS, LOCAL_SPAWN, SHOP_STAND, SELL_STAND

# Seconds per tile step measured on the real client (~133 ms, frame-locked).
STEP_SECONDS = 0.133
STEP_JITTER = 0.008


def tile_to_server(tile_id: int, slot_index: int) -> Optional[Tuple[int, int]]:
    """Map a garden tile id (0-199, 20 cols x 10 rows) to world coordinates.

    The garden is drawn as 23 x 12 local cells: boardwalk on row 0/11 and
    columns 0/11/22, plantable cells in between. Local (11, 11) is the spawn.
    """
    if slot_index is None or not (0 <= slot_index < len(SPAWN_POSITIONS)):
        return None
    row, col = divmod(int(tile_id), 20)
    local_x = col + 1 if col < 10 else col + 2
    local_y = row + 1
    spawn = SPAWN_POSITIONS[slot_index]
    return (
        spawn["x"] + local_x - LOCAL_SPAWN["x"],
        spawn["y"] + local_y - LOCAL_SPAWN["y"],
    )


def current_position(game_state) -> Optional[Tuple[int, int]]:
    pos = game_state.get_player_position() or {}
    if pos.get("x") is None or pos.get("y") is None:
        return None
    return pos["x"], pos["y"]


def distance(a: Tuple[int, int], b: Tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


async def walk_to(client, game_state, x: int, y: int) -> bool:
    """Walk tile-by-tile to (x, y). Returns False if the connection dropped."""
    start = current_position(game_state)
    if start is None:
        slot = game_state.get_user_slot_index()
        if slot is None:
            return False
        start = (SPAWN_POSITIONS[slot]["x"], SPAWN_POSITIONS[slot]["y"])

    cx, cy = start
    if (cx, cy) == (x, y):
        return True

    # L-shaped path; the real pathfinder picks either leg first.
    steps = []
    x_first = random.random() < 0.5
    legs = ("x", "y") if x_first else ("y", "x")
    for axis in legs:
        if axis == "x":
            while cx != x:
                cx += 1 if x > cx else -1
                steps.append((cx, cy))
        else:
            while cy != y:
                cy += 1 if y > cy else -1
                steps.append((cx, cy))

    # The first step goes out almost immediately after the "click".
    await asyncio.sleep(random.uniform(0.03, 0.07))
    for i, (sx, sy) in enumerate(steps):
        if i:
            await asyncio.sleep(max(0.11, random.gauss(STEP_SECONDS, STEP_JITTER)))
        if not client.is_connected:
            return False
        await client.send(
            {
                "scopePath": ["Room", "Quinoa"],
                "type": "PlayerPosition",
                "position": {"x": sx, "y": sy},
            }
        )
        game_state.set_player_position(sx, sy)
    return True


async def teleport(client, game_state, x: int, y: int) -> bool:
    """What the top-bar Shop/Garden/Sell buttons send."""
    if not client.is_connected:
        return False
    await client.send(
        {"scopePath": ["Room", "Quinoa"], "type": "Teleport", "position": {"x": x, "y": y}}
    )
    game_state.set_player_position(x, y)
    # Screen fades over to the new place before the player acts again.
    await asyncio.sleep(random.uniform(0.8, 1.6))
    return True


def home_position(game_state) -> Optional[Tuple[int, int]]:
    slot = game_state.get_user_slot_index()
    if slot is None or not (0 <= slot < len(SPAWN_POSITIONS)):
        return None
    return SPAWN_POSITIONS[slot]["x"], SPAWN_POSITIONS[slot]["y"]


def in_own_garden(game_state) -> bool:
    home, here = home_position(game_state), current_position(game_state)
    if not home or not here:
        return False
    # Local grid is x 0..22, y 0..11 with spawn at local (11, 11).
    return (home[0] - 11 <= here[0] <= home[0] + 11) and (home[1] - 11 <= here[1] <= home[1])


async def go_home(client, game_state) -> bool:
    """The "Garden" button."""
    home = home_position(game_state)
    if home is None:
        return False
    if in_own_garden(game_state):
        return True
    return await teleport(client, game_state, *home)


async def go_to_shop(client, game_state) -> bool:
    return await teleport(client, game_state, SHOP_STAND["x"], SHOP_STAND["y"])


async def go_to_sell(client, game_state) -> bool:
    return await teleport(client, game_state, SELL_STAND["x"], SELL_STAND["y"])


async def walk_to_tile(client, game_state, tile_id: int) -> bool:
    """Walk onto a garden tile of our own slot, then settle like a person."""
    target = tile_to_server(tile_id, game_state.get_user_slot_index())
    if target is None:
        return False
    if not in_own_garden(game_state) and not await go_home(client, game_state):
        return False
    if not await walk_to(client, game_state, *target):
        return False
    # Arrive, look at the plant card, press Harvest.
    await asyncio.sleep(random.uniform(0.35, 1.1))
    return True
