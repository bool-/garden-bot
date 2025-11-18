"""
WebSocket client for Magic Garden game.

Handles connection lifecycle, authentication, room joining,
message sending/receiving, and running automation tasks.
"""

import asyncio
import json
import traceback
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List, Callable

import aiohttp
import websockets

from game_state import GameState
from config import BotConfig, save_last_room, save_cookies
from network.protocol import (
    process_message,
    process_welcome_message,
    log_message_to_file,
    is_player_in_room_state,
    apply_json_patch,
    GardenFullError,
)
from utils.constants import MESSAGE_LOG_FILE, SPAWN_POSITIONS, GAME_VERSION


class MagicGardenClient:
    """
    WebSocket client for Magic Garden game.
    Handles connection, authentication, room joining, and message handling.
    """

    def __init__(self, game_state: GameState, config: BotConfig):
        """
        Initialize the client.

        Args:
            game_state: Global game state instance
            config: Bot configuration
        """
        self.game_state = game_state
        self.config = config
        self.websocket = None
        self.task_factories: List[Callable] = []  # Functions that create tasks
        self.player_id = config.player_id
        self.cookies = config.cookies
        self.spawn_pos = None

        # Connection lifecycle management
        self._connected = asyncio.Event()
        self._disconnect_requested = asyncio.Event()
        self._connection_id = 0  # Incremented on each new connection

    @property
    def is_connected(self) -> bool:
        """Check if the client is currently connected to the server."""
        return self.websocket is not None and self._connected.is_set()

    def _signal_disconnect(self):
        """Signal that the connection has been lost."""
        self._connected.clear()
        self._disconnect_requested.set()
        print("\n" + "!" * 60)
        print("CONNECTION LOST - Automation tasks will pause...")
        print("!" * 60 + "\n")

    async def authenticate(self, room_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Authenticate with server for a specific room.

        Args:
            room_id: Room ID to authenticate for (e.g., "MG1")

        Returns:
            Tuple of (auth_data, updated_cookies) or (None, None) on failure
        """
        auth_url = f"https://magicgarden.gg/version/{GAME_VERSION}/api/rooms/{room_id}/user/authenticate-web"
        headers = {
            "accept": "*/*",
            "content-type": "application/json",
            "origin": "https://magicgarden.gg",
            "referer": f"https://magicgarden.gg/r/{room_id}",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "cookie": self.cookies,
        }
        payload = {"provider": "maybe-existing-jwt"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(auth_url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        updated_cookies = self.cookies

                        if "Set-Cookie" in response.headers:
                            set_cookie = response.headers.get("Set-Cookie")
                            new_cookie = set_cookie.split(";")[0]
                            cookie_dict = {}
                            for cookie_pair in self.cookies.split("; "):
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
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            print(f"  Network error during authentication: {e}")
            return None, None

    async def try_room(
        self, room_id: str, headers: Dict[str, str]
    ) -> Tuple[Optional[Any], Optional[Dict], Optional[str]]:
        """
        Try to connect to a specific room and check if player is in it.

        Args:
            room_id: Room ID to connect to (e.g., "MG1")
            headers: HTTP headers with authentication cookies

        Returns:
            Tuple of (websocket, welcome_data, room_id) or (None, None, None) on failure
        """
        url = f"wss://magicgarden.gg/version/{GAME_VERSION}/api/rooms/{room_id}/connect?surface=%22web%22&platform=%22desktop%22&playerId=%22{self.player_id}%22&version=%22{GAME_VERSION}%22&source=%22manualUrl%22&capabilities=%22fbo_mipmap_unsupported%22"

        print(f"\nTrying room {room_id}...")

        try:
            # Connect WITHOUT async with so we can keep the connection open
            websocket = await websockets.connect(
                url, additional_headers=headers, compression="deflate"
            )

            # Send initial messages
            await self._send_message_raw(
                websocket,
                {"scopePath": ["Room"], "type": "VoteForGame", "gameName": "Quinoa"},
            )
            await self._send_message_raw(
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

                    print(f"\n  Looking for player ID: {self.player_id}")

                    if is_player_in_room_state(full_state, self.player_id):
                        # Check if garden (Quinoa game) is full before committing to this room
                        quinoa_state = full_state.get("child", {}).get("data", {})
                        if quinoa_state:
                            user_slots = quinoa_state.get("userSlots", [])
                            # Count occupied slots (non-empty)
                            occupied_slot_count = sum(1 for slot in user_slots if slot)
                            if occupied_slot_count == 6:
                                # All 6 slots occupied, check if we have one
                                our_slot_found = any(
                                    slot and slot.get("playerId") == self.player_id
                                    for slot in user_slots
                                )
                                if not our_slot_found:
                                    print(f"  ✗ Garden full: All 6 slots occupied by other players")
                                    await websocket.close()
                                    return None, None, None

                        print(f"  ✓ Found player in room {room_id}!")
                        # Return the open websocket connection and the FULL Welcome message
                        return websocket, data, room_id

                    print(
                        "  Player not present in Welcome response; waiting briefly for updates..."
                    )
                    loop = asyncio.get_running_loop()
                    wait_deadline = loop.time() + 3.0

                    while True:
                        remaining = wait_deadline - loop.time()
                        if remaining <= 0:
                            break

                        try:
                            followup = await asyncio.wait_for(
                                websocket.recv(), timeout=remaining
                            )
                        except asyncio.TimeoutError:
                            break

                        if isinstance(followup, str) and followup.strip().lower() == "ping":
                            await websocket.send("pong")
                            continue

                        try:
                            follow_data = json.loads(followup)
                        except json.JSONDecodeError:
                            continue

                        msg_type = follow_data.get("type")
                        if msg_type == "PartialState":
                            patches = follow_data.get("patches") or []
                            for patch in patches:
                                try:
                                    apply_json_patch(full_state, patch)
                                except Exception as patch_err:
                                    print(
                                        f"  Error applying patch while waiting for player: {patch_err}"
                                    )
                            if is_player_in_room_state(full_state, self.player_id):
                                print(
                                    f"  ✓ Found player in room {room_id} after server updates!"
                                )
                                return websocket, data, room_id
                        elif msg_type == "Welcome":
                            new_state = follow_data.get("fullState")
                            if not new_state:
                                continue
                            data = follow_data
                            full_state = new_state
                            if is_player_in_room_state(full_state, self.player_id):
                                print(
                                    f"  ✓ Found player in room {room_id} after updated Welcome!"
                                )
                                return websocket, data, room_id

                    # Check if garden is full before giving up
                    quinoa_state = full_state.get("child", {}).get("data", {})
                    if quinoa_state:
                        user_slots = quinoa_state.get("userSlots", [])
                        # Count occupied slots (non-empty)
                        occupied_slot_count = sum(1 for slot in user_slots if slot)
                        if occupied_slot_count == 6:
                            our_slot_found = any(
                                slot and slot.get("playerId") == self.player_id
                                for slot in user_slots
                            )
                            if not our_slot_found:
                                print(f"  ✗ Garden full: All 6 slots occupied by other players")
                                await websocket.close()
                                return None, None, None

                    latest_players = full_state.get("data", {}).get("players", []) or []
                    actual_player_count = sum(
                        1 for slot in latest_players if slot is not None
                    )
                    print(
                        f"  Player not in room {room_id} after waiting ({actual_player_count}/6 players)"
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

    async def _send_message_raw(self, websocket, message: Dict[str, Any]):
        """
        Send a message to the server (internal helper that doesn't log or track stats).

        Args:
            websocket: WebSocket connection
            message: Message to send
        """
        await websocket.send(json.dumps(message))

    async def send(self, message: Dict[str, Any]):
        """
        Send a message to the server.

        Args:
            message: Message dict to send

        Raises:
            RuntimeError: If not connected to server
        """
        if not self.is_connected:
            raise RuntimeError(
                "Not connected to server - connection has been lost. "
                "Automation tasks should exit gracefully."
            )

        await self.websocket.send(json.dumps(message))
        self.game_state.increment_stat("messages_sent")
        log_message_to_file("SENT", message)

    async def send_ping(self):
        """Send a ping message to the server."""
        ping_id = int(datetime.now().timestamp() * 1000)
        ping_message = {"scopePath": ["Room", "Quinoa"], "type": "Ping", "id": ping_id}
        await self.send(ping_message)
        self.game_state.increment_stat("pings_sent")

    def register_task(self, task_factory):
        """
        Register an automation task factory to create tasks on each connection.

        Args:
            task_factory: A function that returns a coroutine when called
        """
        self.task_factories.append(task_factory)

    async def _receive_messages(self):
        """
        Receive and process messages from the server.
        Internal task that runs in the background.
        """
        try:
            async for message in self.websocket:
                if message.strip().lower() == "ping":
                    self.game_state.increment_stat("pings_received")
                    await self.websocket.send("pong")
                    self.game_state.increment_stat("pongs_sent")
                    log_message_to_file("SENT", "pong")
                    continue
                process_message(message, self.game_state)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            # Signal disconnect when receive loop exits for any reason
            self._signal_disconnect()

    async def _ping_task(self):
        """
        Send pings periodically.
        Exits gracefully when connection is lost.
        """
        while self.is_connected:
            await asyncio.sleep(2)
            if not self.is_connected:
                break
            try:
                await self.send_ping()
            except RuntimeError:
                # Connection lost, exit gracefully
                break
            except Exception as e:
                print(f"Error in ping task: {e}")
                break

    async def connect(self):
        """
        Connect to Magic Garden server and find available room.

        Returns:
            True if connected successfully, False otherwise
        """
        # Initialize message log
        with open(MESSAGE_LOG_FILE, "w", encoding="utf-8") as f:
            f.write(f"Magic Garden Bot - Message Log\n")
            f.write(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        print("=" * 60)
        print("MAGIC GARDEN BOT - STARTING")
        print("=" * 60)

        # Set player ID in game state
        self.game_state["player_id"] = self.player_id
        print(f"\nPlayer ID: {self.player_id}")

        # Check for room override
        room_id_override = self.game_state.get("room_id_override")
        last_room = self.config.last_room
        search_main_rooms = self.config.search_main_rooms

        # Determine which rooms to try
        all_rooms = [f"MG{num}" for num in range(1, 16)] if search_main_rooms else []

        def prioritize_room(preferred_room, rooms):
            if not preferred_room:
                return rooms
            ordered = [preferred_room]
            for room in rooms:
                if room != preferred_room:
                    ordered.append(room)
            return ordered

        if room_id_override:
            if search_main_rooms:
                print(
                    f"\nUsing room from --room-id parameter first (falling back to others if needed): {room_id_override}"
                )
                rooms_to_try = prioritize_room(room_id_override, all_rooms)
            else:
                print(
                    f"\nUsing room from --room-id parameter (main room searching disabled): {room_id_override}"
                )
                rooms_to_try = [room_id_override]
        elif last_room:
            if search_main_rooms:
                print(
                    f"\nTrying last connected room first (will fall back to others if busy): {last_room}"
                )
                rooms_to_try = prioritize_room(last_room, all_rooms)
            else:
                print(
                    f"\nUsing last connected room only (main room searching disabled): {last_room}"
                )
                rooms_to_try = [last_room]
        else:
            if search_main_rooms:
                print("\nSearching for available room...")
                rooms_to_try = all_rooms
            else:
                print("\nERROR: No room specified and main room searching is disabled!")
                print("Either enable search_main_rooms in config or specify a room with --room-id")
                return False

        # Try rooms
        websocket = None
        welcome_data = None
        connected_room = None
        base_cookies = self.cookies

        for room_id in rooms_to_try:
            print(f"\n[Room {room_id}] Authenticating...")

            # Authenticate for this specific room
            auth_data, updated_cookies = await self.authenticate(room_id)

            if not auth_data or not updated_cookies:
                print(f"  ✗ Authentication failed for {room_id}")
                continue

            print(f"  ✓ Authentication successful for {room_id}")

            if updated_cookies != base_cookies:
                save_cookies(updated_cookies)
                base_cookies = updated_cookies
                self.cookies = updated_cookies

            # Set up headers with authenticated cookies
            headers = {
                "Origin": "https://magicgarden.gg",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Cookie": updated_cookies,
            }

            # Try to connect to this room
            ws, data, room = await self.try_room(room_id, headers)

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
            if search_main_rooms:
                print("All rooms (MG1-MG15) are full or unreachable.")
            else:
                print(f"The specified room '{rooms_to_try[0] if rooms_to_try else 'N/A'}' is full or unreachable.")
                print("Try enabling search_main_rooms in config to search other rooms.")
            print("!" * 60)
            return False

        print(f"\n{'='*60}")
        print(f"CONNECTED TO ROOM: {connected_room}")
        print(f"{'='*60}\n")

        # Store websocket and room ID
        self.websocket = websocket
        self.game_state["room_id"] = connected_room

        # Increment connection ID for this new connection
        self._connection_id += 1

        # Signal successful connection
        self._connected.set()

        # Process the welcome message and store spawn position
        self.spawn_pos = process_welcome_message(welcome_data, self.game_state)

        return True

    async def _startup_task(self):
        """
        Handle initialization that requires receiving messages.
        Sends initial player position to server.
        """
        from automation.pets import wait_for_user_slot, initialize_pets

        # Wait for user slot to be populated (requires message processing to be active)
        slot_available = True
        spawn_pos_updated = self.spawn_pos

        if self.game_state.get("user_slot_index") is None:
            slot = await wait_for_user_slot(self.game_state, timeout=10.0)
            slot_available = slot is not None
            if slot_available and self.game_state.get("user_slot_index") is not None:
                spawn_pos_updated = SPAWN_POSITIONS[
                    self.game_state["user_slot_index"]
                ].copy()

        # Send PlayerPosition message with spawn position
        if spawn_pos_updated and slot_available:
            position_message = {
                "scopePath": ["Room", "Quinoa"],
                "type": "PlayerPosition",
                "position": spawn_pos_updated,
            }
            await self.send(position_message)
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
        await initialize_pets(self, self.game_state)

    async def _run_session(self):
        """
        Run a single connection session.
        Returns True if the session completed due to connection loss (eligible for retry).
        Returns False if there was a critical error.
        """
        # Create asyncio tasks (not just coroutines)
        tasks = []

        try:
            # Create and start all tasks
            tasks.append(asyncio.create_task(self._receive_messages()))
            tasks.append(asyncio.create_task(self._startup_task()))
            tasks.append(asyncio.create_task(self._ping_task()))

            # Create fresh instances of registered automation tasks
            for factory in self.task_factories:
                tasks.append(asyncio.create_task(factory()))

            # Wait for the receive task to complete (it exits when connection closes)
            # The receive task is always the first one
            await tasks[0]

            # Connection lost - cancel all other tasks
            for task in tasks[1:]:
                if not task.done():
                    task.cancel()

            # Wait for all tasks to finish cancellation
            await asyncio.gather(*tasks[1:], return_exceptions=True)

            return True

        except Exception as e:
            # Cancel all tasks on error
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

            print(f"Error in session: {e}")
            print(f"Traceback: {traceback.format_exc()}")
            return False

    async def run(self):
        """
        Run the client (main entry point).
        Connects to the server and runs all registered automation tasks.
        Automatically attempts reconnection on connection loss.
        """
        try:
            retry_count = 0
            max_retries = self.config.reconnection.max_retries
            base_delay = self.config.reconnection.base_delay
            max_delay = self.config.reconnection.max_delay

            await self._run_with_reconnection(retry_count, max_retries, base_delay, max_delay)
        except Exception as e:
            print(f"\n[FATAL ERROR] Unhandled exception in run(): {e}")
            print(f"Traceback: {traceback.format_exc()}")
            raise

    async def _run_with_reconnection(self, retry_count, max_retries, base_delay, max_delay):
        """Internal reconnection loop."""
        while True:
            # Connect to server
            if not await self.connect():
                if retry_count >= max_retries:
                    print("\n" + "!" * 60)
                    print("FAILED TO CONNECT - Max retries reached")
                    print("!" * 60)
                    return

                # Failed initial connection, wait and retry
                retry_count += 1
                delay = min(base_delay * (2 ** (retry_count - 1)), max_delay)
                print(f"\nRetrying connection in {delay} seconds... (attempt {retry_count}/{max_retries})")
                await asyncio.sleep(delay)
                continue

            # Reset retry count on successful connection
            if retry_count > 0:
                print(f"\n{'='*60}")
                print(f"RECONNECTION SUCCESSFUL!")
                print(f"{'='*60}\n")
            retry_count = 0

            # Run the session
            session_ok = await self._run_session()

            # Check if we should attempt reconnection
            if not self.is_connected:
                # Connection was lost
                if retry_count >= max_retries:
                    print("\n" + "!" * 60)
                    print("MAX RECONNECTION ATTEMPTS REACHED - Shutting down permanently")
                    print("!" * 60)
                    return

                # Calculate backoff delay
                retry_count += 1
                delay = min(base_delay * (2 ** (retry_count - 1)), max_delay)

                print("\n" + "=" * 60)
                print(f"ATTEMPTING RECONNECTION...")
                print(f"Retry {retry_count}/{max_retries} - Waiting {delay} seconds")
                print("=" * 60 + "\n")

                await asyncio.sleep(delay)

                # Reset connection state for next attempt
                self._disconnect_requested.clear()
                self.websocket = None

                # Continue to next iteration to reconnect
                continue
            else:
                # Session ended normally (shouldn't happen in normal operation)
                break
