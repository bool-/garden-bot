"""
Constants used throughout the Magic Garden bot.
"""

# Message logging file
MESSAGE_LOG_FILE = "messages.log"

# Configuration file
CONFIG_FILE = "bot_config.json"

# Fallback game version. The client auto-detects the live build at startup
# (MagicGardenClient.refresh_version); this is only used if that fails.
# magicgarden.gg pins each client build; the server rejects outdated releases
# with HTTP 409 "VersionExpired", which makes authentication (and thus the whole
# bot) fail. Refresh this whenever auth starts returning 409: load
# https://magicgarden.gg/ and read the build id from the script tag src,
# e.g. <script src="/version/2036/assets/index-*.js"> -> "2036".
GAME_VERSION = "2071"

# Browser identity used for HTTP and the WebSocket handshake.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
)

# Spawn positions - server coordinates for spawning (determines which garden you get)
# Ordered left-to-right, top-to-bottom (slot 0-5)
# Local (0,0) maps to base position. Slots offset by 26 right and 11 down
# Slot 0 verified on build 2071 (spawn (24,24), tile 169 at (23,22)); the
# other slots assume the old 26/11 spacing still holds.
SPAWN_POSITIONS = [
    {"x": 24, "y": 24},  # Slot 0: Top-left
    {"x": 50, "y": 24},  # Slot 1: Top-middle (26 right)
    {"x": 76, "y": 24},  # Slot 2: Top-right (52 right)
    {"x": 24, "y": 35},  # Slot 3: Bottom-left (11 down)
    {"x": 50, "y": 35},  # Slot 4: Bottom-middle (26 right, 11 down)
    {"x": 76, "y": 35},  # Slot 5: Bottom-right (52 right, 11 down)
]

# Inventory holds at most this many item entries (stackables like seeds count
# once per species; every harvested crop is its own entry). Harvesting into a
# full inventory is rejected by the server, so we never try.
INVENTORY_CAPACITY = 100

# Where the top-bar buttons teleport you (verified on build 2071).
SHOP_STAND = {"x": 40, "y": 30}  # "Shop" -> seed stall, then "Open Seed Shop"
SELL_STAND = {"x": 59, "y": 30}  # "Sell" -> crop stand, then "Sell crops"

# Spawn cell inside a garden's local 23x12 grid (center boardwalk crossing).
LOCAL_SPAWN = {"x": 11, "y": 11}
