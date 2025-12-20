from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import requests

from app.engine import DecisionEngine
from app.state_cache import StateCache
from client import ApiClient


@dataclass
class BotControl:
    running: bool = True
    paused: bool = False
    tick_sec: float = 1.0  # IMPORTANT: 1 tick per second => GET arena <= 1 rps, move <= 1 rps


class BotRunner(threading.Thread):
    def __init__(self, api: ApiClient, engine: DecisionEngine, cache: StateCache, control: BotControl, *, quiet: bool = False) -> None:
        super().__init__(daemon=True)
        self.api = api
        self.engine = engine
        self.cache = cache
        self.control = control
        self.quiet = quiet

    def run(self) -> None:
        next_ts = time.perf_counter()
        while self.control.running:
            if self.control.paused:
                time.sleep(0.1)
                continue

            now = time.perf_counter()
            if now < next_ts:
                time.sleep(next_ts - now)
            tick_start = time.perf_counter()
            next_ts = tick_start + max(0.2, float(self.control.tick_sec))

            try:
                state = self.api.get_arena()
                self.cache.set_state(state)
            except requests.RequestException as exc:
                self.cache.set_error(f"[arena] request error: {exc}")
                continue

            if not self.quiet:
                alive = sum(1 for b in state.bombers if b.alive)
                print(f"[arena] round={state.round} score={state.raw_score} alive={alive}/{len(state.bombers)} errors={state.errors}")

            try:
                commands = self.engine.decide(state)
            except Exception as exc:
                self.cache.set_error(f"[engine] error: {exc}")
                continue

            if commands:
                try:
                    resp = self.api.send_move(commands)
                    self.cache.set_move_response(resp)
                    if not self.quiet:
                        print(f"[move] code={resp.get('code')} errors={resp.get('errors')}")
                except requests.RequestException as exc:
                    self.cache.set_error(f"[move] request error: {exc}")

            self.cache.set_tick_ms((time.perf_counter() - tick_start) * 1000.0)
