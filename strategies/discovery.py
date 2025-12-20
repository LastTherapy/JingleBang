from __future__ import annotations

import importlib
import pkgutil
from typing import Callable

from strategies.base import Strategy


def discover_strategy_factories() -> dict[str, Callable[[], Strategy]]:
    """Auto-import modules in strategies package and collect Strategy classes by `id`."

    Add a new strategy by:
      - creating strategies/my_strategy.py
      - defining a class with `id: str` and `decide_for_unit(...)`
    It will be discovered automatically (no need to edit main).
    """
    factories: dict[str, Callable[[], Strategy]] = {}

    import strategies  # package
    for m in pkgutil.iter_modules(strategies.__path__):
        name = m.name
        if name.startswith("_") or name in {"base", "discovery"}:
            continue
        mod = importlib.import_module(f"strategies.{name}")

        for obj in vars(mod).values():
            if isinstance(obj, type) and hasattr(obj, "id") and callable(getattr(obj, "decide_for_unit", None)):
                # instantiate once to validate id
                try:
                    sid = str(getattr(obj, "id"))
                except Exception:
                    continue
                if not sid:
                    continue
                # Keep first occurrence; explicit overrides can be done by naming collisions intentionally.
                factories.setdefault(sid, lambda cls=obj: cls())

    return factories
