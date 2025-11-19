# Magic Garden Bot

> **⚠️ EDUCATIONAL USE ONLY**
> This project is created strictly for educational purposes to demonstrate WebSocket protocols, bot automation techniques, and GUI development with Python. Use of automation tools may violate the terms of service of Magic Garden. The authors do not condone or encourage the use of this software to gain unfair advantages in the game. Use at your own risk.

A bot for Magic Garden that connects via WebSocket, provides real-time game state visualization, and automates gameplay tasks.

## Quick Start

### Installation

```bash
pip install -r requirements.txt
```

### GUI Mode (Recommended)

**PyQt6 UI (Default):**
```bash
python app.py
```

Launches the modern PyQt6 interface with:
- **VS Code Dark+ theme** - Professional dark theme inspired by VS Code
- **Fully responsive design** - Resizable window and panels
- **Garden visualization** - Real-time garden grid with dynamic scaling
- **Tabbed interface** - Inventory, Pets, Shop, Journal, and Stats tabs
- **Live console** - Real-time bot activity logging
- **Connection info** - Player position and network statistics

**Tkinter UI (Legacy):**
```bash
python app.py --ui tkinter
```

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
- **`ui/`** - User interface modules:
  - `qt_gui.py` - Modern PyQt6 interface (default)
  - `qt_components/` - Modular UI components (garden, inventory, pets, etc.)
  - `gui.py` - Legacy Tkinter interface
- **`utils/`** - Coordinate conversion, validation, etc.

## Features

### Core Functionality

- ✅ **WebSocket connection** - Full game protocol support
- ✅ **Thread-safe state management** - Proper locking for concurrent access
- ✅ **Automatic message logging** - All WebSocket traffic saved to `messages.log`
- ✅ **Persistent player ID** - Saved in `bot_config.json`
- ✅ **Real-time updates** - UI refreshes on every game state change
- ✅ **Emulates browser behavior** - Proper pings, pongs, position updates

### UI Features

**PyQt6 UI (Default):**
- ✅ **VS Code Dark+ theme** - Professional color scheme
- ✅ **Component-based architecture** - Modular, maintainable code
- ✅ **Fully responsive** - Dynamic window and panel resizing
- ✅ **Garden visualization** - Real-time grid with mutation indicators
- ✅ **Tabbed interface** - Inventory, Pets, Shop, Journal, Stats
- ✅ **Copy-friendly panels** - Content updates don't interrupt text selection
- ✅ **Scroll preservation** - Panel scroll position maintained during updates

**Tkinter UI (Legacy):**
- ✅ **Three-panel layout** - World view, Garden view, Stats/Inventory
- ✅ **Simple interface** - Lightweight alternative

### Automation Features

**✅ Auto-harvest** - Automatically harvest mature crops, replant, and sell
- Enable/disable via config
- Configurable species list to auto-harvest
- Separate list for species that need replanting (perennials like Sunflower keep growing, annuals like Carrot/Tomato/Bamboo need replanting)
- Configurable minimum mutations (e.g., only harvest crops with 3+ mutations)
- Prioritizes highest mutation count when selling
- Harvests ALL ready plants of each species (not just one)
- Automatically sells all harvested crops after each cycle
- Configurable check interval

**✅ Pet automation** - Feed hungry pets and move them around garden
- Configurable food limits per species
- Random movement within garden bounds

**✅ Shop automation** - Auto-purchase seeds and eggs when low
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
