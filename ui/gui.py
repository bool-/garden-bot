"""
GUI components for Magic Garden bot.

This module contains the main GUI window and console redirection.
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
import queue
import time

from game_state import GameState
from config import HarvestConfig
from utils.coordinates import convert_server_to_local_coords


# Console output redirector for GUI
class ConsoleRedirector:
    def __init__(self, message_queue, original_stream):
        self.message_queue = message_queue
        self.original_stream = original_stream

    def write(self, message):
        # Write to original console
        self.original_stream.write(message)
        self.original_stream.flush()

        # Queue message for GUI thread to process
        if self.message_queue:
            self.message_queue.put(message)

    def flush(self):
        self.original_stream.flush()


# GUI Application - Simple Inventory Display
class MagicGardenGUI:
    def __init__(self, root, game_state: GameState, harvest_config: HarvestConfig = None):
        self.root = root
        self.game_state = game_state
        self.harvest_config = harvest_config

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

        # Redirect stdout to console log using a thread-safe queue
        self.console_queue = queue.Queue()
        import sys
        sys.stdout = ConsoleRedirector(self.console_queue, sys.stdout)
        self.root.after(50, self.process_console_queue)

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
        return self.game_state.get_player_slot()

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
                local_coords = convert_server_to_local_coords(server_x, server_y, self.game_state)
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
                            if len(slots) > 1:
                                print(
                                    f"DEBUG: tile {tid} reported {len(slots)} plant slots; only the first will be rendered."
                                )
                            if slots:
                                slot = slots[0]
                                end_time = slot.get("endTime", 0)
                                species = slot.get("species", "?")
                                mutations = slot.get("mutations", [])
                                mutation_count = len(mutations)

                                # Get min mutations required for harvest
                                min_mutations = 3
                                if self.harvest_config:
                                    min_mutations = self.harvest_config.min_mutations

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

                    # Check for Dawnlit/Ambershine states (bottom indicator)
                    light_state = None
                    light_color = None
                    if "Ambershine" in mutations:
                        light_state = "Ambershine"
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
                    position.get("x"), position.get("y"), self.game_state
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

    def process_console_queue(self):
        """Append queued console output on the GUI thread."""
        try:
            while True:
                message = self.console_queue.get_nowait()
                self.console_log.insert(tk.END, message)
                self.console_log.see(tk.END)
        except queue.Empty:
            pass
        except tk.TclError:
            return  # Widget destroyed during shutdown

        try:
            self.root.after(50, self.process_console_queue)
        except tk.TclError:
            pass

    def update_ui(self):
        """Update UI with current game state"""
        # Player info
        player_id = self.game_state.get("player_id")
        self.player_id_var.set(player_id or "Unknown")
        display_name = self.game_state.get("player_name") or player_id or "Unknown"
        self.player_name_var.set(display_name)

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
        stats = self.game_state["statistics"]
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
        room_id = self.game_state.get("room_id", "Unknown")
        self.stats_room_id.set(room_id)

        # Get player count from full_state
        # Note: game_state["full_state"] returns a deepcopy, so it's thread-safe
        player_count = 0
        full_state = self.game_state["full_state"]
        if full_state:
            room_data = full_state.get("data", {})
            players = room_data.get("players", [])
            # Count non-None players
            player_count = sum(1 for p in players if p is not None)
        self.stats_player_count.set(f"{player_count}/6")

        # Schedule next update
        self.root.after(500, self.update_ui)
