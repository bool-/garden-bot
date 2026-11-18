"""
Magic Garden Bot - Application Entry Point

Main application that orchestrates the bot, automation tasks, and GUI.
"""

import asyncio
import argparse
import threading
import sys

# Windows consoles default to cp1252, which crashes on the status glyphs we print.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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
    parser.add_argument(
        "--serve", action="store_true",
        help="Also run the remote control API (bind/port/token from bot_config.json 'remote')",
    )
    parser.add_argument(
        "--remote", type=str, metavar="URL",
        help="Open only the window and control a bot running elsewhere, e.g. http://100.122.51.56:8765",
    )
    parser.add_argument("--token", type=str, help="Token for --remote (or GARDEN_BOT_TOKEN env var)")
    return parser.parse_args()


def remote_settings(config) -> dict:
    """bind/port/token for the control API; creates and saves a token once."""
    import json as _json
    import secrets
    from utils.constants import CONFIG_FILE

    remote = dict(config.remote or {})
    remote.setdefault("bind", "127.0.0.1")
    remote.setdefault("port", 8765)
    if not remote.get("token"):
        remote["token"] = secrets.token_urlsafe(24)
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                raw = _json.load(f)
            raw["remote"] = remote
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                _json.dump(raw, f, indent=2)
            print(f"Created a remote API token in {CONFIG_FILE} (remote.token)")
        except OSError as e:
            print(f"Could not save the remote token: {e}")
    return remote


def run_remote_window(url: str, token: str):
    """Window only: watch and steer a bot that runs somewhere else."""
    from PyQt6.QtWidgets import QApplication
    from ui.qt_gui import MagicGardenGUI
    from ui.remote_source import RemoteBrain, RemoteClient, RemoteGameState, RemoteSource

    source = RemoteSource(url, token)
    holder = {"client": RemoteClient(source), "brain": RemoteBrain(source), "remote": source}
    app = QApplication(sys.argv)
    window = MagicGardenGUI(RemoteGameState(source), None, client_holder=holder)
    window.setWindowTitle(f"Garden Bot (remote: {url})")
    window.show()
    code = app.exec()
    source.stop()
    sys.exit(code)


async def run_bot(config, game_state, headless=False, client_holder=None, serve=False):
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

    if (config.brain or {}).get("enabled"):
        from automation import economy, gamedata
        from automation.brain import Brain

        # Keep the game tables in step with the live build before playing.
        room = game_state.get("room_id_override") or config.last_room or "MG1"
        await asyncio.to_thread(gamedata.ensure_current, room)
        economy.reload()

        print("Brain enabled: feeding, shopping, selling, harvesting and planting on one loop")
        brain = Brain(client, game_state, config.brain)
        if client_holder is not None:
            client_holder["brain"] = brain
        client.register_task(lambda: brain.run())
        server = None
        if serve:
            from automation.remote import RemoteServer

            remote = remote_settings(config)
            server = RemoteServer(client, game_state, brain, remote["token"])
            await server.start(remote["bind"], int(remote["port"]))
        try:
            await client.run()
        finally:
            if server:
                await server.stop()
            await client.close_http()
        return

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

    if args.remote:
        import os

        token = args.token or os.environ.get("GARDEN_BOT_TOKEN", "")
        if not token:
            print("--remote needs --token or the GARDEN_BOT_TOKEN environment variable")
            return
        run_remote_window(args.remote, token)
        return

    # Load config
    try:
        config = load_config()
    except RuntimeError as exc:
        print(f"\nConfiguration error: {exc}")
        print("Update bot_config.json and restart the bot.")
        return

    from network.protocol import set_log_mode
    set_log_mode(config.message_log)

    # Create game state
    game_state = GameState()

    # Store CLI args in game state
    if args.room_id:
        game_state["room_id_override"] = args.room_id
    game_state["headless_mode"] = args.headless

    if args.headless:
        # Headless mode
        print("Running in headless mode (no GUI)")
        asyncio.run(run_bot(config, game_state, headless=True, serve=args.serve))
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
                loop.run_until_complete(run_bot(config, game_state, headless=False,
                                                client_holder=client_holder, serve=args.serve))

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
