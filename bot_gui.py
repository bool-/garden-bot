import asyncio
import websockets
import json
import aiohttp
import secrets
import os
import sys
import tkinter as tk
from tkinter import ttk, scrolledtext
from datetime import datetime
import threading
import traceback
from copy import deepcopy
import random


# Console output redirector for GUI
class ConsoleRedirector:
    def __init__(self, widget, original_stream):
        self.widget = widget
        self.original_stream = original_stream

    def write(self, message):
        # Write to original console
        self.original_stream.write(message)
        self.original_stream.flush()

        # Write to GUI widget (thread-safe)
        if self.widget:
            try:
                self.widget.insert(tk.END, message)
                self.widget.see(tk.END)
            except:
                pass  # Ignore errors if widget is destroyed

    def flush(self):
        self.original_stream.flush()


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

# Game state - stores full state and metadata
game_state = {
    "player_id": None,
    "player_name": None,
    "room_id": None,  # Current room ID
    "full_state": None,  # Store entire fullState from Welcome message
    "player_position": {
        "x": 11,
        "y": 11,
    },  # Track player position (local coords: 0-22 for x, 0-11 for y)
    "user_slot_index": None,  # Which user slot (0-5) we're in
    "pet_positions": {},  # Track pet positions {pet_id: {"x": x, "y": y}}
    "pet_positions_synced_with_server": False,
    "statistics": {  # Connection statistics
        "messages_received": 0,
        "messages_sent": 0,
        "pings_sent": 0,
        "pings_received": 0,
        "pongs_sent": 0,
        "pongs_received": 0,
        "last_update": "Never",
        "patches_applied": 0,
    },
}

# Lock to protect game_state from concurrent access
game_state_lock = threading.Lock()

MESSAGE_LOG_FILE = "messages.log"
CONFIG_FILE = "bot_config.json"

# Shop configuration
shop_config = None

# Harvest configuration
harvest_config = None


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


def get_random_spawn_position():
    """Select a random spawn position to send to server (determines garden slot)"""
    return random.choice(SPAWN_POSITIONS).copy()


def get_local_spawn_position():
    """Get the local position where player appears (bottom center of own garden)"""
    # Player spawns at bottom center in local coordinates
    # Local coords: x=0-22 (23 cols), y=0-11 (12 rows)
    # Bottom center: x=11 (middle of 23), y=10 (near bottom, row 10 is last garden row in visual)
    return {"x": 11, "y": 11}


# JSON Patch implementation
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


def parse_command_line_args():
    """Parse command line arguments"""
    room_id_override = None
    for arg in sys.argv[1:]:
        if arg.startswith("--room-id="):
            room_id_override = arg.split("=", 1)[1]
    return room_id_override


# GUI Application - Simple Inventory Display
class MagicGardenGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("🌻 Magic Garden Bot")
        self.root.geometry("1250x800")

        # Modern color palette
        self.colors = {
            "bg_dark": "#0f0f1e",           # Deep navy background
            "bg_medium": "#1a1a2e",         # Medium navy
            "bg_light": "#25254a",          # Lighter navy/purple
            "accent_primary": "#6c5ce7",    # Vibrant purple
            "accent_secondary": "#00b894",  # Teal green
            "accent_tertiary": "#fd79a8",   # Pink
            "text_primary": "#e8e8f0",      # Off-white
            "text_secondary": "#a0a0c0",    # Muted purple-gray
            "success": "#00e676",           # Bright green
            "warning": "#ffd93d",           # Golden yellow
            "error": "#ff6b9d",             # Pink-red
            "canvas_bg": "#16162a",         # Canvas background
        }

        self.root.configure(bg=self.colors["bg_dark"])

        # Modern Style
        style = ttk.Style()
        style.theme_use("clam")

        # Frame styles
        style.configure("TFrame", background=self.colors["bg_dark"])
        style.configure("Card.TFrame", background=self.colors["bg_medium"], relief="flat")

        # Label styles
        style.configure(
            "TLabel",
            background=self.colors["bg_dark"],
            foreground=self.colors["text_primary"],
            font=("Segoe UI", 10)
        )
        style.configure(
            "Title.TLabel",
            font=("Segoe UI", 16, "bold"),
            foreground=self.colors["accent_primary"]
        )
        style.configure(
            "Subtitle.TLabel",
            font=("Segoe UI", 11, "bold"),
            foreground=self.colors["accent_secondary"]
        )
        style.configure(
            "Small.TLabel",
            font=("Segoe UI", 8),
            foreground=self.colors["text_secondary"]
        )

        # LabelFrame styles
        style.configure(
            "TLabelframe",
            background=self.colors["bg_medium"],
            borderwidth=2,
            relief="solid"
        )
        style.configure(
            "TLabelframe.Label",
            background=self.colors["bg_medium"],
            foreground=self.colors["accent_primary"],
            font=("Segoe UI", 10, "bold")
        )

        self.setup_ui()
        self.update_ui()

    def setup_ui(self):
        # Main container
        main_container = ttk.Frame(self.root, padding="10")
        main_container.pack(fill=tk.BOTH, expand=True)

        # Create two-column layout
        content_frame = ttk.Frame(main_container)
        content_frame.pack(fill=tk.BOTH, expand=True)

        # LEFT COLUMN - Garden Visualization
        left_column = ttk.Frame(content_frame)
        left_column.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 15))

        # Connection & Player Info Panel (consolidated)
        info_frame = ttk.LabelFrame(left_column, text="👤 Player & Connection", padding="12")
        info_frame.pack(fill=tk.X, pady=(0, 10))

        self.player_id_var = tk.StringVar(value="Unknown")
        self.player_name_var = tk.StringVar(value="Unknown")
        self.stats_room_id = tk.StringVar(value="Unknown")
        self.stats_player_count = tk.StringVar(value="0/6")
        self.stats_ping = tk.StringVar(value="0")
        self.stats_pong = tk.StringVar(value="0")
        self.stats_messages_sent = tk.StringVar(value="0")
        self.stats_messages_received = tk.StringVar(value="0")
        self.stats_patches_applied = tk.StringVar(value="0")
        self.stats_last_update = tk.StringVar(value="Never")

        # Row 0: Player info
        ttk.Label(info_frame, text="Player:", font=("Segoe UI", 9, "bold"),
                 foreground=self.colors["accent_secondary"]).grid(
            row=0, column=0, sticky=tk.W, padx=(0, 8), pady=3
        )
        ttk.Label(info_frame, textvariable=self.player_name_var, font=("Segoe UI", 9)).grid(
            row=0, column=1, sticky=tk.W, pady=3
        )

        ttk.Label(info_frame, text="ID:", font=("Segoe UI", 9, "bold"),
                 foreground=self.colors["accent_secondary"]).grid(
            row=0, column=2, sticky=tk.W, padx=(20, 8), pady=3
        )
        ttk.Label(info_frame, textvariable=self.player_id_var, font=("Segoe UI", 9)).grid(
            row=0, column=3, sticky=tk.W, pady=3
        )

        # Row 1: Room info
        ttk.Label(info_frame, text="Room:", font=("Segoe UI", 9, "bold"),
                 foreground=self.colors["accent_secondary"]).grid(
            row=1, column=0, sticky=tk.W, padx=(0, 8), pady=3
        )
        ttk.Label(info_frame, textvariable=self.stats_room_id, font=("Segoe UI", 9)).grid(
            row=1, column=1, sticky=tk.W, pady=3
        )

        ttk.Label(info_frame, text="Players:", font=("Segoe UI", 9, "bold"),
                 foreground=self.colors["accent_secondary"]).grid(
            row=1, column=2, sticky=tk.W, padx=(20, 8), pady=3
        )
        ttk.Label(info_frame, textvariable=self.stats_player_count, font=("Segoe UI", 9)).grid(
            row=1, column=3, sticky=tk.W, pady=3
        )

        # Row 2: Network stats
        ttk.Label(info_frame, text="Ping/Pong:", font=("Segoe UI", 9, "bold"),
                 foreground=self.colors["accent_secondary"]).grid(
            row=2, column=0, sticky=tk.W, padx=(0, 8), pady=3
        )
        ttk.Label(info_frame, textvariable=self.stats_ping, font=("Segoe UI", 9)).grid(
            row=2, column=1, sticky=tk.W, pady=3
        )

        ttk.Label(info_frame, text="Messages:", font=("Segoe UI", 9, "bold"),
                 foreground=self.colors["accent_secondary"]).grid(
            row=2, column=2, sticky=tk.W, padx=(20, 8), pady=3
        )
        ttk.Label(info_frame, textvariable=self.stats_messages_sent, font=("Segoe UI", 9)).grid(
            row=2, column=3, sticky=tk.W, pady=3
        )

        # Row 3: Updates
        ttk.Label(info_frame, text="Patches:", font=("Segoe UI", 9, "bold"),
                 foreground=self.colors["accent_secondary"]).grid(
            row=3, column=0, sticky=tk.W, padx=(0, 8), pady=3
        )
        ttk.Label(info_frame, textvariable=self.stats_patches_applied, font=("Segoe UI", 9)).grid(
            row=3, column=1, sticky=tk.W, pady=3
        )

        ttk.Label(info_frame, text="Last Update:", font=("Segoe UI", 9, "bold"),
                 foreground=self.colors["accent_secondary"]).grid(
            row=3, column=2, sticky=tk.W, padx=(20, 8), pady=3
        )
        ttk.Label(info_frame, textvariable=self.stats_last_update, font=("Segoe UI", 9)).grid(
            row=3, column=3, sticky=tk.W, pady=3
        )

        # Garden Canvas with legend inside
        garden_frame = ttk.LabelFrame(left_column, text="🌻 Garden View", padding="0")
        garden_frame.pack(fill=tk.X, expand=False, pady=(0, 10))

        # Canvas sized EXACTLY for 12 rows x 23 cols grid
        # 28 pixels per tile + 4 for labelframe border (2 on each side)
        self.garden_canvas = tk.Canvas(
            garden_frame,
            width=23 * 28 + 4,  # 648 - exactly 23 cols + borders
            height=12 * 28 + 4,  # 340 - exactly 12 rows + borders
            bg=self.colors["canvas_bg"],
            highlightthickness=0,
        )
        self.garden_canvas.pack()

        # Create a canvas for the legend - INSIDE garden_frame
        self.legend_canvas = tk.Canvas(
            garden_frame,
            height=30,
            width=23 * 28 + 4,
            bg=self.colors["bg_medium"],
            highlightthickness=0,
        )
        self.legend_canvas.pack()

        # Console Log
        log_frame = ttk.LabelFrame(left_column, text="📜 Console Log", padding="12")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 0))

        self.console_log = scrolledtext.ScrolledText(
            log_frame,
            height=10,
            width=50,
            bg=self.colors["bg_light"],
            fg=self.colors["text_primary"],
            font=("Consolas", 8),
            wrap=tk.WORD,
            insertbackground=self.colors["accent_primary"],
            selectbackground=self.colors["accent_primary"],
            selectforeground=self.colors["text_primary"],
        )
        self.console_log.pack(fill=tk.BOTH, expand=True)

        # Redirect stdout to console log
        sys.stdout = ConsoleRedirector(self.console_log, sys.stdout)

        # RIGHT COLUMN - Text Info
        right_column = ttk.Frame(content_frame)
        right_column.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Pet State
        pet_frame = ttk.LabelFrame(right_column, text="🐾 Pet State", padding="12")
        pet_frame.pack(fill=tk.BOTH, expand=False, pady=(0, 10))

        self.pet_text = scrolledtext.ScrolledText(
            pet_frame,
            height=12,
            width=50,
            bg=self.colors["bg_light"],
            fg=self.colors["text_primary"],
            font=("Consolas", 9),
            wrap=tk.WORD,
            insertbackground=self.colors["accent_primary"],
            selectbackground=self.colors["accent_primary"],
            selectforeground=self.colors["text_primary"],
        )
        self.pet_text.pack(fill=tk.BOTH, expand=True)

        # Inventory
        inv_frame = ttk.LabelFrame(right_column, text="🎒 Inventory", padding="12")
        inv_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.inventory_text = scrolledtext.ScrolledText(
            inv_frame,
            height=15,
            width=50,
            bg=self.colors["bg_light"],
            fg=self.colors["text_primary"],
            font=("Consolas", 9),
            wrap=tk.WORD,
            insertbackground=self.colors["accent_primary"],
            selectbackground=self.colors["accent_primary"],
            selectforeground=self.colors["text_primary"],
        )
        self.inventory_text.pack(fill=tk.BOTH, expand=True)

        # Game Stats (separate box)
        game_stats_frame = ttk.LabelFrame(
            right_column, text="📊 Game Stats", padding="12"
        )
        game_stats_frame.pack(fill=tk.X, pady=(0, 0))

        self.game_stats_text = scrolledtext.ScrolledText(
            game_stats_frame,
            height=7,
            width=50,
            bg=self.colors["bg_light"],
            fg=self.colors["text_primary"],
            font=("Consolas", 9),
            wrap=tk.WORD,
            insertbackground=self.colors["accent_primary"],
            selectbackground=self.colors["accent_primary"],
            selectforeground=self.colors["text_primary"],
        )
        self.game_stats_text.pack(fill=tk.BOTH, expand=True)

    def draw_legend(self):
        """Draw the color legend with actual matching colors"""
        self.legend_canvas.delete("all")

        # Legend items with vibrant colors
        legend_items = [
            ("#00d4ff", "You"),
            ("#00e676", "Ready"),
            ("#ff9100", "Grown"),
            ("#ffd93d", "Growing"),
            ("#69f0ae", "Ready Egg"),
            ("#ffeb3b", "Growing Egg"),
            ("#d946ef", "Pet"),
            ("#4a4a5e", "Empty"),
        ]

        x_pos = 10
        y_center = 15
        for color, label in legend_items:
            # Draw color square with rounded effect
            self.legend_canvas.create_rectangle(
                x_pos, y_center - 6, x_pos + 14, y_center + 6,
                fill=color, outline=self.colors["accent_primary"], width=1
            )
            # Draw label with new font
            self.legend_canvas.create_text(
                x_pos + 18, y_center, text=label,
                fill=self.colors["text_primary"],
                font=("Segoe UI", 8), anchor="w"
            )
            x_pos += 84

    def log_to_console(self, message):
        """Add a message to the console log widget"""
        self.console_log.insert(tk.END, message + "\n")
        self.console_log.see(tk.END)  # Auto-scroll to bottom

    def extract_player_data(self):
        """Extract player data from full_state"""
        with game_state_lock:
            if not game_state["full_state"]:
                return None

            our_player_id = game_state["player_id"]
            full_state = game_state["full_state"]

            # Navigate to Quinoa game state
            if "child" not in full_state or full_state["child"].get("scope") != "Quinoa":
                return None

            quinoa_state = full_state["child"].get("data", {})
            user_slots = quinoa_state.get("userSlots", [])

            # Find our player's slot and make a deep copy to avoid race conditions
            for slot in user_slots:
                if slot and slot.get("playerId") == our_player_id:
                    return deepcopy(slot)

            return None

    def render_garden_state(self, player_slot):
        """Render the garden grid with actual tile objects"""

        slot_data = player_slot.get("data", {})
        # Clear canvas
        self.garden_canvas.delete("all")

        # Canvas dimensions
        canvas_width = 650
        canvas_height = 400

        # Get garden data
        garden_data = slot_data.get("garden", {})
        tile_objects = garden_data.get("tileObjects", {})

        # Garden is 10 rows x 20 columns (200 tiles total: 0-199)
        # But visually it's two 10×10 sections with boardwalk paths
        garden_rows = 10
        garden_cols = 20

        # Visual grid includes boardwalk paths
        # +1 top border, +1 bottom border, +1 middle path
        visual_rows = garden_rows + 2  # 12 total
        # +1 left border, +1 middle path, +1 right border
        visual_cols = garden_cols + 3  # 23 total

        # Calculate tile size to fill entire canvas
        tile_size_width = canvas_width // visual_cols
        tile_size_height = canvas_height // visual_rows

        # Use the smaller dimension to ensure grid fits entirely
        tile_size = min(tile_size_width, tile_size_height)

        # Draw background
        self.garden_canvas.create_rectangle(
            0, 0, canvas_width, canvas_height, fill=self.colors["canvas_bg"], outline=""
        )

        # Stats
        total_tiles = len(tile_objects)
        growing_count = 0
        mature_count = 0
        empty_count = 0
        import time

        current_time = int(time.time() * 1000)

        for tile_id, tile_obj in tile_objects.items():
            if tile_obj and tile_obj.get("objectType") == "plant":
                slots = tile_obj.get("slots", [])
                if slots:
                    slot = slots[0]
                    end_time = slot.get("endTime", 0)
                    if current_time >= end_time:
                        mature_count += 1
                    else:
                        growing_count += 1

        empty_count = 200 - total_tiles

        # Position the grid - offset by labelframe border width
        border_offset = 2
        start_x = border_offset
        start_y = border_offset

        # Get player position from server state
        player_server_pos = player_slot.get("position")
        player_x = -1  # Default to invalid if no position
        player_y = -1

        if isinstance(player_server_pos, dict):
            server_x = player_server_pos.get("x")
            server_y = player_server_pos.get("y")
            if server_x is not None and server_y is not None:
                # Convert server position to local coordinates
                local_coords = convert_server_to_local_coords(server_x, server_y)
                if local_coords:
                    player_x = local_coords.get("x", -1)
                    player_y = local_coords.get("y", -1)

        # Helper: Convert garden tile ID to visual position
        def garden_tile_to_visual(tile_id):
            """Convert garden tile (0-199) to visual grid position"""
            row = tile_id // garden_cols
            col = tile_id % garden_cols

            # Add 1 for top border
            visual_row = row + 1

            # Left section (cols 0-9): add 1 for left border
            # Right section (cols 10-19): add 2 for left border + middle path
            if col < 10:
                visual_col = col + 1
            else:
                visual_col = col + 2

            return visual_row, visual_col

        def garden_coord_to_visual(coord_x, coord_y):
            """Convert local garden coordinates to the visual grid."""
            if coord_x is None or coord_y is None:
                return None

            visual_row = coord_y + 1
            if coord_x < 10:
                visual_col = coord_x + 1
            else:
                visual_col = coord_x + 2

            if (
                visual_row < 0
                or visual_row >= visual_rows
                or visual_col < 0
                or visual_col >= visual_cols
            ):
                return None

            return visual_row, visual_col

        # Draw visual grid
        for row in range(visual_rows):
            for col in range(visual_cols):
                x = start_x + col * tile_size
                y = start_y + row * tile_size

                # Initialize variables for all tiles
                tile_obj = None
                obj_type = None
                slots = None

                # Determine if this is a boardwalk path
                is_boardwalk = (
                    row == 0
                    or row == visual_rows - 1  # Top/bottom border
                    or col == 0
                    or col == visual_cols - 1  # Left/right border
                    or col == 11  # Middle path (between two 10×10 sections)
                )

                if is_boardwalk:
                    # Boardwalk path - warmer brown/tan color
                    fill_color = "#a0826d"
                    outline_color = "#b8956f"
                else:
                    # Default empty garden tile - dark purple-gray
                    fill_color = "#4a4a5e"
                    outline_color = "#5a5a6e"

                    # Check if there's a garden tile at this visual position
                    for tid, obj in tile_objects.items():
                        if tid.isdigit():
                            obj_row, obj_col = garden_tile_to_visual(int(tid))
                            if obj_row == row and obj_col == col:
                                tile_obj = obj
                                break

                    # Render garden tile if present
                    if tile_obj:
                        obj_type = tile_obj.get("objectType")

                        if obj_type == "plant":
                            slots = tile_obj.get("slots", [])
                            if slots:
                                slot = slots[0]
                                end_time = slot.get("endTime", 0)
                                species = slot.get("species", "?")
                                mutations = slot.get("mutations", [])
                                mutation_count = len(mutations)

                                # Get min mutations required for harvest
                                min_mutations = 3
                                if harvest_config:
                                    min_mutations = harvest_config.get(
                                        "min_mutations", 3
                                    )

                                # Check if mature
                                if current_time >= end_time:
                                    # Mature - check mutations
                                    if mutation_count >= min_mutations:
                                        # Ready to harvest - vibrant bright green
                                        fill_color = "#00e676"
                                        outline_color = "#1fec84"
                                    else:
                                        # Grown but not fully mutated - vibrant orange
                                        fill_color = "#ff9100"
                                        outline_color = "#ffa726"
                                else:
                                    # Growing - golden yellow
                                    fill_color = "#ffd93d"
                                    outline_color = "#ffe066"
                            else:
                                # Empty plant slot
                                fill_color = "#5a5a6e"
                                outline_color = "#6a6a7e"
                        elif obj_type == "egg":
                            # Egg - check if mature
                            matured_at = tile_obj.get("maturedAt", 0)
                            if current_time >= matured_at:
                                # Mature egg (ready) - bright mint green
                                fill_color = "#69f0ae"
                                outline_color = "#7ff5bb"
                            else:
                                # Growing egg - bright yellow
                                fill_color = "#ffeb3b"
                                outline_color = "#fff176"
                        elif obj_type == "pet":
                            # Pet on tile - vibrant magenta/purple
                            fill_color = "#d946ef"
                            outline_color = "#e469f2"
                        elif obj_type == "decor":
                            # Decoration - blue/gray
                            fill_color = "#607D8B"
                            outline_color = "#78909C"
                        else:
                            # Unknown object
                            fill_color = "#666666"
                            outline_color = "#888888"

                # Draw tile
                self.garden_canvas.create_rectangle(
                    x,
                    y,
                    x + tile_size - 1,
                    y + tile_size - 1,
                    fill=fill_color,
                    outline=outline_color,
                    width=1,
                )

                # Draw mutation indicators for plants
                if tile_obj and obj_type == "plant" and slots:
                    slot = slots[0]
                    mutations = slot.get("mutations", [])

                    # Check for Rainbow mutation
                    if "Rainbow" in mutations:
                        # Draw rainbow gradient indicator in top-right corner
                        indicator_size = max(tile_size // 4, 3)
                        indicator_x = x + tile_size - indicator_size - 2
                        indicator_y = y + 2

                        # Create a small rainbow effect with multiple colored stripes
                        rainbow_colors = ["#ff0000", "#ff7f00", "#ffff00", "#00ff00", "#0000ff", "#4b0082"]
                        stripe_height = max(indicator_size // len(rainbow_colors), 1)

                        for i, color in enumerate(rainbow_colors):
                            self.garden_canvas.create_rectangle(
                                indicator_x,
                                indicator_y + i * stripe_height,
                                indicator_x + indicator_size,
                                indicator_y + (i + 1) * stripe_height,
                                fill=color,
                                outline="",
                            )

                    # Check for Gold mutation
                    if "Gold" in mutations:
                        # Draw gold star/diamond indicator
                        indicator_size = max(tile_size // 4, 3)
                        # Position in top-left if Rainbow is present, otherwise top-right
                        if "Rainbow" in mutations:
                            indicator_x = x + 2
                        else:
                            indicator_x = x + tile_size - indicator_size - 2
                        indicator_y = y + 2

                        # Draw a gold circle/oval
                        self.garden_canvas.create_oval(
                            indicator_x,
                            indicator_y,
                            indicator_x + indicator_size,
                            indicator_y + indicator_size,
                            fill="#ffd700",
                            outline="#ffed4e",
                            width=1,
                        )

                    # Check for Wet/Chilled/Frozen states (left side indicator)
                    water_state = None
                    water_color = None
                    if "Frozen" in mutations:
                        water_state = "Frozen"
                        water_color = "#E1F5FE"  # Ice blue/white
                    elif "Chilled" in mutations:
                        water_state = "Chilled"
                        water_color = "#00BCD4"  # Cyan
                    elif "Wet" in mutations:
                        water_state = "Wet"
                        water_color = "#2196F3"  # Blue

                    if water_state:
                        indicator_size = max(tile_size // 4, 3)
                        indicator_x = x + 2
                        indicator_y = y + tile_size // 2 - indicator_size // 2

                        # Draw water/ice state indicator
                        self.garden_canvas.create_oval(
                            indicator_x,
                            indicator_y,
                            indicator_x + indicator_size,
                            indicator_y + indicator_size,
                            fill=water_color,
                            outline="#FFFFFF",
                            width=1,
                        )

                    # Check for Dawnlit/Amberlit states (bottom indicator)
                    light_state = None
                    light_color = None
                    if "Amberlit" in mutations:
                        light_state = "Amberlit"
                        light_color = "#FFAB00"  # Amber/golden
                    elif "Dawnlit" in mutations:
                        light_state = "Dawnlit"
                        light_color = "#FF6090"  # Dawn pink

                    if light_state:
                        indicator_size = max(tile_size // 4, 3)
                        indicator_x = x + tile_size // 2 - indicator_size // 2
                        indicator_y = y + tile_size - indicator_size - 2

                        # Draw light state indicator
                        self.garden_canvas.create_oval(
                            indicator_x,
                            indicator_y,
                            indicator_x + indicator_size,
                            indicator_y + indicator_size,
                            fill=light_color,
                            outline="#FFFFFF",
                            width=1,
                        )

        # Draw pets using current petSlotInfos positions
        pet_slot_infos = player_slot.get("petSlotInfos")
        if isinstance(pet_slot_infos, dict):
            for pet_id, slot_info in pet_slot_infos.items():
                if not isinstance(slot_info, dict):
                    continue

                position = slot_info.get("position")
                if not isinstance(position, dict):
                    continue

                local_coords = convert_server_to_local_coords(
                    position.get("x"), position.get("y")
                )
                if not local_coords:
                    continue

                # Local coords map 1:1 to visual grid (0-22 for x, 0-11 for y)
                local_x = local_coords.get("x")
                local_y = local_coords.get("y")

                # Bounds check
                if local_x < 0 or local_x > 22 or local_y < 0 or local_y > 11:
                    continue

                pet_pixel_x = start_x + local_x * tile_size
                pet_pixel_y = start_y + local_y * tile_size

                center_x = pet_pixel_x + tile_size // 2
                center_y = pet_pixel_y + tile_size // 2
                radius = max(tile_size // 3, 4)

                self.garden_canvas.create_oval(
                    center_x - radius,
                    center_y - radius,
                    center_x + radius,
                    center_y + radius,
                    fill="#d946ef",
                    outline="#e980f5",
                    width=2,
                )

        # Draw player marker using local coordinates
        # Convert local coordinates (0-22, 0-11) to visual grid for rendering
        if player_x >= 0 and player_y >= 0:
            # Player is in local coordinates, render directly on visual grid
            # Local coords map 1:1 to visual grid (both are 0-22 for x, 0-11 for y)
            player_pixel_x = start_x + player_x * tile_size
            player_pixel_y = start_y + player_y * tile_size

            # Draw bright cyan circle for player
            center_x = player_pixel_x + tile_size // 2
            center_y = player_pixel_y + tile_size // 2
            radius = max(tile_size // 3, 4)
            self.garden_canvas.create_oval(
                center_x - radius,
                center_y - radius,
                center_x + radius,
                center_y + radius,
                fill="#00d4ff",
                outline="#33ddff",
                width=2,
            )

    def render_pet_state(self, slot_data):
        """Render the pet state in its own box"""
        # Save scroll position
        scroll_pos = self.pet_text.yview()
        self.pet_text.delete("1.0", tk.END)

        # Parse active pet slots
        pet_slots = slot_data.get("petSlots", [])
        active_pets = []
        for pet_slot in pet_slots:
            if pet_slot:
                active_pet = {
                    "id": pet_slot.get("id"),
                    "species": pet_slot.get("petSpecies"),
                    "name": pet_slot.get("name"),
                    "xp": pet_slot.get("xp", 0),
                    "hunger": pet_slot.get("hunger", 0),
                    "mutations": pet_slot.get("mutations", []),
                    "scale": pet_slot.get("targetScale", 1.0),
                    "abilities": pet_slot.get("abilities", []),
                }
                active_pets.append(active_pet)

        # Parse inventory items for pets
        inv_data = slot_data.get("inventory", {})
        items_list = inv_data.get("items", [])

        pets = []
        for item in items_list:
            if item.get("itemType") == "Pet":
                pet_info = {
                    "id": item.get("id"),
                    "species": item.get("petSpecies"),
                    "name": item.get("name"),
                    "xp": item.get("xp", 0),
                    "hunger": item.get("hunger", 0),
                    "mutations": item.get("mutations", []),
                    "scale": item.get("targetScale", 1.0),
                    "abilities": item.get("abilities", []),
                }
                pets.append(pet_info)

        # Active Pets
        if active_pets:
            self.pet_text.insert("1.0", f"Active Pets ({len(active_pets)}):\n")
            for pet in active_pets:
                species = pet.get("species", "Unknown")
                xp = pet.get("xp", 0)
                hunger = pet.get("hunger", 0)
                abilities = pet.get("abilities", [])
                mutations = pet.get("mutations", [])

                self.pet_text.insert(tk.END, f"  • {species}")
                if mutations:
                    self.pet_text.insert(tk.END, f" [{', '.join(mutations)}]")
                self.pet_text.insert(
                    tk.END, f"\n    XP: {xp:,} | Hunger: {hunger:.0f}\n"
                )
                if abilities:
                    self.pet_text.insert(
                        tk.END, f"    Abilities: {', '.join(abilities)}\n"
                    )
            self.pet_text.insert(tk.END, "\n")
        else:
            self.pet_text.insert("1.0", "Active Pets: None\n\n")

        # Inventory Pets
        if pets:
            self.pet_text.insert(tk.END, f"Pets in Inventory ({len(pets)}):\n")
            # Show top 10 pets
            for i, pet in enumerate(pets[:10]):
                species = pet.get("species", "Unknown")
                xp = pet.get("xp", 0)
                abilities = pet.get("abilities", [])
                mutations = pet.get("mutations", [])

                ability_str = ", ".join(abilities[:2]) if abilities else "None"
                mutation_str = f" [{', '.join(mutations)}]" if mutations else ""

                self.pet_text.insert(
                    tk.END,
                    f"  {i+1:2d}. {species}{mutation_str} (XP: {xp:,}) - {ability_str}\n",
                )
            if len(pets) > 10:
                self.pet_text.insert(
                    tk.END, f"\n  ... and {len(pets) - 10} more pets\n"
                )
        else:
            self.pet_text.insert(tk.END, "Pets in Inventory: None\n")

        # Restore scroll position
        self.pet_text.yview_moveto(scroll_pos[0])

    def update_ui(self):
        """Update UI with current game state"""
        # Player info
        self.player_id_var.set(game_state["player_id"] or "Unknown")
        self.player_name_var.set(game_state["player_name"] or "Unknown")

        # Extract player data from full_state
        player_slot = self.extract_player_data()

        if not player_slot:
            self.inventory_text.delete("1.0", tk.END)
            self.inventory_text.insert("1.0", "Waiting for game state...\n")
            self.garden_canvas.delete("all")
            self.garden_canvas.create_text(
                330,
                205,
                text="Waiting for game state...",
                fill=self.colors["text_secondary"],
                font=("Segoe UI", 14),
            )
            self.pet_text.delete("1.0", tk.END)
            self.pet_text.insert("1.0", "Waiting for game state...\n")
            self.root.after(500, self.update_ui)
            return

        slot_data = player_slot.get("data", {})

        # Draw legend
        self.draw_legend()

        # Render garden state
        self.render_garden_state(player_slot)

        # Render pet state
        self.render_pet_state(slot_data)

        # Save current scroll position for inventory
        scroll_pos = self.inventory_text.yview()
        self.inventory_text.delete("1.0", tk.END)

        # Coins
        coins = slot_data.get("coinsCount", 0)
        coins_formatted = f"{coins:,}"
        self.inventory_text.insert("1.0", f"💰 Coins: {coins_formatted}\n\n")

        # Parse inventory items
        inv_data = slot_data.get("inventory", {})
        items_list = inv_data.get("items", [])

        seeds = {}
        tools = {}
        eggs = {}
        produce = []

        for item in items_list:
            item_type = item.get("itemType")
            quantity = item.get("quantity", 0)

            if item_type == "Seed" and "species" in item:
                seeds[item["species"]] = quantity
            elif item_type == "Tool" and "toolId" in item:
                tools[item["toolId"]] = quantity
            elif item_type == "Egg" and "eggId" in item:
                eggs[item["eggId"]] = quantity
            elif item_type == "Produce":
                produce_info = {
                    "id": item.get("id"),
                    "species": item.get("species"),
                    "scale": item.get("scale", 1.0),
                    "mutations": item.get("mutations", []),
                }
                produce.append(produce_info)

        # Format inventory in two columns
        # Seeds
        if seeds:
            self.inventory_text.insert(tk.END, "🌱 Seeds:\n")
            sorted_seeds = sorted(seeds.items())
            # Split into two columns
            mid = (len(sorted_seeds) + 1) // 2
            col1 = sorted_seeds[:mid]
            col2 = sorted_seeds[mid:]

            for i in range(max(len(col1), len(col2))):
                line = ""
                if i < len(col1):
                    seed_type, count = col1[i]
                    line += f"  {seed_type:<20} {count:>5}"
                else:
                    line += " " * 27

                if i < len(col2):
                    seed_type, count = col2[i]
                    line += f"    {seed_type:<20} {count:>5}"

                self.inventory_text.insert(tk.END, line + "\n")
            self.inventory_text.insert(tk.END, "\n")
        else:
            self.inventory_text.insert(tk.END, "🌱 Seeds: None\n\n")

        # Tools
        if tools:
            self.inventory_text.insert(tk.END, "🔧 Tools:\n")
            sorted_tools = sorted(tools.items())
            # Split into two columns
            mid = (len(sorted_tools) + 1) // 2
            col1 = sorted_tools[:mid]
            col2 = sorted_tools[mid:]

            for i in range(max(len(col1), len(col2))):
                line = ""
                if i < len(col1):
                    tool_type, count = col1[i]
                    line += f"  {tool_type:<20} {count:>5}"
                else:
                    line += " " * 27

                if i < len(col2):
                    tool_type, count = col2[i]
                    line += f"    {tool_type:<20} {count:>5}"

                self.inventory_text.insert(tk.END, line + "\n")
            self.inventory_text.insert(tk.END, "\n")
        else:
            self.inventory_text.insert(tk.END, "🔧 Tools: None\n\n")

        # Eggs
        if eggs:
            self.inventory_text.insert(tk.END, "🥚 Eggs:\n")
            sorted_eggs = sorted(eggs.items())
            # Split into two columns
            mid = (len(sorted_eggs) + 1) // 2
            col1 = sorted_eggs[:mid]
            col2 = sorted_eggs[mid:]

            for i in range(max(len(col1), len(col2))):
                line = ""
                if i < len(col1):
                    egg_type, count = col1[i]
                    line += f"  {egg_type:<20} {count:>5}"
                else:
                    line += " " * 27

                if i < len(col2):
                    egg_type, count = col2[i]
                    line += f"    {egg_type:<20} {count:>5}"

                self.inventory_text.insert(tk.END, line + "\n")
            self.inventory_text.insert(tk.END, "\n")
        else:
            self.inventory_text.insert(tk.END, "🥚 Eggs: None\n\n")

        # Produce
        if produce:
            self.inventory_text.insert(tk.END, f"🌾 Produce: {len(produce)} items\n")
            # Count by species
            produce_count = {}
            for item in produce:
                species = item.get("species", "Unknown")
                produce_count[species] = produce_count.get(species, 0) + 1

            sorted_produce = sorted(produce_count.items())
            # Split into two columns
            mid = (len(sorted_produce) + 1) // 2
            col1 = sorted_produce[:mid]
            col2 = sorted_produce[mid:]

            for i in range(max(len(col1), len(col2))):
                line = ""
                if i < len(col1):
                    species, count = col1[i]
                    line += f"  {species:<20} {count:>5}"
                else:
                    line += " " * 27

                if i < len(col2):
                    species, count = col2[i]
                    line += f"    {species:<20} {count:>5}"

                self.inventory_text.insert(tk.END, line + "\n")
            self.inventory_text.insert(tk.END, "\n")

        # Restore scroll position
        self.inventory_text.yview_moveto(scroll_pos[0])

        # Update Game Stats in separate box
        self.game_stats_text.delete("1.0", tk.END)
        stats = slot_data.get("stats", {})
        player_stats_data = stats.get("player", {})
        self.game_stats_text.insert(
            "1.0",
            f"  Crops Harvested: {player_stats_data.get('numCropsHarvested', 0):,}\n",
        )
        self.game_stats_text.insert(
            tk.END,
            f"  Seeds Planted: {player_stats_data.get('numSeedsPlanted', 0):,}\n",
        )
        self.game_stats_text.insert(
            tk.END, f"  Pets Sold: {player_stats_data.get('numPetsSold', 0):,}\n"
        )
        self.game_stats_text.insert(
            tk.END, f"  Eggs Hatched: {player_stats_data.get('numEggsHatched', 0):,}\n"
        )
        total_earnings = player_stats_data.get(
            "totalEarningsSellCrops", 0
        ) + player_stats_data.get("totalEarningsSellPet", 0)
        self.game_stats_text.insert(
            tk.END, f"  Total Earnings: {total_earnings:,} coins\n"
        )

        # Update statistics using StringVars
        stats = game_state["statistics"]
        sent = stats["messages_sent"]
        received = stats["messages_received"]
        self.stats_messages_sent.set(f"↑{sent:,} / ↓{received:,}")

        # Combine ping/pong into one stat
        pings = stats["pings_sent"]
        pongs = stats["pongs_received"]
        self.stats_ping.set(f"↑{pings:,} / ↓{pongs:,}")

        self.stats_patches_applied.set(f"{stats['patches_applied']:,}")
        self.stats_last_update.set(stats["last_update"])

        # Update room info
        room_id = game_state.get("room_id", "Unknown")
        self.stats_room_id.set(room_id)

        # Get player count from full_state
        player_count = 0
        with game_state_lock:
            if game_state["full_state"]:
                room_data = game_state["full_state"].get("data", {})
                players = room_data.get("players", [])
                # Count non-None players
                player_count = sum(1 for p in players if p is not None)
        self.stats_player_count.set(f"{player_count}/6")

        # Schedule next update
        self.root.after(500, self.update_ui)


# WebSocket functions
def log_message_to_file(direction, message, timestamp=None):
    """Log all messages to file"""
    if timestamp is None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    try:
        with open(MESSAGE_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"[{timestamp}] {direction}\n")
            f.write(f"{'='*80}\n")
            if isinstance(message, str):
                parsed = json.loads(message)
                f.write(json.dumps(parsed, indent=2))
            else:
                f.write(json.dumps(message, indent=2))
            f.write("\n")
    except:
        pass


def generate_id(alphabet, length):
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_player_id():
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    return "p_" + generate_id(alphabet, 16)


def load_user_config():
    """Load single user configuration"""
    global harvest_config, shop_config

    config = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
        except Exception:
            config = {}

    config_dirty = False

    player_id = config.get("playerId")
    if not player_id:
        player_id = generate_player_id()
        config["playerId"] = player_id
        config_dirty = True

    ready_config = config.get("ready_to_harvest")
    if isinstance(ready_config, dict):
        harvest_config = ready_config
    else:
        harvest_config = {"min_mutations": 3}
        config["ready_to_harvest"] = harvest_config
        config_dirty = True

    normalized_shop = normalize_shop_config(config.get("shop"))
    if normalized_shop != config.get("shop"):
        config["shop"] = normalized_shop
        config_dirty = True
    shop_config = normalized_shop
    print(f"Loaded shop config: Auto-buy enabled = {shop_config.get('enabled', False)}")

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

    last_room = config.get("lastRoom")

    if config_dirty:
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=2)
        except Exception:
            pass

    if missing_cookie_error:
        raise RuntimeError(missing_cookie_error)

    return {"playerId": player_id, "cookies": cookies, "lastRoom": last_room}


def save_last_room(room_id):
    """Save the last connected room to config"""
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


def save_cookies(cookies):
    """Persist the latest cookie string to the config"""
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


async def authenticate_user(cookies, room_id="MG1"):
    auth_url = f"https://magicgarden.gg/version/cb622cd/api/rooms/{room_id}/user/authenticate-web"
    headers = {
        "accept": "*/*",
        "content-type": "application/json",
        "origin": "https://magicgarden.gg",
        "referer": f"https://magicgarden.gg/r/{room_id}",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "cookie": cookies,
    }
    payload = {"provider": "maybe-existing-jwt"}

    async with aiohttp.ClientSession() as session:
        async with session.post(auth_url, json=payload, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                updated_cookies = cookies
                if "Set-Cookie" in response.headers:
                    set_cookie = response.headers.get("Set-Cookie")
                    new_cookie = set_cookie.split(";")[0]
                    cookie_dict = {}
                    for cookie_pair in cookies.split("; "):
                        if "=" in cookie_pair:
                            name, value = cookie_pair.split("=", 1)
                            cookie_dict[name] = value
                    if "=" in new_cookie:
                        name, value = new_cookie.split("=", 1)
                        cookie_dict[name] = value
                    updated_cookies = "; ".join(
                        [f"{k}={v}" for k, v in cookie_dict.items()]
                    )

                if data.get("isAuthenticated"):
                    return data, updated_cookies
            return None, None


def process_welcome_message(data):
    """Store fullState from Welcome message and set random spawn position"""
    log_message_to_file("RECEIVED (Welcome)", data)

    print("\n" + "=" * 60)
    print("PROCESSING WELCOME MESSAGE")
    print("=" * 60)

    our_player_id = game_state["player_id"]
    print(f"Looking for player: {our_player_id}")

    # Navigate to Quinoa game state
    if "fullState" not in data:
        print("ERROR: No fullState in welcome message")
        return None

    full_state = data["fullState"]

    # Store the entire fullState
    with game_state_lock:
        game_state["full_state"] = deepcopy(full_state)

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

            # Store our player's name and slot index
            if player_id == our_player_id:
                game_state["player_name"] = player_name
                game_state["user_slot_index"] = slot_idx
                print(f"  → We are in slot {slot_idx}")

    # Get spawn position for our detected slot
    if game_state["user_slot_index"] is not None:
        server_spawn_pos = SPAWN_POSITIONS[game_state["user_slot_index"]].copy()
        print(f"\nUsing spawn position for slot {game_state['user_slot_index']}")
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
    print(f"Player: {game_state['player_name'] or game_state['player_id']}")
    print("=" * 60 + "\n")

    game_state["statistics"]["last_update"] = datetime.now().strftime("%H:%M:%S")

    # Return the server spawn position
    return server_spawn_pos


def process_partial_state_message(data):
    """Process PartialState messages by applying JSON patches"""
    log_message_to_file("RECEIVED (PartialState)", data)

    with game_state_lock:
        if not game_state["full_state"]:
            print("WARNING: Received PartialState before Welcome message")
            return

        if "patches" not in data:
            print("WARNING: PartialState message has no patches")
            return

        patches = data["patches"]

        # Apply each patch to the fullState
        for patch in patches:
            try:
                apply_json_patch(game_state["full_state"], patch)
                game_state["statistics"]["patches_applied"] += 1
            except Exception as e:
                print(f"ERROR applying patch: {e}")
                print(f"Patch: {patch}")

        game_state["statistics"]["last_update"] = datetime.now().strftime("%H:%M:%S")


def process_message(message):
    try:
        game_state["statistics"]["messages_received"] += 1
        data = json.loads(message)
        msg_type = data.get("type")

        if msg_type == "Welcome":
            process_welcome_message(data)
        elif msg_type == "PartialState":
            process_partial_state_message(data)
        elif msg_type == "Ping":
            game_state["statistics"]["pings_received"] += 1
            log_message_to_file(f"RECEIVED ({msg_type})", data)
        elif msg_type == "Pong":
            game_state["statistics"]["pongs_received"] += 1
            log_message_to_file(f"RECEIVED ({msg_type})", data)
        else:
            log_message_to_file(f"RECEIVED ({msg_type})", data)

        return data
    except json.JSONDecodeError:
        log_message_to_file("RECEIVED (RAW)", message)
        return None


async def send_message(websocket, message):
    await websocket.send(json.dumps(message))
    game_state["statistics"]["messages_sent"] += 1
    log_message_to_file("SENT", message)


async def send_ping(websocket):
    ping_id = int(datetime.now().timestamp() * 1000)
    ping_message = {"scopePath": ["Room", "Quinoa"], "type": "Ping", "id": ping_id}
    await send_message(websocket, ping_message)
    game_state["statistics"]["pings_sent"] += 1


def get_slot_base_position():
    """Get the base coordinates for our user slot"""
    slot_idx = game_state.get("user_slot_index")
    if slot_idx is None or slot_idx >= len(SPAWN_POSITIONS):
        # Default to slot 0 if unknown
        return SPAWN_POSITIONS[0].copy()
    return SPAWN_POSITIONS[slot_idx].copy()


def find_player_user_slot():
    """Return the userSlot entry for our player if it exists.
    Returns the full slot object which contains both 'data' and 'petSlotInfos' at the slot level."""
    with game_state_lock:
        if not game_state["full_state"]:
            return None

        our_player_id = game_state["player_id"]
        if not our_player_id:
            return None

        full_state = game_state["full_state"]
        child_state = full_state.get("child", {})
        if child_state.get("scope") != "Quinoa":
            return None

        quinoa_state = child_state.get("data", {})
        user_slots = quinoa_state.get("userSlots", [])

        for slot_index, slot in enumerate(user_slots):
            if slot and slot.get("playerId") == our_player_id:
                game_state["user_slot_index"] = slot_index
                return deepcopy(slot)

        return None


async def wait_for_user_slot(require_data=False, timeout=10.0, check_interval=0.2):
    """Wait until our user slot (and optional data block) is populated."""
    loop = asyncio.get_running_loop()
    start_time = loop.time() if timeout is not None else None
    notified = False

    while True:
        slot = find_player_user_slot()
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


def get_player_slot_data_for_pets():
    """Return our player's slot data for the Quinoa game."""
    slot = find_player_user_slot()
    if not slot:
        return None

    slot_data = slot.get("data")
    if isinstance(slot_data, dict):
        return slot_data
    return None


def convert_local_to_server_coords(local_x, local_y):
    spawn_pos = get_slot_base_position()  # This is where player spawns (bottom-center)
    local_spawn = get_local_spawn_position()  # Player local position (11, 11)

    if (
        spawn_pos is None
        or local_spawn is None
        or local_x is None
        or local_y is None
        or game_state.get("user_slot_index") is None
    ):
        return None

    # Spawn position is where local (11, 11) maps to in server coords
    # So: server = spawn_pos + (local - local_spawn)
    server_x = spawn_pos["x"] + (local_x - local_spawn["x"])
    server_y = spawn_pos["y"] + (local_y - local_spawn["y"])
    return {"x": int(server_x), "y": int(server_y)}


def convert_server_to_local_coords(server_x, server_y):
    spawn_pos = get_slot_base_position()  # This is where player spawns (bottom-center)
    local_spawn = get_local_spawn_position()  # Player local position (11, 11)

    if (
        spawn_pos is None
        or local_spawn is None
        or server_x is None
        or server_y is None
        or game_state.get("user_slot_index") is None
    ):
        return None

    # Spawn position is where local (11, 11) maps to in server coords
    # So: local = local_spawn + (server - spawn_pos)
    local_x = local_spawn["x"] + (server_x - spawn_pos["x"])
    local_y = local_spawn["y"] + (server_y - spawn_pos["y"])
    return {"x": int(local_x), "y": int(local_y)}


async def initialize_pet_positions(websocket, wait_timeout=10.0):
    """Initialize pet positions from game state"""
    slot_data = get_player_slot_data_for_pets()
    if not slot_data:
        slot = await wait_for_user_slot(require_data=True, timeout=wait_timeout)
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
                # Random local position within the garden (local coords: 0-22 x, 0-11 y)
                local_pos = {
                    "x": random.randint(0, 22),
                    "y": random.randint(0, 11),
                }

                server_pos = convert_local_to_server_coords(
                    local_pos["x"], local_pos["y"]
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
        await send_message(websocket, pet_positions_message)


async def move_pets_randomly(websocket, wait_timeout=10.0):
    """Randomly move pets within garden bounds and send positions every update"""
    # Local coordinate bounds (0-indexed): 23 cols (0-22), 12 rows (0-11)
    MIN_X, MAX_X = 0, 22
    MIN_Y, MAX_Y = 0, 11

    slot_data = get_player_slot_data_for_pets()
    if not slot_data:
        slot = await wait_for_user_slot(require_data=True, timeout=wait_timeout)
        if not slot:
            return
        slot_data = slot.get("data", {})
        if not slot_data:
            return

    # petSlotInfos is at the slot level, not in slot['data']
    # Get it from the slot directly
    slot = find_player_user_slot()
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
        local_coords = convert_server_to_local_coords(server_pos["x"], server_pos["y"])
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
        new_server_pos = convert_local_to_server_coords(new_pos["x"], new_pos["y"])
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
        await send_message(websocket, pet_positions_message)


async def send_pet_positions(websocket):
    # Move pets randomly
    await move_pets_randomly(websocket)


async def find_harvestable_plant(slot_data, species):
    """Find a ready-to-harvest plant of the specified species
    Returns (tile_slot, slots_index) if found, else (None, None)
    """
    import time

    current_time = int(time.time() * 1000)

    garden_data = slot_data.get("garden", {})
    tile_objects = garden_data.get("tileObjects", {})

    # Get min mutations required for harvest
    min_mutations = 3
    if harvest_config:
        min_mutations = harvest_config.get("min_mutations", 3)

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


async def harvest_and_replant(websocket, slot_data, species):
    """Harvest a plant of the specified species and replant it
    Returns True if successful, False otherwise
    """
    tile_slot, slots_index = await find_harvestable_plant(slot_data, species)

    if tile_slot is None:
        return False

    print(f"🌾 Found harvestable {species} at slot {tile_slot}")

    # Harvest the crop
    harvest_message = {
        "scopePath": ["Room", "Quinoa"],
        "type": "HarvestCrop",
        "slot": tile_slot,
        "slotsIndex": slots_index,
    }
    await send_message(websocket, harvest_message)
    print(f"✂️  Harvested {species} from slot {tile_slot}")

    # Wait a moment for the harvest to process
    await asyncio.sleep(0.3)

    # Replant the same species
    plant_message = {
        "scopePath": ["Room", "Quinoa"],
        "type": "PlantSeed",
        "slot": tile_slot,
        "species": species,
    }
    await send_message(websocket, plant_message)
    print(f"🌱 Replanted {species} in slot {tile_slot}")

    return True


async def find_and_harvest(websocket, slot_data, species, mode="highest", min_mutations=None):
    """Find and harvest a plant of the specified species based on mutation priority

    Args:
        websocket: WebSocket connection
        slot_data: Player's slot data containing garden and inventory
        species: Plant species to find and harvest
        mode: "lowest" to prioritize lowest mutation count (for pet feeding)
              "highest" to prioritize highest mutation count (for auto-harvesting/selling)
        min_mutations: Minimum mutation count required to harvest (default: use harvest_config value)
                      Set to 0 for pet feeding to harvest any mature plant

    Returns:
        True if successful, False otherwise
    """
    import time

    current_time = int(time.time() * 1000)

    garden_data = slot_data.get("garden", {})
    tile_objects = garden_data.get("tileObjects", {})

    # Get min mutations required for harvest
    if min_mutations is None:
        min_mutations = 3
        if harvest_config:
            min_mutations = harvest_config.get("min_mutations", 3)

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
                harvestable_plants.append({
                    "tile_id": int(tile_id),
                    "slot_index": slot_index,
                    "mutation_count": len(mutations),
                    "mutations": mutations
                })

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

    print(f"🌾 Found harvestable {species} at slot {tile_slot} (mutations: {mutation_count}, priority: {priority_msg})")

    # Harvest the crop
    harvest_message = {
        "scopePath": ["Room", "Quinoa"],
        "type": "HarvestCrop",
        "slot": tile_slot,
        "slotsIndex": slots_index,
    }
    await send_message(websocket, harvest_message)
    print(f"✂️  Harvested {species} from slot {tile_slot}")

    # Wait a moment for the harvest to process
    await asyncio.sleep(0.3)

    # Replant the same species
    plant_message = {
        "scopePath": ["Room", "Quinoa"],
        "type": "PlantSeed",
        "slot": tile_slot,
        "species": species,
    }
    await send_message(websocket, plant_message)
    print(f"🌱 Replanted {species} in slot {tile_slot}")

    return True


async def feed_hungry_pets(websocket):
    """Check for hungry pets and feed them with appropriate produce"""
    # Extract player slot data while holding the lock
    with game_state_lock:
        if not game_state["full_state"]:
            return

        our_player_id = game_state["player_id"]
        full_state = game_state["full_state"]

        # Navigate to Quinoa game state
        if "child" not in full_state or full_state["child"].get("scope") != "Quinoa":
            return

        quinoa_state = full_state["child"].get("data", {})
        user_slots = quinoa_state.get("userSlots", [])

        # Find our player's slot and make a deep copy
        our_slot = None
        for slot in user_slots:
            if slot and slot.get("playerId") == our_player_id:
                our_slot = deepcopy(slot)
                break

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

    # Pet food mappings
    pet_food_map = {"Bee": "OrangeTulip", "Chicken": "Aloe", "Worm": "Aloe"}

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
                await send_message(websocket, feed_message)
                print(
                    f"🍽️  Fed {pet_species} (ID: {pet_id[:8]}...) with {required_food}"
                )

                # Remove the used produce from our lookup to avoid double-feeding
                produce_by_species[required_food].pop(0)
                if not produce_by_species[required_food]:
                    del produce_by_species[required_food]
            else:
                # No produce available - try to harvest and replant
                # Use mode="lowest" to prioritize plants with lowest mutation count for pet feeding
                # Use min_mutations=0 to accept any mature plant regardless of mutation count
                print(
                    f"⚠️  {pet_species} is hungry but no {required_food} available in inventory"
                )
                print(f"🔍 Searching for harvestable {required_food} (prioritizing lowest mutations for pet feeding)...")

                success = await find_and_harvest(
                    websocket, slot_data, required_food, mode="lowest", min_mutations=0
                )

                if success:
                    print(
                        f"✅ Harvested and replanted {required_food} for {pet_species}"
                    )
                    # Wait for the harvest to be processed and added to inventory
                    await asyncio.sleep(1.0)
                else:
                    print(f"❌ No harvestable {required_food} found in garden")


async def check_and_buy_from_shop(websocket):
    """Check shop inventory and buy configured items if available"""
    global shop_config

    if not shop_config or not shop_config.get("enabled", False):
        return

    # Extract player slot and shop data while holding the lock
    with game_state_lock:
        if not game_state["full_state"]:
            return

        our_player_id = game_state["player_id"]
        full_state = game_state["full_state"]

        # Navigate to Quinoa game state
        if "child" not in full_state or full_state["child"].get("scope") != "Quinoa":
            return

        quinoa_state = full_state["child"].get("data", {})
        user_slots = quinoa_state.get("userSlots", [])

        # Find our player's slot and make a deep copy
        our_slot = None
        for slot in user_slots:
            if slot and slot.get("playerId") == our_player_id:
                our_slot = deepcopy(slot)
                break

        # Also copy the shops data since we need it
        shops_data = deepcopy(quinoa_state.get("shops", {}))

    if not our_slot:
        return

    slot_data = our_slot.get("data", {})
    current_coins = slot_data.get("coinsCount", 0)

    # Check coin limits
    min_coins = shop_config.get("min_coins_to_keep", 0)
    print(f"\n🛍️  Checking shops... (Balance: {current_coins:,} coins)")

    if current_coins <= min_coins:
        print(f"   ⚠️  Not enough coins (need to keep {min_coins:,})")
        return

    if not shops_data:
        print("   📭 No shops available")
        return

    # Get configured items to buy
    items_config = shop_config.get("items_to_buy", {})
    items_bought = 0
    total_items_in_stock = 0

    # Check seed shop
    seed_shop = shops_data.get("seed", {})
    seed_inventory = seed_shop.get("inventory", [])
    seeds_to_buy = []

    if seed_inventory:
        seeds_config = items_config.get("seeds", {})
        seeds_enabled = seeds_config.get("enabled", False)
        configured_seeds = seeds_config.get("items", [])

        # Check if we have any seeds to buy
        for item in seed_inventory:
            if not item:
                continue

            species = item.get("species")
            stock = item.get("initialStock", 0)

            if stock > 0:
                total_items_in_stock += 1

                # Check if we want to buy this seed
                if seeds_enabled and species in configured_seeds:
                    print(f"   ✅ Found configured seed: {species} (Stock: {stock})")
                    seeds_to_buy.append({"species": species, "stock": stock})
                else:
                    if not seeds_enabled:
                        print(
                            f"   ➖ {species} (Seed) - seed buying disabled (Stock: {stock})"
                        )
                    else:
                        print(
                            f"   ➖ {species} (Seed) - not in config (Stock: {stock})"
                        )

    # Check egg shop
    egg_shop = shops_data.get("egg", {})
    egg_inventory = egg_shop.get("inventory", [])
    eggs_to_buy = []

    if egg_inventory:
        eggs_config = items_config.get("eggs", {})
        eggs_enabled = eggs_config.get("enabled", False)
        configured_eggs = eggs_config.get("items", [])

        for item in egg_inventory:
            if not item:
                continue

            egg_id = item.get("eggId")
            stock = item.get("initialStock", 0)

            if stock > 0:
                total_items_in_stock += 1

                # Check if we want to buy this egg
                if eggs_enabled and egg_id in configured_eggs:
                    print(f"   ✅ Found configured egg: {egg_id} (Stock: {stock})")
                    eggs_to_buy.append({"eggId": egg_id, "stock": stock})
                else:
                    if not eggs_enabled:
                        print(
                            f"   ➖ {egg_id} (Egg) - egg buying disabled (Stock: {stock})"
                        )
                    else:
                        print(f"   ➖ {egg_id} (Egg) - not in config (Stock: {stock})")

    # Buy all configured seeds
    for seed_item in seeds_to_buy:
        species = seed_item["species"]
        stock = seed_item["stock"]

        print(f"   💳 Purchasing {stock}x {species} seeds...")

        # Buy all available stock
        for i in range(stock):
            buy_message = {
                "type": "PurchaseSeed",
                "species": species,
                "scopePath": ["Room", "Quinoa"],
            }
            await send_message(websocket, buy_message)

            # Optimistically update shop count in game_state
            with game_state_lock:
                if game_state["full_state"]:
                    full_state = game_state["full_state"]
                    if "child" in full_state and full_state["child"].get("scope") == "Quinoa":
                        quinoa_state = full_state["child"].get("data", {})
                        shops = quinoa_state.get("shops", {})
                        seed_shop = shops.get("seed", {})
                        inventory = seed_shop.get("inventory", [])

                        for item in inventory:
                            if item and item.get("species") == species:
                                current_stock = item.get("initialStock", 0)
                                if current_stock > 0:
                                    item["initialStock"] = current_stock - 1
                                    if i == 0:  # Only print on first purchase
                                        print(f"   📉 Optimistically updating {species} stock from {current_stock}")
                                break

            items_bought += 1
            await asyncio.sleep(0.1)  # Small delay between purchases

        print(f"   🛒 Bought {stock}x {species} seeds")

    # Buy all configured eggs
    for egg_item in eggs_to_buy:
        egg_id = egg_item["eggId"]
        stock = egg_item["stock"]

        print(f"   💳 Purchasing {stock}x {egg_id}...")

        # Buy all available stock
        for i in range(stock):
            buy_message = {
                "type": "PurchaseEgg",
                "eggId": egg_id,
                "scopePath": ["Room", "Quinoa"],
            }
            await send_message(websocket, buy_message)

            # Optimistically update shop count in game_state
            with game_state_lock:
                if game_state["full_state"]:
                    full_state = game_state["full_state"]
                    if "child" in full_state and full_state["child"].get("scope") == "Quinoa":
                        quinoa_state = full_state["child"].get("data", {})
                        shops = quinoa_state.get("shops", {})
                        egg_shop = shops.get("egg", {})
                        inventory = egg_shop.get("inventory", [])

                        for item in inventory:
                            if item and item.get("eggId") == egg_id:
                                current_stock = item.get("initialStock", 0)
                                if current_stock > 0:
                                    item["initialStock"] = current_stock - 1
                                    if i == 0:  # Only print on first purchase
                                        print(f"   📉 Optimistically updating {egg_id} stock from {current_stock}")
                                break

            items_bought += 1
            await asyncio.sleep(0.1)  # Small delay between purchases

        print(f"   🛒 Bought {stock}x {egg_id}")

    # Summary
    if total_items_in_stock == 0:
        print("   📭 All shops are out of stock")
    elif items_bought == 0:
        print(
            f"   ℹ️  Found {total_items_in_stock} items in stock, but none match config"
        )
    else:
        print(
            f"   ✅ Purchased {items_bought} item(s) and returned to original position"
        )


async def try_room(room_id, player_id, headers):
    """Try to connect to a specific room and check if player is in it"""
    url = f"wss://magicgarden.gg/version/cb622cd/api/rooms/{room_id}/connect?surface=%22web%22&platform=%22desktop%22&playerId=%22{player_id}%22&version=%22cb622cd%22&source=%22manualUrl%22&capabilities=%22fbo_mipmap_unsupported%22"

    print(f"\nTrying room {room_id}...")

    try:
        # Connect WITHOUT async with so we can keep the connection open
        websocket = await websockets.connect(
            url, additional_headers=headers, compression="deflate"
        )

        # Send initial messages
        await send_message(
            websocket,
            {"scopePath": ["Room"], "type": "VoteForGame", "gameName": "Quinoa"},
        )
        await send_message(
            websocket,
            {"scopePath": ["Room"], "type": "SetSelectedGame", "gameName": "Quinoa"},
        )

        # Wait for Welcome message with timeout
        try:
            message = await asyncio.wait_for(websocket.recv(), timeout=5.0)

            if message.strip().lower() == "ping":
                await websocket.send("pong")
                message = await asyncio.wait_for(websocket.recv(), timeout=5.0)

            try:
                data = json.loads(message)
            except json.JSONDecodeError as e:
                print(f"  Failed to parse message from {room_id}: {e}")
                print(f"  Raw message: {message[:200]}")
                await websocket.close()
                return None, None, None

            if not data or not isinstance(data, dict):
                print(f"  Received invalid data from {room_id}: {data}")
                await websocket.close()
                return None, None, None

            if data.get("type") == "Welcome":
                # Check if player is in this room
                full_state = data.get("fullState")
                if not full_state:
                    print(f"  No fullState in Welcome message for {room_id}")
                    await websocket.close()
                    return None, None, None

                room_data = full_state.get("data")
                if not room_data:
                    print(f"  No room data in Welcome message for {room_id}")
                    await websocket.close()
                    return None, None, None

                players = room_data.get("players")
                if not players:
                    print(f"  No player data in Welcome message for {room_id}")
                    await websocket.close()
                    return None, None, None

                print(f"  Found {len(players)} players in room {room_id}:")
                for idx, player in enumerate(players):
                    if player:
                        player_name = player.get("name", "Unknown")
                        player_id_in_room = player.get("id", "Unknown")
                        print(
                            f"    [{idx+1}] Name: {player_name} | ID: {player_id_in_room}"
                        )
                    else:
                        print(f"    [{idx+1}] Empty slot")

                print(f"\n  Looking for player ID: {player_id}")

                for slot in players:
                    if slot and slot.get("id") == player_id:
                        print(f"  ✓ Found player in room {room_id}!")
                        # Return the open websocket connection and the FULL Welcome message
                        return websocket, data, room_id

                # Count actual players (non-None slots)
                actual_player_count = sum(1 for slot in players if slot is not None)
                print(
                    f"  Player not in room {room_id} ({actual_player_count}/6 players)"
                )
                # Close this connection before returning
                await websocket.close()
                return None, None, None
            else:
                print(f"  Unexpected message type from {room_id}: {data.get('type')}")
                await websocket.close()
                return None, None, None

        except asyncio.TimeoutError:
            print(f"  Timeout waiting for Welcome message from {room_id}")
            await websocket.close()
            return None, None, None

    except Exception as e:
        print(f"  Error connecting to {room_id}: {e}")
        print(f"  Traceback: {traceback.format_exc()}")
        return None, None, None


async def websocket_client():
    with open(MESSAGE_LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"Magic Garden Bot - Message Log\n")
        f.write(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    print("=" * 60)
    print("MAGIC GARDEN BOT - STARTING")
    print("=" * 60)

    # Load user configuration
    try:
        user = load_user_config()
    except RuntimeError as exc:
        print(f"\nConfiguration error: {exc}")
        print("Update bot_config.json and restart the bot.")
        return
    player_id = user["playerId"]
    base_cookies = user["cookies"]
    last_room = user["lastRoom"]

    # Check for command line override
    room_id_override = parse_command_line_args()

    game_state["player_id"] = player_id
    print(f"\nPlayer ID: {player_id}")

    # Determine which rooms to try
    all_rooms = [f"MG{num}" for num in range(1, 16)]

    def prioritize_room(preferred_room, rooms):
        if not preferred_room:
            return rooms
        ordered = [preferred_room]
        for room in rooms:
            if room != preferred_room:
                ordered.append(room)
        return ordered

    if room_id_override:
        print(
            f"\nUsing room from --room-id parameter first (falling back to others if needed): {room_id_override}"
        )
        rooms_to_try = prioritize_room(room_id_override, all_rooms)
    elif last_room:
        print(
            f"\nTrying last connected room first (will fall back to others if busy): {last_room}"
        )
        rooms_to_try = prioritize_room(last_room, all_rooms)
    else:
        print("\nSearching for available room...")
        rooms_to_try = all_rooms

    # Try rooms
    websocket = None
    welcome_data = None
    connected_room = None

    for room_id in rooms_to_try:
        print(f"\n[Room {room_id}] Authenticating...")

        # Authenticate for this specific room
        auth_data, updated_cookies = await authenticate_user(base_cookies, room_id)

        if not auth_data or not updated_cookies:
            print(f"  ✗ Authentication failed for {room_id}")
            continue

        print(f"  ✓ Authentication successful for {room_id}")

        if updated_cookies != base_cookies:
            save_cookies(updated_cookies)
            base_cookies = updated_cookies

        # Set up headers with authenticated cookies
        headers = {
            "Origin": "https://magicgarden.gg",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Cookie": updated_cookies,
        }

        # Try to connect to this room
        ws, data, room = await try_room(room_id, player_id, headers)

        if ws and data:
            websocket = ws
            welcome_data = data
            connected_room = room
            # Save this as the last successful room
            save_last_room(room)
            break

    if not websocket:
        print("\n" + "!" * 60)
        print("ERROR: Could not find an available room!")
        print("All rooms (MG1-MG15) are full or unreachable.")
        print("!" * 60)
        return

    print(f"\n{'='*60}")
    print(f"CONNECTED TO ROOM: {connected_room}")
    print(f"{'='*60}\n")

    # Store room ID in game state
    game_state["room_id"] = connected_room

    # Process the welcome message and get spawn position
    spawn_pos = process_welcome_message(welcome_data)

    try:
        # We're already connected via the try_room function
        # Continue with the existing websocket

        async def startup_task():
            """Handle initialization that requires receiving messages"""
            # Wait for user slot to be populated (requires message processing to be active)
            slot_available = True
            if game_state.get("user_slot_index") is None:
                slot = await wait_for_user_slot(timeout=10.0)
                slot_available = slot is not None
                if slot_available and game_state.get("user_slot_index") is not None:
                    spawn_pos_updated = SPAWN_POSITIONS[
                        game_state["user_slot_index"]
                    ].copy()
                else:
                    spawn_pos_updated = spawn_pos
            else:
                spawn_pos_updated = spawn_pos

            # Send PlayerPosition message with spawn position
            if spawn_pos_updated and slot_available:
                position_message = {
                    "scopePath": ["Room", "Quinoa"],
                    "type": "PlayerPosition",
                    "position": spawn_pos_updated,
                }
                await send_message(websocket, position_message)
                print(
                    f"Sent spawn position to server: ({spawn_pos_updated['x']}, {spawn_pos_updated['y']})\n"
                )
            elif not spawn_pos_updated:
                print("No spawn position available to send to server.\n")
            else:
                print(
                    "Skipped sending spawn position; user slot never became available.\n"
                )

            # Initialize pet positions
            await initialize_pet_positions(websocket)

        async def ping_task():
            """Send pings periodically"""
            while True:
                await asyncio.sleep(2)
                try:
                    await send_ping(websocket)
                except:
                    break

        async def pet_movement_task():
            """Move pets and send positions periodically"""
            while True:
                await asyncio.sleep(1)  # Send pet positions every second
                try:
                    await send_pet_positions(websocket)
                except:
                    break

        async def feeding_task():
            """Check and feed hungry pets periodically"""
            while True:
                await asyncio.sleep(5)  # Check every 5 seconds
                try:
                    await feed_hungry_pets(websocket)
                except:
                    break

        async def shop_buying_task():
            """Check shop and buy configured items periodically"""
            # Wait a bit before starting to allow game state to load
            await asyncio.sleep(10)

            interval = 10  # Default interval
            if shop_config:
                interval = shop_config.get("check_interval_seconds", 10)

            while True:
                await asyncio.sleep(interval)
                try:
                    await check_and_buy_from_shop(websocket)
                except Exception as e:
                    print(f"Error in shop buying task: {e}")

        async def receive_messages():
            """Receive and process messages"""
            try:
                async for message in websocket:
                    if message.strip().lower() == "ping":
                        game_state["statistics"]["pings_received"] += 1
                        await websocket.send("pong")
                        game_state["statistics"]["pongs_sent"] += 1
                        log_message_to_file("SENT", "pong")
                        continue
                    process_message(message)
            except websockets.exceptions.ConnectionClosed:
                pass

        await asyncio.gather(
            receive_messages(),
            startup_task(),
            ping_task(),
            pet_movement_task(),
            feeding_task(),
            shop_buying_task(),
        )

    except Exception as e:
        print(f"Error: {e}")


def run_websocket():
    """Run WebSocket in async event loop"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(websocket_client())


def main():
    # Start WebSocket in separate thread
    ws_thread = threading.Thread(target=run_websocket, daemon=True)
    ws_thread.start()

    # Start GUI
    root = tk.Tk()
    app = MagicGardenGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
