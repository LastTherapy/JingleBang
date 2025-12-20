from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

from model import GameState


@dataclass
class StateCache:
    _lock: threading.RLock = threading.RLock()
    _state: Optional[GameState] = None
    _state_ts: float = 0.0

    _last_move_response: Optional[dict] = None
    _last_move_ts: float = 0.0

    _last_error: Optional[str] = None
    _last_tick_ms: float = 0.0

    def set_state(self, state: GameState) -> None:
        with self._lock:
            self._state = state
            self._state_ts = time.time()

    def get_state(self) -> Optional[GameState]:
        with self._lock:
            return self._state

    def get_state_meta(self) -> dict:
        with self._lock:
            return {
                "ts": self._state_ts,
                "has_state": self._state is not None,
                "last_error": self._last_error,
                "last_tick_ms": self._last_tick_ms,
                "last_move_ts": self._last_move_ts,
            }

    def set_move_response(self, resp: dict) -> None:
        with self._lock:
            self._last_move_response = resp
            self._last_move_ts = time.time()

    def get_move_response(self) -> Optional[dict]:
        with self._lock:
            return self._last_move_response

    def set_error(self, msg: str) -> None:
        with self._lock:
            self._last_error = msg

    def set_tick_ms(self, ms: float) -> None:
        with self._lock:
            self._last_tick_ms = ms
