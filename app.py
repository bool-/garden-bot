"""
Magic Garden Bot - Application Entry Point

Main application that orchestrates the bot, automation tasks, and GUI.
"""

import asyncio
import argparse
import threading
import sys

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
    parser.add_argument(
        "--ui",
        type=str,
        choices=["tkinter", "qt"],
        default="qt",
        help="Choose UI framework (default: qt)",
    )
    return parser.parse_args()


async def run_bot(config, game_state, headless=False, client_holder=None):
    """
    Run the bot (headless or with GUI).

    Args:
        config: Bot configuration
        game_state: Global game state
        headless: Whether running in headless mode
        client_holder: Optional dict to store client reference for GUI access
    """
    # Create client
    client = MagicGardenClient(game_state, config)

    # Store client reference if holder provided (for GUI thread-safe access)
    if client_holder is not None:
        client_holder["client"] = client
        client_holder["loop"] = asyncio.get_running_loop()

    # Register automation task factories (lambdas that create new task instances)
    client.register_task(
        lambda: harvest.run_auto_harvest(client, game_state, config.harvest)
    )

    # Only register pet automation tasks if enabled
    if config.pet_food.feeding_enabled:
        client.register_task(
            lambda: pets.run_pet_feeder(client, game_state, config.pet_food)
        )
    if config.pet_food.movement_enabled:
        client.register_task(lambda: pets.run_pet_mover(client, game_state))

    client.register_task(lambda: shop.run_shop_buyer(client, game_state, config.shop))

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
        # GUI mode - choose UI framework
        if args.ui == "qt":
            # PyQt6 GUI
            from PyQt6.QtWidgets import QApplication
            from PyQt6.QtGui import QIcon
            from ui.qt_gui import MagicGardenGUI
            import ctypes

            # Set Windows App User Model ID for proper taskbar icon
            if sys.platform == "win32":
                myappid = "magicgarden.bot.client.1.0"
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

            # Holder for client reference (shared between threads)
            client_holder = {}

            # Run websocket in thread
            def run_websocket_thread():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(run_bot(config, game_state, headless=False, client_holder=client_holder))

            ws_thread = threading.Thread(target=run_websocket_thread, daemon=True)
            ws_thread.start()

            # Start Qt GUI
            app = QApplication(sys.argv)

            window = MagicGardenGUI(game_state, config.harvest, client_holder=client_holder)
            window.show()
            sys.exit(app.exec())

        else:  # tkinter
            # Tkinter GUI (legacy)
            import tkinter as tk
            from ui.gui import MagicGardenGUI

            # Run websocket in thread
            def run_websocket_thread():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(run_bot(config, game_state, headless=False))

            ws_thread = threading.Thread(target=run_websocket_thread, daemon=True)
            ws_thread.start()

            # Start tkinter GUI
            root = tk.Tk()
            app = MagicGardenGUI(root, game_state, config.harvest)
            root.mainloop()


if __name__ == "__main__":
    main()
