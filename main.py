from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Optional

import requests

from client import ApiClient
from model import GameState
from strategy import GreedyBomberStrategy

DEFAULT_TOKEN = "345c75ba-26c0-4f3e-acd4-09e63982ca52"
DEFAULT_BASE_URL = "https://games-test.datsteam.dev/api/"


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simple bot for DatsJingleBang")
    parser.add_argument("--token", default=os.getenv("DATS_TOKEN", DEFAULT_TOKEN), help="Auth token for API")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base url (with /api suffix)")
    parser.add_argument("--rps", type=float, default=2.0, help="Max requests per second (per client, arena+move combined)")
    parser.add_argument("--loop-delay", type=float, default=0.35, help="Delay between iterations (seconds)")
    parser.add_argument("--danger-timer", type=float, default=2.5, help="Timer threshold to treat bombs as dangerous")
    return parser.parse_args(argv)


def log_state(state: GameState) -> None:
    alive = sum(1 for b in state.bombers if b.alive)
    print(
        f"[arena] round={state.round} score={state.raw_score} "
        f"bombers alive={alive}/{len(state.bombers)} errors={state.errors}"
    )


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)

    api = ApiClient(base_url=args.base_url, token=args.token, max_rps=args.rps)
    strategy = GreedyBomberStrategy(timer_threshold=args.danger_timer)

    print(f"Starting bot with base_url={args.base_url}, rps={args.rps}")

    while True:
        try:
            state = api.get_arena()
        except requests.RequestException as exc:
            print(f"[arena] request error: {exc}")
            time.sleep(1.0)
            continue

        log_state(state)

        commands = strategy.decide(state)
        if not commands:
            time.sleep(args.loop_delay)
            continue

        try:
            response = api.send_move(commands)
            print(f"[move] response code={response.get('code')} errors={response.get('errors')}")
        except requests.RequestException as exc:
            print(f"[move] request error: {exc}")

        time.sleep(args.loop_delay)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
