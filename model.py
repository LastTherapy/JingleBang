from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


Pos = Tuple[int, int]


@dataclass
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
            id=d["id"],
            alive=bool(d["alive"]),
            pos=(int(d["pos"][0]), int(d["pos"][1])),
            armor=int(d["armor"]),
            bombs_available=int(d["bombs_available"]),
            can_move=bool(d["can_move"]),
            tier=str(d["tier"]),
            safe_time=int(d["safe_time"]),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "alive": self.alive,
            "pos": [self.pos[0], self.pos[1]],
            "armor": self.armor,
            "bombs_available": self.bombs_available,
            "can_move": self.can_move,
            "tier": self.tier,
            "safe_time": self.safe_time,
        }


@dataclass
class Mob:
    id: str
    type: str
    pos: Pos
    safe_time: int

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Mob":
        return Mob(
            id=d["id"],
            type=d["type"],
            pos=(int(d["pos"][0]), int(d["pos"][1])),
            safe_time=int(d["safe_time"]),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "pos": [self.pos[0], self.pos[1]],
            "safe_time": self.safe_time,
        }


@dataclass
class Arena:
    obstacles: List[Pos]
    walls: List[Pos]
    bombs: List[Any]  # пока пусто; тип уточнишь когда появится структура

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Arena":
        return Arena(
            obstacles=[(int(x), int(y)) for x, y in d.get("obstacles", [])],
            walls=[(int(x), int(y)) for x, y in d.get("walls", [])],
            bombs=d.get("bombs", []),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "obstacles": [[x, y] for x, y in self.obstacles],
            "walls": [[x, y] for x, y in self.walls],
            "bombs": self.bombs,
        }


@dataclass
class GameState:
    player: str
    round: str
    map_size: Tuple[int, int]
    bombers: List[Bomber]
    arena: Arena
    enemies: List[Any]
    mobs: List[Mob]
    code: int
    errors: List[Any]
    raw_score: int

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "GameState":
        return GameState(
            player=d["player"],
            round=d["round"],
            map_size=(int(d["map_size"][0]), int(d["map_size"][1])),
            bombers=[Bomber.from_dict(x) for x in d.get("bombers", [])],
            arena=Arena.from_dict(d["arena"]),
            enemies=d.get("enemies", []),
            mobs=[Mob.from_dict(x) for x in d.get("mobs", [])],
            code=int(d.get("code", 0)),
            errors=d.get("errors", []),
            raw_score=int(d.get("raw_score", 0)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "player": self.player,
            "round": self.round,
            "map_size": [self.map_size[0], self.map_size[1]],
            "bombers": [b.to_dict() for b in self.bombers],
            "arena": self.arena.to_dict(),
            "enemies": self.enemies,
            "mobs": [m.to_dict() for m in self.mobs],
            "code": self.code,
            "errors": self.errors,
            "raw_score": self.raw_score,
        }
