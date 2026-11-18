"""
Remote control API, so the Qt window can watch and steer a bot running
elsewhere (e.g. headless on the server, reached over Tailscale).

    GET  /api/state     everything the UI shows: game state, position, brain
                        status/plan/events/settings, client tallies
    POST /api/control   {"paused": bool} | {"request": "sell"|"shop"} |
                        {"settings": {key: value}}

Every request needs `Authorization: Bearer <token>`. Bind it to a private
address (the tailnet IP), never a public one.
"""

import hmac
import json
import time
from typing import Any, Dict, Optional

from aiohttp import web


class RemoteServer:
    def __init__(self, client, game_state, brain, token: str):
        self.client = client
        self.gs = game_state
        self.brain = brain
        self.token = token
        self.runner: Optional[web.AppRunner] = None

    # ------------------------------------------------------------ auth
    def _authorized(self, request: web.Request) -> bool:
        header = request.headers.get("Authorization", "")
        given = header[7:] if header.startswith("Bearer ") else ""
        return bool(self.token) and hmac.compare_digest(given, self.token)

    @web.middleware
    async def _auth(self, request, handler):
        if not self._authorized(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        return await handler(request)

    # ------------------------------------------------------------ state
    def _etag(self) -> str:
        """Cheap fingerprint of everything the UI shows; same tag -> 304."""
        b, c = self.brain, self.client
        parts = [self.gs.get_revision(), bool(getattr(c, "is_connected", False)),
                 getattr(c, "command_ok", 0), getattr(c, "command_rejected", 0),
                 getattr(c, "session_coins_earned", 0), getattr(c, "version", "")]
        if b is not None:
            last = b.events[-1][0] if b.events else 0
            parts += [b.paused, b.action, len(b.events), last, len(b.requests), id(b.cfg)]
        return '"' + "-".join(map(str, parts)) + '"'

    def _payload(self, full_state) -> Dict[str, Any]:
        gs, brain, client = self.gs, self.brain, self.client
        if full_state:  # drop room chat: never shown, often the biggest part
            full_state = dict(full_state)
            full_state["data"] = {k: v for k, v in (full_state.get("data") or {}).items() if k != "chat"}
        out: Dict[str, Any] = {
            "fullState": full_state,
            "playerId": gs.get_player_id(),
            "playerName": gs.get_player_name(),
            "roomId": gs.get_room_id(),
            "slotIndex": gs.get_user_slot_index(),
            "position": gs.get_player_position(),
            "revision": gs.get_revision(),
            "client": {
                "connected": bool(getattr(client, "is_connected", False)),
                "version": getattr(client, "version", None),
                "sessionCoins": getattr(client, "session_coins_earned", 0),
                "ok": getattr(client, "command_ok", 0),
                "rejected": getattr(client, "command_rejected", 0),
            },
            "brain": None,
        }
        if brain is not None:
            out["brain"] = {
                "paused": brain.paused,
                "action": brain.action,
                "events": list(brain.events)[-100:],
                "counters": dict(brain.counters),
                "plan": brain.last_plan,
                "settings": brain.settings(),
            }
        return out

    async def _get_state(self, request):
        etag = self._etag()
        if request.headers.get("If-None-Match") == etag:
            return web.Response(status=304, headers={"ETag": etag})
        # Serialise straight from the live state under its lock: no deep copy.
        body = self.gs.read_full_state(
            lambda fs: json.dumps(self._payload(fs), separators=(",", ":"), default=list))
        resp = web.Response(body=body.encode("utf-8"), content_type="application/json",
                            headers={"ETag": etag})
        resp.enable_compression()
        return resp

    async def _post_control(self, request):
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "bad json"}, status=400)
        if self.brain is None:
            return web.json_response({"error": "brain disabled"}, status=409)
        if "paused" in body:
            self.brain.paused = bool(body["paused"])
        if body.get("request") in ("sell", "shop"):
            self.brain.request(body["request"])
        if isinstance(body.get("settings"), dict):
            self.brain.apply_settings(body["settings"])
        return web.json_response({"ok": True, "paused": self.brain.paused})

    # ------------------------------------------------------------ lifecycle
    async def start(self, host: str, port: int):
        app = web.Application(middlewares=[self._auth])
        app.router.add_get("/api/state", self._get_state)
        app.router.add_post("/api/control", self._post_control)
        self.runner = web.AppRunner(app, access_log=None)
        await self.runner.setup()
        site = web.TCPSite(self.runner, host, port)
        await site.start()
        print(f"Remote control API listening on http://{host}:{port}")

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()
