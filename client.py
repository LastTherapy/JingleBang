from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterable, Optional

import requests

from model import GameState, MoveCommand


class ApiClient:
    """HTTP client with a strict min interval between ANY requests.

    - If max_rps=1 => min_interval=1.0 sec
    - If max_rps=2 => min_interval=0.5 sec  (GET arena + POST move within a second)
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        max_rps: float = 2.0,
        timeout: float = 10.0,
        debug_dir: str = "debug",
        session: Optional[requests.Session] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.token = token
        self.timeout = float(timeout)
        self.max_rps = float(max_rps)
        self.min_interval = 1.0 / self.max_rps if self.max_rps > 0 else 0.0

        self._last_req_ts = 0.0
        self._session = session or requests.Session()

        self._debug_dir = Path(debug_dir)
        self._debug_dir.mkdir(parents=True, exist_ok=True)

    def _rate_limit(self) -> None:
        if self.min_interval <= 0:
            return
        now = time.perf_counter()
        delta = now - self._last_req_ts
        if delta < self.min_interval:
            time.sleep(self.min_interval - delta)
        self._last_req_ts = time.perf_counter()

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        self._rate_limit()
        url = self.base_url + path.lstrip("/")
        headers = kwargs.pop("headers", {})
        headers.update({"accept": "application/json", "X-Auth-Token": self.token})
        return self._session.request(method, url, headers=headers, timeout=self.timeout, **kwargs)

    def _save_debug(self, filename: str, data: object) -> None:
        try:
            (self._debug_dir / filename).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def get_arena(self) -> GameState:
        r = self._request("GET", "arena")
        r.raise_for_status()
        data = r.json()
        self._save_debug("last_arena.json", data)
        return GameState.from_dict(data)

    def send_move(self, commands: Iterable[MoveCommand]) -> dict:
        payload = {"bombers": [c.to_dict() for c in commands]}
        r = self._request("POST", "move", json=payload)
        self._save_debug("last_move_request.json", payload)
        try:
            self._save_debug("last_move_response.json", r.json())
        except Exception:
            pass
        r.raise_for_status()
        return r.json()
