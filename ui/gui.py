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

    def _calculate_garden_stats(self, tile_objects):
        """Calculate garden statistics from tile objects."""
        growing_count = 0
        mature_count = 0
        current_time = int(time.time() * 1000)

        for tile_obj in tile_objects.values():
            if tile_obj and tile_obj.get("objectType") == "plant":
                slots = tile_obj.get("slots", [])
                if slots:
                    slot = slots[0]
                    end_time = slot.get("endTime", 0)
                    if current_time >= end_time:
                        mature_count += 1
                    else:
                        growing_count += 1

        empty_count = 200 - len(tile_objects)
        return growing_count, mature_count, empty_count

    def _build_tile_position_map(self, tile_objects, garden_cols=20):
        """Build a map from visual position to tile object for fast lookup."""
        position_map = {}

        for tid, obj in tile_objects.items():
            if tid.isdigit():
                tile_id = int(tid)
                row = tile_id // garden_cols
                col = tile_id % garden_cols

                # Convert to visual position
                visual_row = row + 1  # +1 for top border
                visual_col = col + 1 if col < 10 else col + 2  # +1 or +2 for borders

                position_map[(visual_row, visual_col)] = (tid, obj)

        return position_map

    def _get_tile_color(self, tile_obj, min_mutations):
        """Determine fill and outline color for a tile object."""
        current_time = int(time.time() * 1000)
        obj_type = tile_obj.get("objectType")

        if obj_type == "plant":
            slots = tile_obj.get("slots", [])
            if slots:
                slot = slots[0]
                end_time = slot.get("endTime", 0)
                mutations = slot.get("mutations", [])
                mutation_count = len(mutations)

                if current_time >= end_time:
                    # Mature
                    if mutation_count >= min_mutations:
                        return "#00e676", "#1fec84"  # Ready to harvest - vibrant green
                    else:
                        return "#ff9100", "#ffa726"  # Grown but not mutated - orange
                else:
                    return "#ffd93d", "#ffe066"  # Growing - yellow
            else:
                return "#5a5a6e", "#6a6a7e"  # Empty plant slot
        elif obj_type == "egg":
            matured_at = tile_obj.get("maturedAt", 0)
            if current_time >= matured_at:
                return "#69f0ae", "#7ff5bb"  # Mature egg - mint green
            else:
                return "#ffeb3b", "#fff176"  # Growing egg - bright yellow
        elif obj_type == "pet":
            return "#d946ef", "#e469f2"  # Pet - magenta
        elif obj_type == "decor":
            return "#607D8B", "#78909C"  # Decoration - blue/gray
        else:
            return "#666666", "#888888"  # Unknown

    def _draw_mutation_indicators(self, canvas, x, y, tile_size, mutations):
        """Draw mutation indicators on a plant tile."""
        indicator_size = max(tile_size // 4, 3)

        # Rainbow indicator (top-right)
        if "Rainbow" in mutations:
            indicator_x = x + tile_size - indicator_size - 2
            indicator_y = y + 2
            rainbow_colors = ["#ff0000", "#ff7f00", "#ffff00", "#00ff00", "#0000ff", "#4b0082"]
            stripe_height = max(indicator_size // len(rainbow_colors), 1)

            for i, color in enumerate(rainbow_colors):
                canvas.create_rectangle(
                    indicator_x,
                    indicator_y + i * stripe_height,
                    indicator_x + indicator_size,
                    indicator_y + (i + 1) * stripe_height,
                    fill=color,
                    outline="",
                )

        # Gold indicator (top-left if Rainbow, else top-right)
        if "Gold" in mutations:
            indicator_x = x + 2 if "Rainbow" in mutations else x + tile_size - indicator_size - 2
            indicator_y = y + 2
            canvas.create_oval(
                indicator_x,
                indicator_y,
                indicator_x + indicator_size,
                indicator_y + indicator_size,
                fill="#ffd700",
                outline="#ffed4e",
                width=1,
            )

        # Water state indicator (left side)
        water_states = {
            "Frozen": "#E1F5FE",
            "Chilled": "#00BCD4",
            "Wet": "#2196F3",
        }
        for state, color in water_states.items():
            if state in mutations:
                indicator_x = x + 2
                indicator_y = y + tile_size // 2 - indicator_size // 2
                canvas.create_oval(
                    indicator_x,
                    indicator_y,
                    indicator_x + indicator_size,
                    indicator_y + indicator_size,
                    fill=color,
                    outline="#FFFFFF",
                    width=1,
                )
                break

        # Light state indicator (bottom)
        light_states = {
            "Ambershine": "#FFAB00",
            "Dawnlit": "#FF6090",
        }
        for state, color in light_states.items():
            if state in mutations:
                indicator_x = x + tile_size // 2 - indicator_size // 2
                indicator_y = y + tile_size - indicator_size - 2
                canvas.create_oval(
                    indicator_x,
                    indicator_y,
                    indicator_x + indicator_size,
                    indicator_y + indicator_size,
                    fill=color,
                    outline="#FFFFFF",
                    width=1,
                )
                break

    def render_garden_state(self, player_slot):
        """Render the garden grid with actual tile objects."""
        slot_data = player_slot.get("data", {})
        self.garden_canvas.delete("all")

        # Extract garden data
        garden_data = slot_data.get("garden", {})
        tile_objects = garden_data.get("tileObjects", {})

        # Configuration
        canvas_width = 650
        canvas_height = 400
        garden_rows, garden_cols = 10, 20
        visual_rows, visual_cols = 12, 23  # +borders and paths
        border_offset = 2

        # Calculate tile size
        tile_size = min(canvas_width // visual_cols, canvas_height // visual_rows)

        # Draw background
        self.garden_canvas.create_rectangle(
            0, 0, canvas_width, canvas_height, fill=self.colors["canvas_bg"], outline=""
        )

        # Build tile position map (eliminates O(n²×m) lookups)
        position_map = self._build_tile_position_map(tile_objects, garden_cols)

        # Get min mutations config
        min_mutations = self.harvest_config.min_mutations if self.harvest_config else 3

        # Draw grid
        for row in range(visual_rows):
            for col in range(visual_cols):
                x = border_offset + col * tile_size
                y = border_offset + row * tile_size

                # Check if boardwalk
                is_boardwalk = row in (0, visual_rows - 1) or col in (0, visual_cols - 1, 11)

                if is_boardwalk:
                    fill_color, outline_color = "#a0826d", "#b8956f"
                else:
                    # Check for tile object at this position
                    tile_info = position_map.get((row, col))
                    if tile_info:
                        tid, tile_obj = tile_info
                        fill_color, outline_color = self._get_tile_color(tile_obj, min_mutations)

                        # Warn if multiple slots (should be rare)
                        if tile_obj.get("objectType") == "plant":
                            slots = tile_obj.get("slots", [])
                            if len(slots) > 1:
                                print(f"DEBUG: tile {tid} has {len(slots)} slots; rendering first only")
                    else:
                        fill_color, outline_color = "#4a4a5e", "#5a5a6e"  # Empty

                # Draw tile
                self.garden_canvas.create_rectangle(
                    x, y, x + tile_size - 1, y + tile_size - 1,
                    fill=fill_color, outline=outline_color, width=1
                )

                # Draw mutation indicators
                if not is_boardwalk:
                    tile_info = position_map.get((row, col))
                    if tile_info:
                        _, tile_obj = tile_info
                        if tile_obj.get("objectType") == "plant":
                            slots = tile_obj.get("slots", [])
                            if slots:
                                mutations = slots[0].get("mutations", [])
                                self._draw_mutation_indicators(
                                    self.garden_canvas, x, y, tile_size, mutations
                                )

        # Draw pets
        pet_slot_infos = player_slot.get("petSlotInfos")
        if isinstance(pet_slot_infos, dict):
            for slot_info in pet_slot_infos.values():
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

                local_x, local_y = local_coords.get("x"), local_coords.get("y")
                if local_x < 0 or local_x > 22 or local_y < 0 or local_y > 11:
                    continue

                center_x = border_offset + local_x * tile_size + tile_size // 2
                center_y = border_offset + local_y * tile_size + tile_size // 2
                radius = max(tile_size // 3, 4)

                self.garden_canvas.create_oval(
                    center_x - radius, center_y - radius,
                    center_x + radius, center_y + radius,
                    fill="#d946ef", outline="#e980f5", width=2
                )

        # Draw player marker
        player_pos = player_slot.get("position")
        if isinstance(player_pos, dict):
            server_x, server_y = player_pos.get("x"), player_pos.get("y")
            if server_x is not None and server_y is not None:
                local_coords = convert_server_to_local_coords(server_x, server_y, self.game_state)
                if local_coords:
                    player_x, player_y = local_coords.get("x", -1), local_coords.get("y", -1)
                    if player_x >= 0 and player_y >= 0:
                        center_x = border_offset + player_x * tile_size + tile_size // 2
                        center_y = border_offset + player_y * tile_size + tile_size // 2
                        radius = max(tile_size // 3, 4)

                        self.garden_canvas.create_oval(
                            center_x - radius, center_y - radius,
                            center_x + radius, center_y + radius,
                            fill="#00d4ff", outline="#33ddff", width=2
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
