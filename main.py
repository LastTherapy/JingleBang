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

from strategies.idle import IdleStrategy
from strategies.farm_obstacles import FarmObstaclesStrategy
from strategies.evade_mobs import EvadeAndBombMobsStrategy


DEFAULT_TOKEN = "345c75ba-26c0-4f3e-acd4-09e63982ca52"
DEFAULT_BASE_URL = "https://games-test.datsteam.dev/api/"


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Bot + FastAPI GUI for DatsJingleBang")
    p.add_argument("--token", default=os.getenv("DATS_TOKEN", DEFAULT_TOKEN), help="Auth token for API")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base url (with /api suffix)")
    p.add_argument("--rps", type=float, default=2.0, help="Max requests per second (per client)")
    p.add_argument("--loop-delay", type=float, default=0.35, help="Delay between iterations (seconds)")
    p.add_argument("--danger-timer", type=float, default=2.5, help="Timer threshold to treat bombs as dangerous")

    p.add_argument("--assignments", default="assignments.json", help="Path to assignments json")

    p.add_argument("--gui-host", default="127.0.0.1", help="GUI host")
    p.add_argument("--gui-port", type=int, default=8000, help="GUI port")
    p.add_argument("--no-gui", action="store_true", help="Run bot without GUI")
    p.add_argument("--no-bot", action="store_true", help="Run GUI without bot loop")
    p.add_argument("--quiet", action="store_true", help="Less console logs")

    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)

    api = ApiClient(base_url=args.base_url, token=args.token, max_rps=args.rps)

    registry = StrategyRegistry(
        {
            "idle": lambda: IdleStrategy(),
            "farm_obstacles": lambda: FarmObstaclesStrategy(),
            "evade_bomb_mobs": lambda: EvadeAndBombMobsStrategy(),
        }
    )
    assignments = AssignmentStore(Path(args.assignments))
    cache = StateCache()
    engine = DecisionEngine(registry, assignments, EngineConfig(max_path=30, danger_timer=args.danger_timer))
    control = BotControl(loop_delay=args.loop_delay)

    runner = None
    if not args.no_bot:
        runner = BotRunner(api=api, engine=engine, cache=cache, control=control, quiet=args.quiet)
        runner.start()

    if args.no_gui:
        # просто ждём поток
        if runner:
            runner.join()
        return 0

    app = create_app(cache=cache, assignments=assignments, registry=registry, control=control)
    uvicorn.run(app, host=args.gui_host, port=args.gui_port, log_level="warning" if args.quiet else "info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
