"""
Magic Garden Bot - Application Entry Point

Main application that orchestrates the bot, automation tasks, and GUI.
"""

import asyncio
import argparse
import threading

from config import load_config
from game_state import GameState
from network.client import MagicGardenClient
from automation import harvest, pets, shop


def parse_args():
    """
    Parse command line arguments.

    Returns:
        argparse.Namespace with parsed arguments
    """
    parser = argparse.ArgumentParser(description="Magic Garden Bot")
    parser.add_argument(
        "--room-id", type=str, help="Override room ID to join (e.g., MG1)"
    )
    parser.add_argument(
        "--headless", action="store_true", help="Run in headless mode (no GUI)"
    )
    return parser.parse_args()


async def run_bot(config, game_state, headless=False):
    """
    Run the bot (headless or with GUI).

    Args:
        config: Bot configuration
        game_state: Global game state
        headless: Whether running in headless mode
    """
    # Create client
    client = MagicGardenClient(game_state, config)

    # Register automation tasks
    client.register_task(
        harvest.run_auto_harvest(client, game_state, config.harvest)
    )
    client.register_task(pets.run_pet_feeder(client, game_state, config.pet_food))
    client.register_task(pets.run_pet_mover(client, game_state))
    client.register_task(shop.run_shop_buyer(client, game_state, config.shop))

    # Run client
    await client.run()


def main():
    """Application entry point."""
    args = parse_args()

    # Load config
    try:
        config = load_config()
    except RuntimeError as exc:
        print(f"\nConfiguration error: {exc}")
        print("Update bot_config.json and restart the bot.")
        return

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
        # GUI mode - import tkinter and GUI (only when needed)
        import tkinter as tk
        from ui.gui import MagicGardenGUI

        # Run websocket in thread
        def run_websocket_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(run_bot(config, game_state, headless=False))

        ws_thread = threading.Thread(target=run_websocket_thread, daemon=True)
        ws_thread.start()

        # Start GUI
        root = tk.Tk()
        app = MagicGardenGUI(root, game_state, config.harvest)
        root.mainloop()


if __name__ == "__main__":
    main()
