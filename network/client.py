"""
WebSocket client for Magic Garden game.

Handles connection lifecycle, authentication, room joining,
message sending/receiving, and running automation tasks.
"""

import asyncio
import contextlib
import json
import random
import time
import re
from urllib.parse import quote
import traceback
import uuid
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
from utils.constants import MESSAGE_LOG_FILE, SPAWN_POSITIONS, GAME_VERSION, USER_AGENT


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

        # Mirror the real web client's connect parameters. The device id is
        # persistent (localStorage in a browser); the document id is per page
        # load; the attempt counter increments on every socket the "page" opens.
        self.version = GAME_VERSION
        self.client_device_id = config.client_device_id
        self.client_document_id = str(uuid.uuid4())
        self._connection_attempt = 0

        # One body: harvest walks, shop trips and pet feeding take turns.
        self.body_lock = asyncio.Lock()

        # One shared HTTP session (connection reuse) for auth and page loads.
        self._http: Optional[aiohttp.ClientSession] = None

        # requestId -> inner command, and the commands the server rejected.
        self._sent_commands: Dict[str, Dict[str, Any]] = {}
        self.rejected_commands: List[Dict[str, Any]] = []
        # Session tallies the UI shows.
        self.session_coins_earned = 0
        self.command_ok = 0
        self.command_rejected = 0
        self.rejection_log: List[Dict[str, Any]] = []  # recent rejections: time, what, why

        # Connection lifecycle management
        self._connected = asyncio.Event()
        self._disconnect_requested = asyncio.Event()
        self._connection_id = 0  # Incremented on each new connection

        # Monotonic command sequence for QuinoaCommand envelopes. The current
        # client (v2036) wraps every discrete game action in a QuinoaCommand
        # carrying a per-connection incrementing commandSequence (starts at 1)
        # and a fresh requestId UUID. Reset on each new connection.
        self._command_sequence = 0

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

    @contextlib.asynccontextmanager
    async def _session(self):
        """Yield the shared HTTP session, creating it on first use."""
        if self._http is None or self._http.closed:
            self._http = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(limit=4, ttl_dns_cache=600),
                timeout=aiohttp.ClientTimeout(total=30),
            )
        yield self._http

    async def close_http(self):
        if self._http is not None and not self._http.closed:
            await self._http.close()

    def _http_headers(self, room_id: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "accept": "*/*",
            "origin": "https://magicgarden.gg",
            "referer": f"https://magicgarden.gg/r/{room_id}" if room_id else "https://magicgarden.gg/",
            "user-agent": USER_AGENT,
        }
        if self.cookies:
            headers["cookie"] = self.cookies
        return headers

    async def refresh_version(self, room: Optional[str] = None) -> str:
        """Read the live client build id from the room page, like a browser
        loading it would. Builds differ per room during rollouts (MG1 can be
        on 2065 while a private room is on 2071), so always ask the room we
        are about to join. Falls back to the last known build on failure."""
        room = room or self.config.last_room or "MG1"
        try:
            async with self._session() as session:
                async with session.get(
                    f"https://magicgarden.gg/r/{room}",
                    headers={"user-agent": USER_AGENT, "accept": "text/html"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as response:
                    html = await response.text()
            match = re.search(r"/version/([A-Za-z0-9._-]+)/assets/", html)
            if match:
                if match.group(1) != self.version:
                    print(f"Game build: {match.group(1)} (pinned fallback was {self.version})")
                self.version = match.group(1)
        except Exception as e:
            print(f"Could not detect game build ({e}); using {self.version}")
        return self.version

    async def _companion_fetches(self, room_id: str, paths: List[str]):
        """Best-effort GETs the real client makes around connecting (profile,
        credits, streak...). Results are ignored; they only keep our HTTP
        footprint looking like a browser tab's."""
        base = f"https://magicgarden.gg/version/{self.version}/api/rooms/{room_id}"

        async def one(session, path):
            async with session.get(base + path, headers=self._http_headers(room_id),
                                   timeout=aiohttp.ClientTimeout(total=15)) as r:
                await r.read()

        try:
            async with self._session() as session:
                await asyncio.gather(*[one(session, p) for p in paths], return_exceptions=True)
        except Exception:
            pass

    async def _companion_poll_task(self):
        """The real client re-fetches credits and streak about once a minute."""
        room_id = self.game_state.get("room_id")
        while self.is_connected:
            await asyncio.sleep(random.uniform(55, 65))
            if not self.is_connected:
                break
            await self._companion_fetches(room_id, ["/me/credits", "/me/streak"])

    async def authenticate(self, room_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Authenticate with server for a specific room.

        Args:
            room_id: Room ID to authenticate for (e.g., "MG1")

        Returns:
            Tuple of (auth_data, updated_cookies) or (None, None) on failure
        """
        auth_url = f"https://magicgarden.gg/version/{self.version}/api/rooms/{room_id}/user/authenticate-web"
        headers = self._http_headers(room_id)
        headers["content-type"] = "application/json"
        payload = {"provider": "maybe-existing-jwt"}

        try:
            async with self._session() as session:
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

                    body = await response.text()
                    print(f"  Auth HTTP {response.status}: {body[:200]}")
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
        # Same parameters, order and JSON-string quoting as the real client.
        self._connection_attempt += 1
        q = lambda v: quote(json.dumps(v), safe="")
        url = (
            f"wss://magicgarden.gg/version/{self.version}/api/rooms/{room_id}/connect"
            f"?surface={q('web')}&platform={q('desktop')}&version={q(self.version)}"
            f"&capabilities={q('fbo_mipmap_unsupported')}"
            f"&clientDeviceId={q(self.client_device_id)}&os={q('other')}"
            f"&clientDocumentId={q(self.client_document_id)}"
            f"&clientConnectionAttempt={self._connection_attempt}"
            f"&clientNavigationType={q('navigate')}&clientVisibilityState={q('visible')}"
        )

        print(f"\nTrying room {room_id}...")

        try:
            # Connect WITHOUT async with so we can keep the connection open
            websocket = await websockets.connect(
                url, additional_headers=headers, compression="deflate"
            )

            # Send initial handshake message. The current client (v2036+) no
            # longer votes for / selects a game (rooms run Quinoa directly).
            # The real client simply announces that the socket is open, and the
            # server responds with the Welcome message.
            await self._send_message_raw(websocket, {"type": "SocketOpened"})

            # Wait for Welcome message with timeout
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=5.0)

                # Server heartbeats arrive as "ping:<n>"; the real client
                # echoes the counter back as "pong:<n>".
                if isinstance(message, str) and message.strip().lower().startswith("ping"):
                    await websocket.send(pong_for(message))
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
                                    slot and (slot.get("userId") or slot.get("playerId")) == self.player_id
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

                        if isinstance(followup, str) and followup.strip().lower().startswith("ping"):
                            await websocket.send(pong_for(followup))
                            continue

                        try:
                            follow_data = json.loads(followup)
                        except json.JSONDecodeError:
                            continue

                        msg_type = follow_data.get("type")
                        if msg_type in ("RoomFrame", "PartialState"):
                            if msg_type == "RoomFrame":
                                patches = (follow_data.get("state") or {}).get("patches") or []
                            else:
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
                                slot and (slot.get("userId") or slot.get("playerId")) == self.player_id
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

    async def send_command(self, command: Dict[str, Any], **extra):
        """
        Send a discrete game action wrapped in a QuinoaCommand envelope.

        The current client (v2036) no longer sends raw action messages like
        ``{"type": "HarvestCrop", ...}``. Every discrete command is wrapped::

            {
              "scopePath": ["Room", "Quinoa"],
              "type": "QuinoaCommand",
              "requestId": "<uuid4>",
              "commandSequence": <monotonic int, starts at 1>,
              "command": { "type": "HarvestCrop", ... },
              ...optional top-level fields (e.g. successorItemId)...
            }

        Continuous state updates (e.g. PlayerPosition) are still sent raw via
        ``send`` and must NOT be wrapped.

        Args:
            command: The inner command dict, e.g. {"type": "HarvestCrop", ...}.
            **extra: Extra top-level envelope fields (e.g. successorItemId).
        """
        self._command_sequence += 1
        envelope = {
            "scopePath": ["Room", "Quinoa"],
            "type": "QuinoaCommand",
            "requestId": str(uuid.uuid4()),
            "commandSequence": self._command_sequence,
            "command": command,
        }
        if extra:
            envelope.update(extra)
        self._sent_commands[envelope["requestId"]] = command
        if len(self._sent_commands) > 500:
            self._sent_commands.pop(next(iter(self._sent_commands)))
        await self.send(envelope)

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
                if isinstance(message, str) and message.strip().lower().startswith("ping"):
                    self.game_state.increment_stat("pings_received")
                    pong = pong_for(message)
                    await self.websocket.send(pong)
                    self.game_state.increment_stat("pongs_sent")
                    log_message_to_file("SENT", pong)
                    continue
                process_message(message, self.game_state)
                if isinstance(message, str) and '"QuinoaCommandResult"' in message[:60]:
                    try:
                        result = json.loads(message)
                    except ValueError:
                        result = {}
                    if result.get("ok"):
                        self.command_ok += 1
                        gained = (result.get("currencyGains") or {}).get("coins")
                        if isinstance(gained, (int, float)):
                            self.session_coins_earned += int(gained)
                    if result.get("ok") is False:
                        self.command_rejected += 1
                        cmd = self._sent_commands.get(result.get("requestId"))
                        self.rejection_log.append({"t": time.time(), "command": cmd or {},
                                                   "code": result.get("code") or "rejected"})
                        del self.rejection_log[:-50]
                        if cmd:
                            self.rejected_commands.append(cmd)
                            print(f"Server rejected {cmd.get('type')}: {result.get('code')}")
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

            # Load the room page first (gives this room's current build)
            await self.refresh_version(room_id)

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

            # The page loads the player's profile bits right after auth.
            await self._companion_fetches(room_id, [
                "/me", "/user/connected-accounts", "/me/credits", "/me/streak",
                "/notifications/subscriptions", "/friends", "/me/changelog",
            ])

            # Set up headers with authenticated cookies
            headers = {
                "Origin": "https://magicgarden.gg",
                "User-Agent": USER_AGENT,
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

        # Reset the QuinoaCommand sequence; the server expects it to start at 1
        # for each fresh connection.
        self._command_sequence = 0

        # Signal successful connection
        self._connected.set()

        # Right after the handshake the real client clears its held tool.
        await self.send(
            {"scopePath": ["Room", "Quinoa"], "type": "SetPlayerInteraction", "interaction": None}
        )

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

        # Server timeline messages keep game_state's position in sync after this.
        if spawn_pos_updated and slot_available:
            # A fresh page announces its spawn tile once (the server records it
            # as a "teleport"; later steps are then "walk"s from there, exactly
            # like the browser). Without this our first step is a teleport.
            await self.send(
                {
                    "scopePath": ["Room", "Quinoa"],
                    "type": "PlayerPosition",
                    "position": {"x": spawn_pos_updated["x"], "y": spawn_pos_updated["y"]},
                }
            )
            self.game_state.set_player_position(
                spawn_pos_updated["x"], spawn_pos_updated["y"]
            )
            pos = self.game_state.get_player_position()
            print(f"Standing at ({pos['x']}, {pos['y']}) (slot {self.game_state.get_user_slot_index()})\n")
        else:
            print("Garden slot never became available; movement disabled.\n")

        # Once the scene is drawn the page reports its load timings and asks
        # the pets to greet the player at spawn.
        await self._send_load_reports(spawn_pos_updated)

        # Initialize pet positions
        await initialize_pets(self, self.game_state)

    async def _send_load_reports(self, spawn_pos):
        rnd = random.Random()
        signed_in = rnd.randint(450, 900)
        joined = signed_in + rnd.randint(250, 600)
        splash = joined + rnd.randint(900, 2200)
        presented = splash + rnd.randint(1200, 4200)
        await asyncio.sleep(max(0.5, (presented - joined) / 1000.0 - 1.0))
        marks = {
            "auth:signed-in": signed_in,
            "splash:loaded": splash,
            "room:joined": joined,
            "app:content-presented": presented,
            "atlas:sharpening-started": presented + rnd.randint(0, 3),
        }
        base = {
            "scopePath": ["Room"],
            "type": "ClientLoadReport",
            "firstHiddenMs": 0,
            "transferBytesBeforeContent": rnd.randint(3800, 6200),
            "fetchActiveMsBeforeContent": rnd.randint(700, 1900),
            "contentAddressedFetchedBeforeContent": [],
            "usesUncompressedAtlas": False,
            "logicalCores": self.config_logical_cores(),
            "network": {"effectiveType": "4g", "downlinkMbps": 10, "rttMs": 100},
            "timeZone": "America/Los_Angeles",
        }
        hits = rnd.randint(38, 45)
        steps = [
            ("app:content-presented", {}),
            ("atlas:pages-half", {"atlas:pages-half": marks["atlas:sharpening-started"] + rnd.randint(300, 500)}),
            ("atlas:sharpening-ended", None),
        ]
        for trigger, extra in steps:
            if extra is None:
                sharp = marks["atlas:pages-half"] + rnd.randint(450, 750)
                extra = {"atlas:pages-sharp": sharp, "atlas:sharpening-ended": sharp + rnd.randint(15, 40)}
            marks.update(extra)
            msg = dict(base)
            msg["trigger"] = trigger
            msg["marks"] = dict(marks)
            msg["contentAddressedCache"] = {"status": "open", "hits": hits, "quotaExceeded": False}
            # keep the documented key order of the real client
            ordered = {k: msg[k] for k in ("scopePath", "type", "trigger", "marks", "firstHiddenMs",
                                           "transferBytesBeforeContent", "fetchActiveMsBeforeContent",
                                           "contentAddressedFetchedBeforeContent", "usesUncompressedAtlas",
                                           "logicalCores", "network", "contentAddressedCache", "timeZone")}
            if not self.is_connected:
                return
            await self.send(ordered)
            hits += rnd.randint(5, 9)
            await asyncio.sleep(rnd.uniform(0.3, 0.7))
        if spawn_pos and self.is_connected:
            await self.send({"scopePath": ["Room", "Quinoa"], "type": "RequestPetGreet",
                             "position": {"x": spawn_pos["x"], "y": spawn_pos["y"]}})

    @staticmethod
    def config_logical_cores() -> int:
        import os
        return os.cpu_count() or 8

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
            tasks.append(asyncio.create_task(self._companion_poll_task()))
            # NOTE: The real web client (v2036) does NOT send client-initiated
            # "Ping" messages. The server drives the heartbeat with "ping:<n>"
            # and the client only replies "pong" (handled in _receive_messages).
            # Sending our own Ping was a bot tell and is no longer emitted, so
            # the periodic ping task is intentionally not started here.

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


def pong_for(ping_message: str) -> str:
    """Echo the server heartbeat counter: "ping:3" -> "pong:3"."""
    _, sep, counter = ping_message.strip().partition(":")
    return f"pong:{counter}" if sep else "pong"
