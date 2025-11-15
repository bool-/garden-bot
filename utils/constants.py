"""
Constants used throughout the Magic Garden bot.
"""

# Message logging file
MESSAGE_LOG_FILE = "messages.log"

# Configuration file
CONFIG_FILE = "bot_config.json"

# Game version (used in API URLs and WebSocket connection)
GAME_VERSION = "cb622cd"

# Spawn positions - server coordinates for spawning (determines which garden you get)
# Ordered left-to-right, top-to-bottom (slot 0-5)
# Local (0,0) maps to base position. Slots offset by 26 right and 11 down
SPAWN_POSITIONS = [
    {"x": 14, "y": 14},  # Slot 0: Top-left
    {"x": 40, "y": 14},  # Slot 1: Top-middle (26 right)
    {"x": 66, "y": 14},  # Slot 2: Top-right (52 right)
    {"x": 14, "y": 25},  # Slot 3: Bottom-left (11 down)
    {"x": 40, "y": 25},  # Slot 4: Bottom-middle (26 right, 11 down)
    {"x": 66, "y": 25},  # Slot 5: Bottom-right (52 right, 11 down)
]
