from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Optional

Pos = Tuple[int, int]


def _pos(v: Any) -> Pos:
    return (int(v[0]), int(v[1]))


@dataclass(frozen=True)
class Bomb:
    pos: Pos
    range: int
    timer: float  # seconds

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Bomb":
        return Bomb(pos=_pos(d["pos"]), range=int(d["range"]), timer=float(d["timer"]))


@dataclass(frozen=True)
class Arena:
    walls: List[Pos]
    obstacles: List[Pos]
    bombs: List[Bomb]

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Arena":
        return Arena(
            walls=[_pos(x) for x in d.get("walls", [])],
            obstacles=[_pos(x) for x in d.get("obstacles", [])],
            bombs=[Bomb.from_dict(x) for x in d.get("bombs", [])],
        )


@dataclass(frozen=True)
class Bomber:
    id: str
    alive: bool
    pos: Pos
    armor: int
    bombs_available: int
    can_move: bool
    tier: str
    safe_time: int

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Bomber":
        return Bomber(
            id=str(d["id"]),
            alive=bool(d["alive"]),
            pos=_pos(d["pos"]),
            armor=int(d.get("armor", 0)),
            bombs_available=int(d.get("bombs_available", 0)),
            can_move=bool(d.get("can_move", True)),
            tier=str(d.get("tier", "")),
            safe_time=int(d.get("safe_time", 0)),
        )


@dataclass(frozen=True)
class Mob:
    id: str
    pos: Pos
    tier: str
    safe_time: int
    type: str

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Mob":
        return Mob(
            id=str(d.get("id", "")),
            pos=_pos(d["pos"]),
            tier=str(d.get("tier", "")),
            safe_time=int(d.get("safe_time", 0)),
            type=str(d.get("type", "")),
        )


@dataclass(frozen=True)
class Enemy:
    id: str
    pos: Pos
    tier: str
    safe_time: int

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Enemy":
        return Enemy(
            id=str(d.get("id", "")),
            pos=_pos(d["pos"]),
            tier=str(d.get("tier", "")),
            safe_time=int(d.get("safe_time", 0)),
        )


@dataclass(frozen=True)
class GameState:
    player: str
    round: str
    map_size: Tuple[int, int]
    bombers: List[Bomber]
    arena: Arena
    mobs: List[Mob]
    enemies: List[Enemy]
    raw_score: int
    errors: List[str]
    code: int

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "GameState":
        return GameState(
            player=str(d.get("player", "")),
            round=str(d.get("round", "")),
            map_size=(int(d["map_size"][0]), int(d["map_size"][1])),
            bombers=[Bomber.from_dict(x) for x in d.get("bombers", [])],
            arena=Arena.from_dict(d.get("arena", {})),
            mobs=[Mob.from_dict(x) for x in d.get("mobs", [])],
            enemies=[Enemy.from_dict(x) for x in d.get("enemies", [])],
            raw_score=int(d.get("raw_score", 0)),
            errors=[str(x) for x in d.get("errors", [])],
            code=int(d.get("code", 0)),
        )


@dataclass(frozen=True)
class MoveCommand:
    bomber_id: str
    path: List[Pos]
    bombs: List[Pos]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.bomber_id,
            "path": [[x, y] for (x, y) in self.path],
            "bombs": [[x, y] for (x, y) in self.bombs],
        }
