# Magic Garden Bot

A bot for Magic Garden that connects via WebSocket, provides real-time game state visualization, and automates gameplay tasks.

## Quick Start

### GUI Mode (Recommended)

```bash
python app.py
```

Launches the full graphical interface with:
- **Live world map** - Visual grid showing your position, pets, and other players
- **Garden viewer** - See your actual garden with crops and growth stages
- **Real-time inventory** - Seeds, tools, pets, eggs with quantities
- **Statistics dashboard** - Message counts, connection status
- **Three-panel layout** - World view, Garden view, Stats/Inventory

### Headless Mode

```bash
python app.py --headless
```

Runs automation without GUI - perfect for running in background or on servers.

### Custom Room

```bash
python app.py --room-id MG1
```

Join a specific room instead of the default.

## Architecture

The bot uses a modular architecture:

- **`app.py`** - Main entry point
- **`config.py`** - Configuration management (loads `bot_config.json`)
- **`game_state.py`** - Thread-safe game state management
- **`network/client.py`** - WebSocket client and connection handling
- **`network/protocol.py`** - Message processing and protocol logic
- **`automation/`** - Automated gameplay modules:
  - `harvest.py` - Auto-harvest and replant crops
  - `pets.py` - Pet feeding and movement
  - `shop.py` - Automatic seed/egg purchasing
- **`ui/gui.py`** - Tkinter GUI interface
- **`utils/`** - Coordinate conversion, validation, etc.

## Features

### Core Functionality
✅ **WebSocket connection** - Full game protocol support
✅ **Thread-safe state management** - Proper locking for concurrent access
✅ **Automatic message logging** - All WebSocket traffic saved to `messages.log`
✅ **Persistent player ID** - Saved in `bot_config.json`
✅ **Real-time updates** - UI refreshes on every game state change
✅ **Emulates browser behavior** - Proper pings, pongs, position updates

### Automation Features
✅ **Auto-harvest** - Automatically harvest mature crops, replant, and sell
  - Enable/disable via config
  - Configurable species list to auto-harvest
  - Separate list for species that need replanting (perennials like Bamboo/Sunflower vs annuals like Carrot/Tomato)
  - Configurable minimum mutations (e.g., only harvest crops with 3+ mutations)
  - Prioritizes highest mutation count when selling
  - Harvests ALL ready plants of each species (not just one)
  - Automatically sells all harvested crops after each cycle
  - Configurable check interval
✅ **Pet automation** - Feed hungry pets and move them around garden
  - Configurable food limits per species
  - Random movement within garden bounds
✅ **Shop automation** - Auto-purchase seeds and eggs when low
  - Configurable minimum stock levels
  - Coin balance checking

### Protocol Support

The bot emulates proper client behavior:

1. **Connection** - VoteForGame, SetSelectedGame, authentication
2. **Periodic** - Ping/Pong (every 2s), PlayerPosition updates
3. **Gameplay** - PlantSeed, Harvest, FeedPet, BuyItem, PetPositions
4. **State tracking** - FullState, PartialState (JSON patches)

## Configuration

Edit `bot_config.json` to customize behavior:

```json
{
  "playerId": "your-persistent-id",
  "cookies": "your-magicgarden.gg-cookies",
  "ready_to_harvest": {
    "enabled": true,
    "species": ["Sunflower", "Bamboo", "Carrot", "Tomato"],  // All species to auto-harvest
    "species_to_replant": ["Carrot", "Tomato"],  // Only replant annuals (perennials like Sunflower/Bamboo keep growing)
    "min_mutations": 3,  // Only harvest crops with 3+ mutations
    "check_interval_seconds": 30  // Check for harvestable crops every 30 seconds
  },
  "pet_food_mapping": {
    "Bee": ["Lily", "Daffodil"],
    "Chicken": ["Aloe"],
    "Worm": ["Aloe"]
  },
  "shop": {
    "enabled": true,
    "check_interval_seconds": 60,
    "min_coins_to_keep": 1000,
    "items_to_buy": {
      "seeds": {
        "enabled": true,
        "items": ["Carrot", "Tomato"]
      },
      "eggs": {
        "enabled": true,
        "items": ["CommonEgg", "UncommonEgg"]
      }
    }
  },
  "reconnection": {
    "max_retries": 5,
    "base_delay": 5,
    "max_delay": 60
  }
}
```

## Debugging

All WebSocket traffic is logged to `messages.log`:
- Sent and received messages
- Timestamps
- Full JSON payloads
- Protocol events (Welcome, PartialState, etc.)

Perfect for debugging and understanding the game protocol!

## Legacy Files

⚠️ **`bot_gui.py`** is a legacy monolithic version from before the refactoring. Use `app.py` instead for the current modular architecture with proper separation of concerns.
