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

    _last_move_resp: Optional[dict] = None
    _last_move_ts: float = 0.0

    _last_error: str = ""
    _last_tick_ms: float = 0.0

    def set_state(self, state: GameState) -> None:
        with self._lock:
            self._state = state
            self._state_ts = time.time()

    def get_state(self) -> Optional[GameState]:
        with self._lock:
            return self._state

    def get_state_age_s(self) -> float:
        with self._lock:
            if self._state_ts == 0.0:
                return 1e9
            return time.time() - self._state_ts

    def set_move_response(self, resp: dict) -> None:
        with self._lock:
            self._last_move_resp = resp
            self._last_move_ts = time.time()

    def get_move_response(self) -> Optional[dict]:
        with self._lock:
            return self._last_move_resp

    def set_error(self, msg: str) -> None:
        with self._lock:
            self._last_error = msg

    def get_error(self) -> str:
        with self._lock:
            return self._last_error

    def set_tick_ms(self, ms: float) -> None:
        with self._lock:
            self._last_tick_ms = ms

    def get_tick_ms(self) -> float:
        with self._lock:
            return self._last_tick_ms
