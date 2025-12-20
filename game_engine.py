
import requests
import json
import time
import threading
import queue
import heapq
from collections import deque
from typing import Dict, List, Tuple, Set, Optional, Any
from dataclasses import dataclass
from enum import Enum
import traceback

BASE_URL = "https://games-test.datsteam.dev"
TOKEN = "345c75ba-26c0-4f3e-acd4-09e63982ca52"
POLL_INTERVAL = 0.4  # seconds between game state requests
COMMAND_TIMEOUT = 0.5  # seconds timeout for API calls

HEADERS = {
    "accept": "application/json",
    "Content-Type": "application/json",
    "X-Auth-Token": TOKEN,
}

Pos = Tuple[int, int]


# ============================================================================
# DATA STRUCTURES
# ============================================================================

class UnitMode(Enum):
    """Unit behavior states"""
    SCOUT = "scout"        # Random exploration
    HUNT = "hunt"          # Chase enemies
    FARM = "farm"          # Destroy obstacles
    APPROACH = "approach"  # Moving to bomb position
    RETREAT = "retreat"    # Fleeing from danger
    WAIT = "wait"          # No bombs available


@dataclass
class Unit:
    """Player unit state"""
    id: str
    pos: Pos
    alive: bool
    armor: int
    bombs_available: int
    can_move: bool
    
    
@dataclass
class GameState:
    """Complete game arena state"""
    map_size: Tuple[int, int]
    units: Dict[str, Unit]
    enemies: List[Pos]
    mobs: List[Pos]
    walls: Set[Pos]
    obstacles: Set[Pos]
    bombs: Set[Pos]
    timestamp: float


class UnitState:
    """Persistent state for each unit across frames"""
    def __init__(self, unit_id: str):
        self.id = unit_id
        self.mode = UnitMode.SCOUT
        self.home: Optional[Pos] = None
        self.target: Optional[Pos] = None
        self.approach_path: List[Pos] = []
        self.last_bomb_time = 0.0


# ============================================================================
# API CLIENT
# ============================================================================

class ApiClient:
    """Communication with game server"""
    
    def __init__(self, base_url: str = BASE_URL, token: str = TOKEN):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "X-Auth-Token": token,
            "Content-Type": "application/json"
        })
    
    def get_arena(self) -> Tuple[bool, Dict[str, Any]]:
        """Fetch current game state"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/arena",
                timeout=COMMAND_TIMEOUT
            )
            if response.status_code == 200:
                return True, response.json()
            else:
                print(f"[API] GET /arena returned {response.status_code}")
                return False, {}
        except Exception as e:
            print(f"[API] GET /arena error: {e}")
            return False, {}
    
    def send_move(self, commands: List[Dict[str, Any]]) -> Tuple[bool, Dict[str, Any]]:
        """Send unit movement + bomb commands"""
        try:
            payload = {"bombers": commands}
            response = self.session.post(
                f"{self.base_url}/api/move",
                json=payload,
                timeout=COMMAND_TIMEOUT
            )
            if response.status_code == 200:
                return True, response.json()
            else:
                print(f"[API] POST /move returned {response.status_code}")
                return False, {}
        except Exception as e:
            print(f"[API] POST /move error: {e}")
            return False, {}


# ============================================================================
# PATHFINDING (BFS + A*)
# ============================================================================

class Pathfinder:
    """BFS-based pathfinding with obstacle awareness"""
    
    @staticmethod
    def neighbors4(p: Pos) -> List[Pos]:
        """Get 4-directional neighbors"""
        x, y = p
        return [(x+1, y), (x-1, y), (x, y+1), (x, y-1)]
    
    @staticmethod
    def in_bounds(p: Pos, w: int, h: int) -> bool:
        """Check if position is within map bounds"""
        return 0 <= p[0] < w and 0 <= p[1] < h
    
    @staticmethod
    def manhattan(a: Pos, b: Pos) -> int:
        """Manhattan distance"""
        return abs(a[0] - b[0]) + abs(a[1] - b[1])
    
    @staticmethod
    def find_path(start: Pos, goal: Pos, blocked: Set[Pos], 
                  w: int, h: int, max_len: int = 30) -> Optional[List[Pos]]:
        """
        BFS pathfinding: find shortest collision-free path
        
        Args:
            start: Starting position
            goal: Target position
            blocked: Set of blocked cells (walls, obstacles, bombs, units)
            w, h: Map dimensions
            max_len: Maximum path length
        
        Returns:
            List of positions (excluding start, including goal) or None
        """
        if goal in blocked or not Pathfinder.in_bounds(goal, w, h):
            return None
        
        if start == goal:
            return []
        
        # BFS
        queue = deque([start])
        prev = {start: None}
        
        while queue:
            current = queue.popleft()
            
            if current == goal:
                # Reconstruct path
                path = []
                while current != start:
                    path.append(current)
                    current = prev[current]
                path.reverse()
                return path[:max_len]
            
            for neighbor in Pathfinder.neighbors4(current):
                if not Pathfinder.in_bounds(neighbor, w, h):
                    continue
                if neighbor in blocked or neighbor in prev:
                    continue
                
                prev[neighbor] = current
                queue.append(neighbor)
        
        return None
    
    @staticmethod
    def find_nearest_objective(pos: Pos, objectives: List[Pos], 
                               blocked: Set[Pos], w: int, h: int) -> Optional[Pos]:
        """Find nearest accessible objective"""
        accessible = []
        for obj in objectives:
            if obj not in blocked:
                dist = Pathfinder.manhattan(pos, obj)
                accessible.append((dist, obj))
        
        if accessible:
            accessible.sort()
            return accessible[0][1]
        return None


# ============================================================================
# GAME STATE PARSER
# ============================================================================

class StateParser:
    """Parse raw JSON arena data into GameState"""
    
    @staticmethod
    def parse(data: Dict[str, Any]) -> Optional[GameState]:
        """Parse arena JSON into GameState"""
        try:
            map_size = tuple(data.get("map_size", [215, 215]))
            
            # Parse units
            units = {}
            for unit_data in data.get("bombers", []):
                if unit_data.get("alive"):
                    unit_id = unit_data["id"]
                    units[unit_id] = Unit(
                        id=unit_id,
                        pos=tuple(unit_data["pos"]),
                        alive=True,
                        armor=unit_data.get("armor", 0),
                        bombs_available=unit_data.get("bombs_available", 1),
                        can_move=unit_data.get("can_move", False)
                    )
            
            # Parse enemies
            enemies = [tuple(e["pos"]) for e in data.get("enemies", [])]
            
            # Parse mobs
            mobs = [tuple(m["pos"]) for m in data.get("mobs", [])]
            
            # Parse arena objects
            arena = data.get("arena", {})
            walls = {tuple(w) for w in arena.get("walls", [])}
            obstacles = {tuple(o) for o in arena.get("obstacles", [])}
            bombs = set()
            for b in arena.get("bombs", []):
                if isinstance(b, dict):
                    bombs.add(tuple(b["pos"]))
                else:
                    bombs.add(tuple(b))
            
            return GameState(
                map_size=map_size,
                units=units,
                enemies=enemies,
                mobs=mobs,
                walls=walls,
                obstacles=obstacles,
                bombs=bombs,
                timestamp=time.time()
            )
        
        except Exception as e:
            print(f"[Parser] Error: {e}")
            traceback.print_exc()
            return None


# ============================================================================
# UNIT CONTROLLER (AI)
# ============================================================================

class UnitController:
    """Decision-making for units: movement + bomb placement"""
    
    def __init__(self):
        self.unit_states: Dict[str, UnitState] = {}
        self.pathfinder = Pathfinder()
    
    def get_unit_state(self, unit_id: str) -> UnitState:
        """Get or create persistent state for unit"""
        if unit_id not in self.unit_states:
            self.unit_states[unit_id] = UnitState(unit_id)
        return self.unit_states[unit_id]
    
    def decide(self, unit: Unit, state: GameState) -> Tuple[List[Pos], List[Pos]]:
        """
        Decide movement path and bomb placement for a unit
        
        Returns: (path, bomb_positions)
        """
        u_state = self.get_unit_state(unit.id)
        w, h = state.map_size
        
        # Build blocked set
        blocked = state.walls | state.obstacles | state.bombs
        blocked |= {pos for u_id, u_obj in state.units.items() if u_id != unit.id for pos in [u_obj.pos]}
        
        path = []
        bombs = []
        
        # ===== THREAT DETECTION =====
        in_danger = self._is_in_danger(unit.pos, state)
        
        if in_danger:
            print(f"[Unit {unit.id[:8]}] DANGER DETECTED at {unit.pos}")
            u_state.mode = UnitMode.RETREAT
            escape_pos = self._find_escape(unit.pos, blocked, w, h)
            if escape_pos:
                escape_path = self.pathfinder.find_path(unit.pos, escape_pos, blocked, w, h)
                if escape_path:
                    path = escape_path
                    u_state.home = unit.pos
        
        # ===== OBJECTIVE SELECTION =====
        elif unit.bombs_available > 0:
            # Prioritize enemies within vision range
            nearby_enemies = [e for e in state.enemies if self.pathfinder.manhattan(unit.pos, e) < 20]
            
            if nearby_enemies:
                u_state.mode = UnitMode.HUNT
                target = min(nearby_enemies, key=lambda e: self.pathfinder.manhattan(unit.pos, e))
                path = self.pathfinder.find_path(unit.pos, target, blocked, w, h) or []
            
            elif state.obstacles:
                u_state.mode = UnitMode.FARM
                # Find nearest accessible obstacle
                nearest_obs = self.pathfinder.find_nearest_objective(
                    unit.pos, list(state.obstacles), blocked, w, h
                )
                if nearest_obs:
                    # Approach adjacent cell
                    stand_pos = self._choose_stand_cell(nearest_obs, unit.pos, blocked, w, h)
                    if stand_pos:
                        path = self.pathfinder.find_path(unit.pos, stand_pos, blocked, w, h) or []
                        if path and len(path) > 0:
                            bombs = [path[-1]]  # Plant at destination
                            u_state.home = unit.pos
                            u_state.approach_path = path
            else:
                # Scout
                u_state.mode = UnitMode.SCOUT
                path = self._scout_path(unit.pos, blocked, w, h, steps=5)
        
        else:
            u_state.mode = UnitMode.WAIT
        
        return path[:30], bombs  # Limit path to 30 cells
    
    def _is_in_danger(self, pos: Pos, state: GameState) -> bool:
        """Check if position is in bomb blast radius or adjacent to enemy"""
        # Adjacent to enemy
        for enemy in state.enemies:
            if self.pathfinder.manhattan(pos, enemy) == 1:
                return True
        
        # In bomb radius
        for bomb in state.bombs:
            if self.pathfinder.manhattan(pos, bomb) <= 3:
                return True
        
        return False
    
    def _find_escape(self, pos: Pos, blocked: Set[Pos], w: int, h: int) -> Optional[Pos]:
        """BFS to find nearest safe cell"""
        queue = deque([(pos, 0)])
        visited = {pos}
        
        while queue:
            current, dist = queue.popleft()
            
            if dist > 0:
                return current
            
            if dist > 10:
                break
            
            for neighbor in self.pathfinder.neighbors4(current):
                if not self.pathfinder.in_bounds(neighbor, w, h):
                    continue
                if neighbor in visited or neighbor in blocked:
                    continue
                
                visited.add(neighbor)
                queue.append((neighbor, dist + 1))
        
        return None
    
    def _choose_stand_cell(self, obstacle: Pos, unit_pos: Pos, blocked: Set[Pos], 
                          w: int, h: int) -> Optional[Pos]:
        """Choose adjacent cell to stand and place bomb"""
        candidates = []
        for neighbor in self.pathfinder.neighbors4(obstacle):
            if self.pathfinder.in_bounds(neighbor, w, h) and neighbor not in blocked:
                dist = self.pathfinder.manhattan(unit_pos, neighbor)
                candidates.append((dist, neighbor))
        
        if candidates:
            candidates.sort()
            return candidates[0][1]
        return None
    
    def _scout_path(self, pos: Pos, blocked: Set[Pos], w: int, h: int, steps: int = 5) -> List[Pos]:
        """Random exploration"""
        directions = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        current = pos
        prev = None
        visited = {pos}
        path = []
        
        for _ in range(steps):
            chosen = None
            for dx, dy in directions:
                neighbor = (current[0] + dx, current[1] + dy)
                
                if not self.pathfinder.in_bounds(neighbor, w, h):
                    continue
                if neighbor in blocked or neighbor in visited or neighbor == prev:
                    continue
                
                chosen = neighbor
                break
            
            if not chosen:
                break
            
            prev = current
            current = chosen
            visited.add(current)
            path.append(current)
        
        return path


# ============================================================================
# GAME ENGINE (Main Loop)
# ============================================================================

class GameEngine:
    """Main game loop: fetch state → decide → send commands"""
    
    def __init__(self):
        self.api = ApiClient()
        self.controller = UnitController()
        self.current_state: Optional[GameState] = None
        self.running = True
        self.state_queue: queue.Queue = queue.Queue()
        self.last_state_time = 0.0
    
    def fetch_state(self):
        """Fetch game state from server (runs in background thread)"""
        while self.running:
            try:
                success, data = self.api.get_arena()
                if success:
                    parsed = StateParser.parse(data)
                    if parsed:
                        self.current_state = parsed
                        self.state_queue.put(parsed)
                        print(f"[Game] State updated: {len(parsed.units)} units, "
                              f"{len(parsed.obstacles)} obstacles, {len(parsed.bombs)} bombs")
                
                time.sleep(POLL_INTERVAL)
            
            except Exception as e:
                print(f"[Game] Fetch state error: {e}")
                time.sleep(POLL_INTERVAL)
    
    def decide_and_send(self):
        """Decide unit actions and send commands"""
        while self.running:
            try:
                if self.current_state is None:
                    time.sleep(0.5)
                    continue
                
                state = self.current_state
                commands = []
                
                for unit_id, unit in state.units.items():
                    if not unit.can_move:
                        continue
                    
                    path, bombs = self.controller.decide(unit, state)
                    
                    commands.append({
                        "id": unit_id,
                        "path": [[p[0], p[1]] for p in path],
                        "bombs": [[b[0], b[1]] for b in bombs]
                    })
                    
                    print(f"  [{unit_id[:8]}] path={len(path)} bombs={len(bombs)}")
                
                if commands:
                    success, response = self.api.send_move(commands)
                    if success:
                        print(f"[Command] Sent {len(commands)} unit commands")
                    else:
                        print(f"[Command] Failed to send")
                
                time.sleep(POLL_INTERVAL)
            
            except Exception as e:
                print(f"[Game] Decide/send error: {e}")
                traceback.print_exc()
                time.sleep(POLL_INTERVAL)
    
    def run(self):
        """Start game loop with threaded fetching"""
        print("=" * 70)
        print("BOMBERMAN+ AUTOMATED GAME ENGINE")
        print(f"Server: {BASE_URL}")
        print("=" * 70)
        
        # Start background thread for fetching
        fetch_thread = threading.Thread(target=self.fetch_state, daemon=True)
        fetch_thread.start()
        
        # Main thread: decide and send
        try:
            self.decide_and_send()
        except KeyboardInterrupt:
            print("\n[Game] Shutdown requested")
            self.running = False


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    engine = GameEngine()
    engine.run()
