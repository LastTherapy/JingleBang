from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AssignmentStore:
    path: Path
    default_strategy: str = "farm_obstacles"

    _lock: threading.RLock = threading.RLock()
    _data: dict[str, str] | None = None  # bomber_id -> strategy_id

    def __post_init__(self) -> None:
        self._data = {}
        self.load()

    def load(self) -> None:
        with self._lock:
            if self.path.exists():
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self.default_strategy = raw.get("default", self.default_strategy)
                self._data = dict(raw.get("per_bomber", {}))
            else:
                self._data = {}

    def save(self) -> None:
        with self._lock:
            payload = {"default": self.default_strategy, "per_bomber": self._data}
            self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_for(self, bomber_id: str) -> str:
        with self._lock:
            return self._data.get(bomber_id, self.default_strategy)

    def set_for(self, bomber_id: str, strategy_id: str) -> None:
        with self._lock:
            self._data[bomber_id] = strategy_id
            self.save()

    def set_default(self, strategy_id: str) -> None:
        with self._lock:
            self.default_strategy = strategy_id
            self.save()

    def dump(self) -> dict:
        with self._lock:
            return {"default": self.default_strategy, "per_bomber": dict(self._data)}
