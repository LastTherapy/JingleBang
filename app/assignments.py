from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AssignmentStore:
    path: Path
    _lock: threading.RLock = threading.RLock()
    _data: dict[str, str] = None  # bomber_id -> strategy_id
    _default: str = "farm_obstacles"

    def __post_init__(self) -> None:
        self._data = {}
        self.load()

    def load(self) -> None:
        with self._lock:
            if self.path.exists():
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            else:
                self._data = {}

    def save(self) -> None:
        with self._lock:
            self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_for(self, bomber_id: str) -> str:
        with self._lock:
            return self._data.get(bomber_id, self._default)

    def set_for(self, bomber_id: str, strategy_id: str) -> None:
        with self._lock:
            self._data[bomber_id] = strategy_id
            self.save()

    def dump(self) -> dict[str, str]:
        with self._lock:
            return dict(self._data)

    def set_default(self, strategy_id: str) -> None:
        with self._lock:
            self._default = strategy_id

    def get_default(self) -> str:
        with self._lock:
            return self._default
