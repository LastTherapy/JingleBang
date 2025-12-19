from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterable, Optional

import requests

from model import GameState, MoveCommand


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
        out_dir: str | Path = "out",
        timeout: float = 5.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"accept": "application/json", "X-Auth-Token": token})

        self.min_interval = 1.0 / max_rps
        self.last_request_ts: float = 0.0
        self.timeout = timeout

        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def _rate_limit(self) -> None:
        now = time.perf_counter()
        delta = now - self.last_request_ts
        if delta < self.min_interval:
            time.sleep(self.min_interval - delta)

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        self._rate_limit()
        url = f"{self.base_url}/{path.lstrip('/')}"
        response = self.session.request(method, url, timeout=self.timeout, **kwargs)
        self.last_request_ts = time.perf_counter()
        return response

    def get_arena(self) -> GameState:
        response = self._request("GET", "arena")
        response.raise_for_status()
        return GameState.from_dict(response.json())

    def send_move(self, commands: Iterable[MoveCommand]) -> dict:
        payload = {"bombers": [cmd.to_dict() for cmd in commands]}
        response = self._request("POST", "move", json=payload)
        # Сервер возвращает PublicError с кодом; не бросаем исключение сразу, чтобы можно было логировать ошибки.
        try:
            response.raise_for_status()
        finally:
            self._save_debug("last_move_request.json", payload)
            self._save_debug("last_move_response.json", response.json())
        return response.json()

    def get_boosters(self) -> dict:
        response = self._request("GET", "booster")
        response.raise_for_status()
        return response.json()

    def buy_booster(self, booster: dict) -> dict:
        response = self._request("POST", "booster", json=booster)
        response.raise_for_status()
        return response.json()

    def _save_debug(self, filename: str, data: dict) -> Path:
        path = self.out_dir / filename
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path
