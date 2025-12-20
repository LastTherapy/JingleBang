from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

import uvicorn

from client import ApiClient
from app.assignments import AssignmentStore
from app.engine import DecisionEngine, EngineConfig
from app.registry import StrategyRegistry
from app.state_cache import StateCache
from infra.bot_runner import BotRunner, BotControl
from infra.webapp import create_app
from strategies.farm_obstacles import FarmObstaclesStrategy
from strategies.idle import IdleStrategy


DEFAULT_TOKEN = "345c75ba-26c0-4f3e-acd4-09e63982ca52"
DEFAULT_BASE_URL = "https://games-test.datsteam.dev/api/"


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bot + GUI for DatsJingleBang")

    parser.add_argument("--token", default=os.getenv("DATS_TOKEN", DEFAULT_TOKEN), help="Auth token for API")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base url (with /api suffix)")
    parser.add_argument("--rps", type=float, default=2.0, help="Max requests per second (arena+move combined)")

    parser.add_argument("--loop-delay", type=float, default=0.35, help="Delay between iterations (seconds)")
    parser.add_argument("--danger-timer", type=float, default=2.5, help="Timer threshold to treat bombs as dangerous")

    parser.add_argument("--assignments", default="assignments.json", help="Path to assignments json")

    parser.add_argument("--gui-host", default="127.0.0.1", help="GUI host")
    parser.add_argument("--gui-port", type=int, default=8000, help="GUI port")
    parser.add_argument("--no-gui", action="store_true", help="Run bot without GUI (console only)")
    parser.add_argument("--no-bot", action="store_true", help="Run GUI without bot loop (debug)")
    parser.add_argument("--quiet", action="store_true", help="Less console logs")

    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)

    # ===== registry (плагины стратегий) =====
    registry = StrategyRegistry(
        _factories={
            "idle": lambda: IdleStrategy(),
            "farm_obstacles": lambda: FarmObstaclesStrategy(),
        },
        _descriptions={
            "idle": "do nothing",
            "farm_obstacles": "go to nearest obstacle -> bomb -> escape",
        },
    )

    assignments = AssignmentStore(path=Path(args.assignments), default_strategy="farm_obstacles")
    cache = StateCache()
    control = BotControl(paused=False, loop_delay=args.loop_delay)

    api = ApiClient(base_url=args.base_url, token=args.token, max_rps=args.rps)
    engine = DecisionEngine(registry, assignments, EngineConfig(max_path=30, danger_timer=args.danger_timer))

    runner = BotRunner(api=api, engine=engine, cache=cache, control=control, verbose=not args.quiet)

    if not args.no_bot:
        runner.start()

    if args.no_gui:
        print("Bot loop started (no GUI). Press Ctrl+C to stop.")
        try:
            while True:
                import time
                time.sleep(1.0)
        except KeyboardInterrupt:
            runner.stop()
        return 0

    app = create_app(cache=cache, assignments=assignments, registry=registry, control=control)

    print(f"GUI: http://{args.gui_host}:{args.gui_port}")
    try:
        uvicorn.run(app, host=args.gui_host, port=args.gui_port, log_level="info")
    finally:
        runner.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
