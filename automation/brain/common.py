"""
Shared imports and constants for the garden brain.

The garden brain: one loop that plays the whole game the way a person would,
one action at a time, and optimises for coins.

Every tick, in priority order (each step does one bounded chunk of work and
returns, so hungry pets are never kept waiting behind a long harvest):

  1. Pets   - keep every pet fed with the diet crop that best fits its hunger
              bar (hunger is measured in coins). Fed GoldGranter/RainbowGranter
              pets are the account's money multiplier.
  2. Shop   - on every restock, Teleport to the market and buy everything left
              in the seed, egg and tool stalls, walking stall to stall.
  3. Sell   - Teleport to the crop stand and Sell crops when the bag is filling
              up or holds something valuable. Locked items are never sold.
  4. Harvest- cheap crops as soon as they're ripe; valuable crops only once a
              pet has stamped Gold/Rainbow on them (x25/x50) - unless no
              granter pet is working, then everything ripe.
  5. Plant  - empty tiles: a small food farm per pet first, then the best
              seeds we own.

Wire formats were captured from the real web client (build 2071).
"""

import asyncio
import collections
import json
import os
import random
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from automation import economy as eco  # noqa: F401
from automation.movement import (
    current_position,
    distance,
    go_home,
    go_to_sell,
    teleport,
    tile_to_server,
    walk_to,
    walk_to_tile,
)
from utils.constants import INVENTORY_CAPACITY

GARDEN_TILES = 200
STATE_FILE = "bot_state.json"  # remembers server-rejected purchases across restarts
REJECTION_TTL_S = 24 * 3600
SCOPE = ["Room", "Quinoa"]


def _now_ms(full_state) -> int:
    try:
        return int(full_state["child"]["data"]["currentTime"])
    except Exception:
        return int(time.time() * 1000)


