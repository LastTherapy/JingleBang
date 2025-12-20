from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

import requests

from client import ApiClient
from app.engine import DecisionEngine
from app.state_cache import StateCache


@dataclass
class BotControl:
    running: bool = True
    paused: bool = False
    loop_delay: float = 0.35
    booster_refresh_s: float = 1.5  # как часто обновлять бустеры (сек)


class BotRunner(threading.Thread):
    def __init__(self, api: ApiClient, engine: DecisionEngine, cache: StateCache, control: BotControl, *, quiet: bool = False) -> None:
        super().__init__(daemon=True)
        self.api = api
        self.engine = engine
        self.cache = cache
        self.control = control
        self.quiet = quiet

        self._last_booster_fetch = 0.0
        self._booster = None

    def run(self) -> None:
        while self.control.running:
            t0 = time.time()
            if self.control.paused:
                time.sleep(0.1)
                continue

            try:
                state = self.api.get_arena()
                self.cache.set_state(state)
            except requests.RequestException as exc:
                self.cache.set_error(f"[arena] request error: {exc}")
                time.sleep(0.5)
                continue

            # booster state (кешируем)
            try:
                if self._booster is None or (time.time() - self._last_booster_fetch) >= self.control.booster_refresh_s:
                    self._booster = self.api.get_booster_state()
                    self._last_booster_fetch = time.time()
                    self.cache.set_booster(self._booster)
            except requests.RequestException as exc:
                # не фейлим тик — просто оставляем старое значение
                self.cache.set_error(f"[booster] request error: {exc}")

            booster = self._booster
            if booster is None:
                time.sleep(self.control.loop_delay)
                continue

            if not self.quiet:
                alive = sum(1 for b in state.bombers if b.alive)
                print(f"[arena] round={state.round} score={state.raw_score} alive={alive}/{len(state.bombers)} errors={state.errors}")

            try:
                commands = self.engine.decide(state, booster)
            except Exception as exc:
                self.cache.set_error(f"[engine] error: {exc}")
                time.sleep(self.control.loop_delay)
                continue

            if commands:
                try:
                    resp = self.api.send_move(commands)
                    self.cache.set_move_response(resp)
                    if not self.quiet:
                        print(f"[move] code={resp.get('code')} errors={resp.get('errors')}")
                except requests.RequestException as exc:
                    self.cache.set_error(f"[move] request error: {exc}")

            t1 = time.time()
            self.cache.set_tick_ms((t1 - t0) * 1000.0)

            time.sleep(max(0.0, self.control.loop_delay))
