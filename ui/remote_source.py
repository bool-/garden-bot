"""
Remote mode for the Qt window: watch and steer a bot running elsewhere
(e.g. headless on the server) through its control API (automation/remote.py).

A background thread polls GET /api/state with If-None-Match, so an unchanged
bot costs a ~100-byte 304 per poll. It polls every second while the window is
focused and every 5 seconds otherwise. The stand-ins below expose exactly the
methods the UI already uses on the local GameState / Brain / client objects.
"""

import gzip
import json
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

FAST_POLL_S = 1.0
SLOW_POLL_S = 5.0


class RemoteSource:
    def __init__(self, base_url: str, token: str):
        self.base = base_url.rstrip("/")
        self.token = token
        self.data: Dict[str, Any] = {}
        self.revision = 0  # bumped whenever new data arrives
        self.connected = False
        self.error: Optional[str] = None
        self.fast = True  # set by the window: focused -> poll fast
        self._etag: Optional[str] = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="remote-poll", daemon=True)
        self._thread.start()

    # ------------------------------------------------------------ http
    def _request(self, method: str, path: str, body: Optional[dict] = None):
        headers = {"Authorization": f"Bearer {self.token}", "Accept-Encoding": "gzip"}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if method == "GET" and self._etag:
            headers["If-None-Match"] = self._etag
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        return urllib.request.urlopen(req, timeout=10)

    def _poll_once(self):
        try:
            with self._request("GET", "/api/state") as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                payload = json.loads(raw)
                with self._lock:
                    self.data = payload
                    self._etag = resp.headers.get("ETag")
                    self.revision += 1
            self.connected, self.error = True, None
        except urllib.error.HTTPError as e:
            if e.code == 304:
                self.connected, self.error = True, None
            else:
                self.connected, self.error = False, f"HTTP {e.code}"
        except Exception as e:
            self.connected, self.error = False, str(e)

    def _loop(self):
        while not self._stop.is_set():
            self._poll_once()
            self._wake.wait(FAST_POLL_S if self.fast else SLOW_POLL_S)
            self._wake.clear()

    def control(self, **body):
        """Fire-and-forget POST /api/control, then refresh right away."""
        def send():
            try:
                with self._request("POST", "/api/control", body):
                    pass
            except Exception as e:
                self.error = f"control failed: {e}"
            self._wake.set()
        threading.Thread(target=send, daemon=True).start()

    def stop(self):
        self._stop.set()
        self._wake.set()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return self.data


# ---------------------------------------------------------------- stand-ins
class RemoteGameState:
    """Read-only GameState look-alike backed by the remote snapshot."""

    def __init__(self, source: RemoteSource):
        self.src = source

    def _d(self):
        return self.src.snapshot()

    def get_revision(self):
        return self.src.revision

    def get_full_state(self):
        return self._d().get("fullState")

    def read_full_state(self, fn):
        return fn(self.get_full_state())

    def get_player_id(self):
        return self._d().get("playerId")

    def get_player_name(self):
        return self._d().get("playerName")

    def get_player_name_by_id(self, player_id):
        players = ((self.get_full_state() or {}).get("data") or {}).get("players") or []
        for p in players:
            if p and p.get("id") == player_id:
                return p.get("name")
        return None

    def get_room_id(self):
        return self._d().get("roomId")

    def get_user_slot_index(self):
        return self._d().get("slotIndex")

    def get_player_position(self):
        return self._d().get("position") or {}

    def get_player_slot(self):
        pid = self.get_player_id()
        child = (self.get_full_state() or {}).get("child") or {}
        for s in ((child.get("data") or {}).get("userSlots") or []):
            if s and (s.get("userId") or s.get("playerId")) == pid:
                return s
        return None

    def get_all_user_slots(self):
        child = (self.get_full_state() or {}).get("child") or {}
        return [s for s in ((child.get("data") or {}).get("userSlots") or []) if s]

    def get(self, key, default=None):
        return {"room_id": self.get_room_id(), "full_state": self.get_full_state()}.get(key, default)

    # Manual moves aren't sent in remote mode; keep the UI's calls harmless.
    def set_player_position(self, x, y):
        pass

    def update_full_state_locked(self, fn):
        pass


class RemoteBrain:
    """Brain look-alike: reads come from the snapshot, writes go to the API."""

    enabled = True

    def __init__(self, source: RemoteSource):
        self.src = source
        self._paused_override: Optional[bool] = None

    def _b(self) -> Dict[str, Any]:
        return self.src.snapshot().get("brain") or {}

    @property
    def paused(self) -> bool:
        if self._paused_override is not None:
            return self._paused_override
        return bool(self._b().get("paused"))

    @paused.setter
    def paused(self, value: bool):
        self._paused_override = bool(value)  # show it at once; the server confirms
        self.src.control(paused=bool(value))
        threading.Timer(3.0, self._clear_override).start()

    def _clear_override(self):
        self._paused_override = None

    @property
    def action(self):
        return self._b().get("action", "")

    @property
    def events(self):
        return [tuple(e) for e in self._b().get("events") or []]

    @property
    def counters(self):
        return self._b().get("counters") or {}

    @property
    def last_plan(self):
        return self._b().get("plan") or {}

    @property
    def cfg(self):
        return self.settings()

    @property
    def requests(self):
        return []

    def settings(self):
        return dict(self._b().get("settings") or {})

    def apply_settings(self, updates: Dict[str, Any], save: bool = True):
        self.src.control(settings=updates)

    def request(self, action: str):
        self.src.control(request=action)


class RemoteClient:
    """Client look-alike for the status bar and KPI strip."""

    def __init__(self, source: RemoteSource):
        self.src = source

    def _c(self):
        return self.src.snapshot().get("client") or {}

    @property
    def is_connected(self) -> bool:
        return self.src.connected and bool(self._c().get("connected"))

    @property
    def version(self):
        return self._c().get("version")

    @property
    def session_coins_earned(self):
        return self._c().get("sessionCoins", 0)

    @property
    def command_ok(self):
        return self._c().get("ok", 0)

    @property
    def command_rejected(self):
        return self._c().get("rejected", 0)
