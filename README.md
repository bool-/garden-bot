# Magic Garden Bot

A bot for Magic Garden that connects via WebSocket and provides real-time game state visualization.

## Files

### `bot_gui.py` (GUI Version) ⭐ **RECOMMENDED**
**Full graphical interface with tkinter!**
- **Live world map** - Visual grid showing your position, pets, and other players
- **Garden viewer** - See your actual garden with crops and growth stages
- **Real-time inventory** - Seeds, tools, pets, eggs with quantities
- **Statistics dashboard** - Message counts, connection status
- **Three-panel layout** - World view, Garden view, Stats/Inventory
- **All messages logged to `messages.log`** for debugging

### `bot.py` (Original)
Basic bot with detailed console logging. Shows all game state on startup.

### `bot_v2.py` (Clean Terminal UI)
- **All messages logged to `messages.log`**
- **Clean dashboard UI** with inventory, stats, and garden info
- **Live statistics** tracking
- **Automatic ping/pong handling**

### `bot_v3.py` (ASCII Game Viewer)
Everything from v2, plus:
- **Visual garden view** - See your crops with growth stages (🌰 → 🌱 → 🌿 → 🌾)
- **World minimap** - 40x15 view showing:
  - 🐱 Your position
  - 🐾 Pet locations
  - 👤 Other players
- **Real-time updates** as you play
- **Two-column layout** - Game view on left, stats on right

## Usage

```bash
# Run the GUI version (recommended!)
python bot_gui.py

# Run the ASCII game viewer
python bot_v3.py

# Run the clean UI version
python bot_v2.py

# Run the original
python bot.py
```

## Features

✅ **Automatic message logging** - All WebSocket messages saved to `messages.log`
✅ **Persistent player ID** - Saved in `bot_config.json`
✅ **Real-time updates** - UI refreshes on every game state change
✅ **Clean console output** - Only shows relevant game info
✅ **Emulates browser behavior** - Sends proper pings, pet positions, etc.

## What the bot does

Based on the HAR file analysis, the bot emulates these client behaviors:

1. **Initial connection**:
   - VoteForGame (Quinoa)
   - SetSelectedGame (Quinoa)

2. **Periodic messages** (every 2 seconds):
   - Ping messages with timestamp ID
   - Pong responses to server pings

3. **As needed**:
   - PlayerPosition updates
   - PetPositions updates
   - SetSelectedItem

4. **Tracks everything**:
   - Inventory (coins, seeds, tools, pets, eggs)
   - Garden state (planted crops, growth stages)
   - Player positions (you and others)
   - Pet positions in the world
   - Room info

## Game Viewer Display

```
╔══════════════════════════════════════════════════════════════════════════════════════════════════╗
║                              🪴 Magic Garden Bot - Live Game Viewer 🪴                            ║
╚══════════════════════════════════════════════════════════════════════════════════════════════════╝

┌─ PLAYER INFO ──────────────────────────┐  ┌─ INVENTORY ───────────────────────────┐
│ YourName                               │  │ 💰 Coins: 1250                        │
│ Pos: (66, 25)                         │  │                                        │
│ Garden: 5x5                           │  │ 🌱 Seeds:                              │
└───────────────────────────────────────┘  │   Carrot: 10                          │
                                            │   Tomato: 5                           │
┌─ WORLD VIEW ──────────────────────────┐  │                                        │
│                                        │  │ 🔧 Tools:                              │
│          🐾                           │  │   Watering Can: 1                     │
│                                        │  │                                        │
│             🐱                        │  │ 🐾 Pets:                               │
│                                        │  │   Cat: 3                              │
│        👤                             │  │                                        │
│                   🐾                  │  │ 🥚 Eggs: None                          │
│                                        │  └────────────────────────────────────────┘
│                                        │
└────────────────────────────────────────┘  ┌─ ROOM ────────────────────────────────┐
                                            │ Game: Quinoa                          │
┌─ YOUR GARDEN ─────────────────────────┐  │ Players: 3                            │
│ 🌾 🌿 □  □  □                        │  └────────────────────────────────────────┘
│ 🌱 🌾 □  □  □                        │
│ □  □  □  🌰 □                        │  ┌─ STATS ───────────────────────────────┐
│ □  □  □  □  □                        │  │ Msgs Sent: 42                         │
│ □  □  □  □  □                        │  │ Msgs Recv: 156                        │
└────────────────────────────────────────┘  │ Pings: 21                             │
                                            │ Log: messages.log                     │
Last Update: 14:23:45                       └────────────────────────────────────────┘
```

## Debugging

Check `messages.log` for all WebSocket traffic:
- Every sent message
- Every received message
- Timestamps
- Full JSON data

Perfect for debugging and understanding the game protocol!
