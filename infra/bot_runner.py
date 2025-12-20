from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

import requests

from client import ApiClient
from app.engine import DecisionEngine
from app.state_cache import StateCache
from model import GameState


@dataclass
class BotControl:
    paused: bool = False
    loop_delay: float = 0.35


class BotRunner:
    def __init__(
        self,
        api: ApiClient,
        engine: DecisionEngine,
        cache: StateCache,
        control: BotControl,
        *,
        verbose: bool = True,
    ) -> None:
        self.api = api
        self.engine = engine
        self.cache = cache
        self.control = control
        self.verbose = verbose

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, name="bot-loop", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _log_state(self, state: GameState) -> None:
        alive = sum(1 for b in state.bombers if b.alive)
        print(f"[arena] round={state.round} score={state.raw_score} bombers={alive}/{len(state.bombers)} errors={state.errors}")

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            t0 = time.perf_counter()

            try:
                state = self.api.get_arena()
                self.cache.set_state(state)
                self.cache.set_error("")
                if self.verbose:
                    self._log_state(state)
            except requests.RequestException as exc:
                msg = f"[arena] request error: {exc}"
                self.cache.set_error(msg)
                if self.verbose:
                    print(msg)
                time.sleep(1.0)
                continue

            if not self.control.paused:
                try:
                    commands = self.engine.decide(state)
                    if commands:
                        resp = self.api.send_move(commands)
                        self.cache.set_move_response(resp)
                        if self.verbose:
                            print(f"[move] code={resp.get('code')} errors={resp.get('errors')}")
                except requests.RequestException as exc:
                    msg = f"[move] request error: {exc}"
                    self.cache.set_error(msg)
                    if self.verbose:
                        print(msg)

            dt_ms = (time.perf_counter() - t0) * 1000.0
            self.cache.set_tick_ms(dt_ms)

            time.sleep(max(0.01, float(self.control.loop_delay)))
