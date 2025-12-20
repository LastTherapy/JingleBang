from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterable, Optional

import requests

from model import GameState, MoveCommand, BoosterState


class ApiClient:
    """
    Обёртка над HTTP запросами к API игры с простым ограничением по RPS.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        max_rps: float = 2.0,
        debug_dir: str = "debug",
        session: Optional[requests.Session] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.token = token
        self.max_rps = float(max_rps)
        self.session = session or requests.Session()

        self._last_ts = 0.0
        self._debug_dir = Path(debug_dir)
        self._debug_dir.mkdir(parents=True, exist_ok=True)

    def _throttle(self) -> None:
        if self.max_rps <= 0:
            return
        now = time.time()
        min_dt = 1.0 / self.max_rps
        dt = now - self._last_ts
        if dt < min_dt:
            time.sleep(min_dt - dt)
        self._last_ts = time.time()

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        self._throttle()
        url = self.base_url + ("api/" + path.lstrip("/"))
        headers = kwargs.pop("headers", {})
        headers.update({"accept": "application/json", "X-Auth-Token": self.token})
        return self.session.request(method, url, headers=headers, timeout=10, **kwargs)

    def _save_debug(self, filename: str, payload: object) -> None:
        try:
            (self._debug_dir / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            # debug must never break gameplay
            pass

    def get_arena(self) -> GameState:
        response = self._request("GET", "arena")
        response.raise_for_status()
        data = response.json()
        self._save_debug("last_arena.json", data)
        return GameState.from_dict(data)

    def send_move(self, commands: Iterable[MoveCommand]) -> dict:
        payload = {"bombers": [c.to_dict() for c in commands]}
        response = self._request("POST", "move", json=payload)
        self._save_debug("last_move_request.json", payload)
        try:
            self._save_debug("last_move_response.json", response.json())
        except Exception:
            pass
        response.raise_for_status()
        return response.json()

    def get_booster_state(self) -> BoosterState:
        response = self._request("GET", "booster")
        response.raise_for_status()
        data = response.json()
        self._save_debug("last_booster.json", data)
        return BoosterState.from_dict(data)
