"""
Game state management module for Magic Garden Bot.

This module provides thread-safe state management for the bot, encapsulating
player information, room state, positions, and connection statistics.
"""

import threading
from copy import deepcopy
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class Statistics:
    """Connection statistics"""
    messages_received: int = 0
    messages_sent: int = 0
    pings_sent: int = 0
    pings_received: int = 0
    pongs_sent: int = 0
    pongs_received: int = 0
    last_update: str = "Never"
    patches_applied: int = 0


class GameState:
    """Thread-safe game state manager

    This class encapsulates all game state with proper thread synchronization.
    It provides both modern method-based access and backwards-compatible
    dict-like access for gradual migration.

    Key features:
    - Thread-safe access via RLock (reentrant lock)
    - Type hints for better code clarity
    - Helper methods for common operations
    - Deep copying where appropriate to prevent race conditions
    """

    def __init__(self):
        self._lock = threading.RLock()  # Reentrant lock to allow nested locking
        self._player_id: Optional[str] = None
        self._player_name: Optional[str] = None
        self._room_id: Optional[str] = None
        self._full_state: Optional[Dict[str, Any]] = None
        self._player_position: Dict[str, int] = {"x": 11, "y": 11}
        self._user_slot_index: Optional[int] = None
        self._pet_positions: Dict[str, Dict[str, int]] = {}
        self._pet_positions_synced: bool = False
        self._statistics = Statistics()
        self._extra: Dict[str, Any] = {}  # For runtime-added keys like room_id_override

    # Player info methods
    def get_player_id(self) -> Optional[str]:
        with self._lock:
            return self._player_id

    def set_player_id(self, player_id: str):
        with self._lock:
            self._player_id = player_id

    def get_player_name(self) -> Optional[str]:
        with self._lock:
            return self._player_name

    def set_player_name(self, name: str):
        with self._lock:
            self._player_name = name

    # Room methods
    def get_room_id(self) -> Optional[str]:
        with self._lock:
            return self._room_id

    def set_room_id(self, room_id: str):
        with self._lock:
            self._room_id = room_id

    # Full state methods
    def get_full_state(self) -> Optional[Dict[str, Any]]:
        """Returns a deep copy of the full state"""
        with self._lock:
            return deepcopy(self._full_state) if self._full_state else None

    def set_full_state(self, state: Dict[str, Any]):
        """Sets the full state (makes a deep copy internally)"""
        with self._lock:
            self._full_state = deepcopy(state)

    def get_full_state_unsafe(self) -> Optional[Dict[str, Any]]:
        """Returns the actual full state reference (caller must hold lock or know what they're doing)"""
        return self._full_state

    def update_full_state_locked(self, updater_fn):
        """Execute a function with locked access to full_state for in-place updates

        Args:
            updater_fn: A function that takes full_state and modifies it in-place
        """
        with self._lock:
            if self._full_state:
                updater_fn(self._full_state)

    # Player position methods
    def get_player_position(self) -> Dict[str, int]:
        with self._lock:
            return self._player_position.copy()

    def set_player_position(self, x: int, y: int):
        with self._lock:
            self._player_position = {"x": x, "y": y}

    # User slot index methods
    def get_user_slot_index(self) -> Optional[int]:
        with self._lock:
            return self._user_slot_index

    def set_user_slot_index(self, index: int):
        with self._lock:
            self._user_slot_index = index

    # Pet positions methods
    def get_pet_positions(self) -> Dict[str, Dict[str, int]]:
        with self._lock:
            return deepcopy(self._pet_positions)

    def set_pet_position(self, pet_id: str, x: int, y: int):
        with self._lock:
            self._pet_positions[pet_id] = {"x": x, "y": y}

    def clear_pet_positions(self):
        with self._lock:
            self._pet_positions.clear()

    def get_pet_positions_synced(self) -> bool:
        with self._lock:
            return self._pet_positions_synced

    def set_pet_positions_synced(self, synced: bool):
        with self._lock:
            self._pet_positions_synced = synced

    # Statistics methods
    def increment_stat(self, stat_name: str, amount: int = 1):
        """Atomically increment a statistic counter

        Args:
            stat_name: Name of the statistic field (e.g., "messages_received")
            amount: Amount to increment by (default: 1)
        """
        with self._lock:
            if hasattr(self._statistics, stat_name):
                current = getattr(self._statistics, stat_name)
                if isinstance(current, int):
                    setattr(self._statistics, stat_name, current + amount)

    def set_stat(self, stat_name: str, value):
        """Set a statistic value

        Args:
            stat_name: Name of the statistic field
            value: New value to set
        """
        with self._lock:
            if hasattr(self._statistics, stat_name):
                setattr(self._statistics, stat_name, value)

    def get_statistics(self) -> Statistics:
        """Get a copy of the current statistics"""
        with self._lock:
            # Return a copy to prevent external modification
            return Statistics(
                messages_received=self._statistics.messages_received,
                messages_sent=self._statistics.messages_sent,
                pings_sent=self._statistics.pings_sent,
                pings_received=self._statistics.pings_received,
                pongs_sent=self._statistics.pongs_sent,
                pongs_received=self._statistics.pongs_received,
                last_update=self._statistics.last_update,
                patches_applied=self._statistics.patches_applied
            )

    # Extra keys (for backwards compatibility with dict-like access)
    def get(self, key: str, default=None):
        """Dict-like get for backwards compatibility"""
        with self._lock:
            if key == "player_id":
                return self._player_id
            elif key == "player_name":
                return self._player_name
            elif key == "room_id":
                return self._room_id
            elif key == "full_state":
                return deepcopy(self._full_state) if self._full_state else None
            elif key == "user_slot_index":
                return self._user_slot_index
            elif key == "statistics":
                # Return dict for backwards compatibility
                return {
                    "messages_received": self._statistics.messages_received,
                    "messages_sent": self._statistics.messages_sent,
                    "pings_sent": self._statistics.pings_sent,
                    "pings_received": self._statistics.pings_received,
                    "pongs_sent": self._statistics.pongs_sent,
                    "pongs_received": self._statistics.pongs_received,
                    "last_update": self._statistics.last_update,
                    "patches_applied": self._statistics.patches_applied
                }
            else:
                return self._extra.get(key, default)

    def __getitem__(self, key: str):
        """Dict-like access for backwards compatibility"""
        result = self.get(key)
        if result is None and key not in ["player_id", "player_name", "room_id", "full_state", "user_slot_index"]:
            with self._lock:
                if key not in self._extra:
                    raise KeyError(key)
        return result

    def __setitem__(self, key: str, value):
        """Dict-like setting for backwards compatibility"""
        with self._lock:
            if key == "player_id":
                self._player_id = value
            elif key == "player_name":
                self._player_name = value
            elif key == "room_id":
                self._room_id = value
            elif key == "full_state":
                self._full_state = deepcopy(value) if value else None
            elif key == "user_slot_index":
                self._user_slot_index = value
            elif key == "statistics":
                # Ignore direct statistics assignment, use increment_stat/set_stat
                pass
            else:
                self._extra[key] = value

    def __contains__(self, key: str) -> bool:
        """Dict-like 'in' operator"""
        with self._lock:
            if key in ["player_id", "player_name", "room_id", "full_state", "user_slot_index", "statistics"]:
                return True
            return key in self._extra

    # Helper methods for common operations
    def refresh_player_metadata(self):
        """Update cached player name and slot index from full_state

        This method syncs the cached metadata (player name and slot index)
        with the latest full_state data. It's typically called after
        receiving state updates from the server.
        """
        with self._lock:
            if not self._full_state or not self._player_id:
                return

            # Update player name from room player list
            room_data = self._full_state.get("data") or {}
            players = room_data.get("players") or []
            for player in players:
                if player and player.get("id") == self._player_id:
                    player_name = player.get("name")
                    if player_name:
                        self._player_name = player_name
                    elif not self._player_name:
                        self._player_name = self._player_id
                    break

            # Update slot index from Quinoa child state
            child_state = self._full_state.get("child") or {}
            if child_state.get("scope") != "Quinoa":
                return

            quinoa_state = child_state.get("data") or {}
            user_slots = quinoa_state.get("userSlots") or []
            for idx, slot in enumerate(user_slots):
                if slot and slot.get("playerId") == self._player_id:
                    self._user_slot_index = idx
                    break

    def get_player_slot(self) -> Optional[Dict[str, Any]]:
        """Find and return the player's user slot from game state.

        This returns the full slot object which contains both 'data' and
        'petSlotInfos' at the slot level.

        Returns:
            Deep copy of the player's slot, or None if not found
        """
        with self._lock:
            if not self._full_state or not self._player_id:
                return None

            child_state = self._full_state.get("child", {})
            if child_state.get("scope") != "Quinoa":
                return None

            quinoa_state = child_state.get("data", {})
            user_slots = quinoa_state.get("userSlots", [])

            for slot in user_slots:
                if slot and slot.get("playerId") == self._player_id:
                    return deepcopy(slot)

            return None
