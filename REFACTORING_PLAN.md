# Garden Bot Refactoring Plan

## Status: Phases 1-3 Complete ✓

### Completed Phases

#### Phase 1: Configuration Management ✓
- **Created:** `config.py` (218 lines)
- **Created:** `utils/constants.py` (22 lines)
- **Moved from bot_gui.py:**
  - `get_default_shop_config()`
  - `normalize_shop_config()`
  - `generate_id()`, `generate_player_id()`
  - `load_user_config()` → `load_config()`
  - `save_last_room()`, `save_cookies()`
- **New dataclasses:**
  - `BotConfig` - Complete configuration container
  - `ShopConfig` - Shop auto-buy settings
  - `HarvestConfig` - Harvest settings
  - `PetFoodConfig` - Pet food mappings
- **Benefits:** No more global config variables, structured config objects

#### Phase 2: Network Protocol Layer ✓
- **Created:** `network/protocol.py` (369 lines)
- **Moved from bot_gui.py:**
  - All JSON Patch functions (6 functions, ~120 lines)
  - `log_message_to_file()`
  - `process_welcome_message()`
  - `process_partial_state_message()`
  - `process_message()`
  - `is_player_in_room_state()`
- **Updated:** Functions now take `GameState` as parameter instead of using globals
- **Benefits:** Protocol layer independent of GUI/automation, testable

#### Phase 3: Coordinate & State Utilities ✓
- **Created:** `utils/coordinates.py` (107 lines)
- **Enhanced:** `game_state.py` (+28 lines)
- **Moved from bot_gui.py:**
  - `get_random_spawn_position()`
  - `get_local_spawn_position()`
  - `get_slot_base_position()`
  - `convert_local_to_server_coords()`
  - `convert_server_to_local_coords()`
- **Added to GameState:**
  - `get_player_slot()` - Find player's user slot
- **Benefits:** Centralized coordinate logic, reusable utilities

---

## Remaining Phases

### Phase 4: Network Client Layer

**File to create:** `network/client.py` (~450 lines)

**Class:** `MagicGardenClient`

**Responsibilities:**
- Manage websocket connection lifecycle
- Handle authentication
- Room search and connection
- Send/receive messages
- Maintain connection (ping/pong)
- Update GameState when messages arrive

**Functions to move from bot_gui.py:**

1. **Authentication** (~35 lines)
   ```python
   async def authenticate_user(cookies, room_id="MG1")
   # Lines 1474-1508
   ```

2. **Room Connection** (~157 lines)
   ```python
   async def try_room(room_id, player_id, headers)
   # Lines 2483-2639
   ```

3. **Main Client** (~223 lines)
   ```python
   async def websocket_client()
   # Lines 2642-2864
   # REFACTOR into class methods
   ```

4. **Message Sending** (~10 lines)
   ```python
   async def send_message(websocket, message)
   async def send_ping(websocket)
   # Lines 1683-1693
   ```

**Proposed class structure:**
```python
class MagicGardenClient:
    def __init__(self, game_state: GameState, config: BotConfig):
        self.game_state = game_state
        self.config = config
        self.websocket = None
        self.tasks = []

    async def authenticate(self, room_id: str) -> tuple:
        """Authenticate with server"""

    async def try_room(self, room_id: str) -> bool:
        """Try to connect to specific room"""

    async def connect(self):
        """Main connection logic (from websocket_client)"""

    async def send(self, message: dict):
        """Send message to server"""

    async def send_ping(self):
        """Send ping message"""

    def register_task(self, coro):
        """Register automation task to run"""

    async def receive_messages(self):
        """Message receiving loop"""

    async def run(self):
        """Run client (main entry point)"""
```

**Dependencies:**
- `websockets`
- `aiohttp`
- `asyncio`
- `game_state.GameState`
- `config.BotConfig`
- `network.protocol.process_message`
- `network.protocol.log_message_to_file`

**Testing:**
```bash
cd garden-bot
python -m py_compile network/client.py
python -c "from network.client import MagicGardenClient; print('OK')"
```

---

### Phase 5: Automation Modules

#### 5A. Harvest Automation

**File to create:** `automation/harvest.py` (~180 lines)

**Functions to move from bot_gui.py:**

1. `find_harvestable_plant(slot_data, species)` - Lines 1980-2017 (38 lines)
2. `harvest_and_replant(websocket, slot_data, species)` - Lines 2020-2054 (35 lines)
3. `find_and_harvest(websocket, slot_data, species, mode, min_mutations)` - Lines 2057-2158 (102 lines)

**Refactor signature:**
```python
async def run_auto_harvest(
    client: MagicGardenClient,
    game_state: GameState,
    config: HarvestConfig
):
    """Auto-harvest task that runs periodically"""
```

**Dependencies:**
- `time`
- `asyncio`
- `game_state.GameState`
- `config.HarvestConfig`
- `network.client.MagicGardenClient`

---

#### 5B. Pet Automation

**File to create:** `automation/pets.py` (~260 lines)

**Functions to move from bot_gui.py:**

1. **Feeding** (~105 lines)
   ```python
   async def feed_hungry_pets(websocket)
   # Lines 2161-2265
   ```

2. **Movement** (~105 lines)
   ```python
   async def move_pets_randomly(websocket, wait_timeout=10.0)
   # Lines 1868-1972
   ```

3. **Initialization** (~55 lines)
   ```python
   async def initialize_pet_positions(websocket, wait_timeout=10.0)
   # Lines 1811-1865
   ```

4. **Helpers** (~60 lines)
   ```python
   def get_player_slot_data_for_pets()  # Lines 1759-1768
   async def wait_for_user_slot(...)     # Lines 1732-1756
   def find_player_user_slot()           # Lines 1705-1729
   # Note: Some may move to game_state.py instead
   ```

**Refactor into:**
```python
async def run_pet_feeder(
    client: MagicGardenClient,
    game_state: GameState,
    config: PetFoodConfig
):
    """Pet feeding task"""

async def run_pet_mover(
    client: MagicGardenClient,
    game_state: GameState
):
    """Pet movement task"""

async def initialize_pets(
    client: MagicGardenClient,
    game_state: GameState
):
    """Initialize pet positions"""
```

**Dependencies:**
- `asyncio`
- `game_state.GameState`
- `config.PetFoodConfig`
- `network.client.MagicGardenClient`
- `utils.coordinates` (for pet movement)
- `automation.harvest.find_and_harvest` (for auto-harvest when no food)

---

#### 5C. Shop Automation

**File to create:** `automation/shop.py` (~215 lines)

**Functions to move from bot_gui.py:**

1. `check_and_buy_from_shop(websocket)` - Lines 2268-2480 (213 lines)

**Refactor into:**
```python
async def run_shop_buyer(
    client: MagicGardenClient,
    game_state: GameState,
    config: ShopConfig
):
    """Shop auto-buy task"""
```

**Dependencies:**
- `asyncio`
- `copy.deepcopy`
- `game_state.GameState`
- `config.ShopConfig`
- `network.client.MagicGardenClient`

---

### Phase 6: GUI Layer

**File to create:** `ui/gui.py` (~1,100 lines)

**Classes to move from bot_gui.py:**

1. **ConsoleRedirector** - Lines 27-42 (16 lines)
2. **MagicGardenGUI** - Lines 262-1328 (1,067 lines)

**Key changes:**
- Remove `global game_state, game_state_lock`
- Inject `GameState` in `__init__(self, root, game_state: GameState)`
- Remove direct network calls
- Use controller pattern for actions

**Methods in MagicGardenGUI:**
- `__init__(self, root, game_state: GameState)`
- `setup_ui(self)` - Create widgets
- `draw_legend(self)` - Draw color legend
- `log_to_console(self, message)` - Add console message
- `extract_player_data(self)` - Get player slot
- `render_garden_state(self, player_slot)` - Render garden (~400 lines)
- `render_pet_state(self, slot_data)` - Render pets (~90 lines)
- `process_console_queue(self)` - Process stdout
- `update_ui(self)` - Main update loop (~240 lines)

**Optional split:**
If `ui/gui.py` is too large, consider:
- `ui/renderers.py` - Extract render_garden_state, render_pet_state
- `ui/widgets.py` - Custom widget classes

**Dependencies:**
- `tkinter`
- `queue`
- `game_state.GameState`
- `utils.coordinates.convert_server_to_local_coords`
- `config.HarvestConfig` (for mutation color coding)

---

### Phase 7: Application Entry Point

**File to create:** `app.py` (~50 lines)

**Functions to move from bot_gui.py:**

1. `parse_command_line_args()` - Lines 247-258 (12 lines)
2. `run_websocket()` - Lines 2866-2870 (5 lines)
3. `main()` - Lines 2873-2893 (21 lines)

**Refactor into:**
```python
import asyncio
import threading
import tkinter as tk

from config import load_config
from game_state import GameState
from network.client import MagicGardenClient
from automation import harvest, pets, shop
from ui.gui import MagicGardenGUI


def parse_args():
    """Parse command line arguments"""
    import argparse
    parser = argparse.ArgumentParser(description='Magic Garden Bot')
    parser.add_argument('--room-id', type=str, help='Override room ID')
    parser.add_argument('--headless', action='store_true', help='No GUI')
    return parser.parse_args()


async def run_bot(config, game_state, headless=False):
    """Run the bot (headless or with GUI)"""
    # Create client
    client = MagicGardenClient(game_state, config)

    # Register automation tasks
    client.register_task(harvest.run_auto_harvest(client, game_state, config.harvest))
    client.register_task(pets.run_pet_feeder(client, game_state, config.pet_food))
    client.register_task(pets.run_pet_mover(client, game_state))
    client.register_task(shop.run_shop_buyer(client, game_state, config.shop))

    # Run client
    await client.run()


def main():
    """Application entry point"""
    args = parse_args()

    # Load config
    config = load_config()

    # Create game state
    game_state = GameState()

    # Store CLI args in game state
    if args.room_id:
        game_state["room_id_override"] = args.room_id
    game_state["headless_mode"] = args.headless

    if args.headless:
        # Headless mode
        print("Running in headless mode (no GUI)")
        asyncio.run(run_bot(config, game_state, headless=True))
    else:
        # GUI mode - run websocket in thread
        def run_websocket_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(run_bot(config, game_state, headless=False))

        ws_thread = threading.Thread(target=run_websocket_thread, daemon=True)
        ws_thread.start()

        # Start GUI
        root = tk.Tk()
        app = MagicGardenGUI(root, game_state)
        root.mainloop()


if __name__ == "__main__":
    main()
```

**Dependencies:**
- All modules created in previous phases
- Clean orchestration of components

---

## Migration Strategy

### For Each Remaining Phase:

1. **Create the new module file**
2. **Copy functions from bot_gui.py with minimal changes**
3. **Update function signatures** to take parameters instead of using globals
4. **Update imports** in the new module
5. **Test compilation:** `python -m py_compile <module>.py`
6. **Test imports:** `python -c "from <module> import ..."`
7. **Commit the phase:** `git add <files> && git commit -m "Phase X: ..."`

### Final Integration:

1. **Update bot_gui.py** to import from new modules (temporary step)
2. **Test that bot still runs** with old entry point
3. **Switch entry point** to `app.py`
4. **Remove/archive bot_gui.py**
5. **Update README** with new structure
6. **Final commit:** "Complete refactoring - delete bot_gui.py"

---

## Testing Checklist

After each phase:
- ✓ Module compiles: `python -m py_compile <module>.py`
- ✓ Imports work: `python -c "from <module> import ..."`
- ✓ No circular dependencies
- ✓ Type hints are correct

After Phase 7:
- ✓ Bot runs in GUI mode: `python app.py`
- ✓ Bot runs in headless mode: `python app.py --headless`
- ✓ Bot can connect to rooms
- ✓ Automation tasks run (harvest, pets, shop)
- ✓ GUI updates correctly
- ✓ No console errors

---

## Expected File Structure

```
garden-bot/
├── app.py                      # Entry point (~50 lines)
├── config.py                   # Config management (218 lines) ✓
├── game_state.py              # State container (337 lines) ✓
├── bot_config.json            # User config
├── bot_config.example.json    # Example config
├── requirements.txt
├── README.md
│
├── utils/
│   ├── __init__.py            ✓
│   ├── constants.py           # Constants (22 lines) ✓
│   └── coordinates.py         # Coord utils (107 lines) ✓
│
├── network/
│   ├── __init__.py            ✓
│   ├── protocol.py            # Protocol layer (369 lines) ✓
│   └── client.py              # WebSocket client (~450 lines)
│
├── automation/
│   ├── __init__.py
│   ├── harvest.py             # Auto-harvest (~180 lines)
│   ├── pets.py                # Pet feeding/movement (~260 lines)
│   └── shop.py                # Shop auto-buy (~215 lines)
│
└── ui/
    ├── __init__.py
    └── gui.py                 # GUI (~1,100 lines)
```

**Total new code:** ~2,800 lines across 13 focused modules
**Original bot_gui.py:** 2,897 lines (will be deleted)

---

## Benefits of Refactored Architecture

### Separation of Concerns
- **Config:** Isolated in `config.py`
- **State:** Centralized in `game_state.py`
- **Protocol:** Network protocol in `network/protocol.py`
- **Client:** Connection management in `network/client.py`
- **Automation:** Business logic in `automation/*`
- **UI:** Display logic in `ui/gui.py`
- **App:** Orchestration in `app.py`

### Testability
- Each module can be unit tested independently
- Mock GameState for testing automation
- Mock client for testing without network
- Test protocol without GUI

### Maintainability
- Average module size: ~200-300 lines (except GUI)
- Clear responsibility for each file
- Easy to find and modify code
- No global state (except game_state singleton)

### Extensibility
- Easy to add new automation tasks
- Easy to add new UI views
- Easy to support different game modes
- Protocol changes isolated to one module

---

## Current Progress

### Completed (762 lines extracted):
- ✓ Phase 1: Config layer
- ✓ Phase 2: Protocol layer
- ✓ Phase 3: Utilities layer
- ✓ Commit 8f56de6

### Remaining (~2,100 lines to extract):
- Phase 4: Network client (~450 lines)
- Phase 5: Automation modules (~655 lines)
- Phase 6: GUI layer (~1,100 lines)
- Phase 7: App entry point (~50 lines)

### Estimated Time:
- Phase 4: 1-2 hours
- Phase 5: 1-2 hours
- Phase 6: 2-3 hours
- Phase 7: 30 minutes
- Testing & integration: 1 hour

**Total:** 6-9 hours of focused work

---

## Notes

- Keep `game_state` as singleton (already thread-safe with RLock)
- Pass `GameState` instance to all modules that need it
- Config passed explicitly to each module (no globals)
- Client owns websocket, automation calls client.send()
- GUI only reads state, doesn't send messages directly
- All automation tasks registered with client for lifecycle management
