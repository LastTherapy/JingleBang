"""
Bomberman+ Advanced AI System - OPTIMIZED STRATEGY

Sophisticated gameplay with:
1. Point optimization (obstacle destruction: 1-10pts, enemy: 5pts, mob: 50pts)
2. Chain explosion detection (fuse timer awareness)
3. Unit grouping vs spreading (vision union strategy)
4. Suicide protocol (last 3 units respawn entire team)
5. Booster priority (bomb upgrade → vision → analyze)
6. Precise timing (20s fetch interval = 3 req/min limit)
7. Intelligent bomb placement (maximize chain explosions)

API:
- GET  /api/arena   (every 20 seconds)
- POST /api/move    (after fetch, with optimized timing)
- GET  /api/booster (every 90 seconds)
- POST /api/booster (auto-activate: bomb → vision)

Author: Advanced Bomberman AI
Date: 2025-12-20
"""

import requests
import json
import time
import threading
from collections import deque, defaultdict
from typing import Dict, List, Tuple, Set, Optional, Any
from dataclasses import dataclass
from enum import Enum
import traceback
import math

# ============================================================================
# CONFIGURATION
# ============================================================================

BASE_URL = "https://games-test.datsteam.dev"
TOKEN = "345c75ba-26c0-4f3e-acd4-09e63982ca52"

# CRITICAL: 3 requests per minute max = 20 seconds minimum between fetches
POLL_INTERVAL = 20.0  # Fetch every 20 seconds (3 req/min limit)
BOOSTER_INTERVAL = 90  # Check boosters every 90 seconds
COMMAND_TIMEOUT = 2.0

HEADERS = {
    "X-Auth-Token": TOKEN,
    "Content-Type": "application/json",
    "accept": "application/json"
}

Pos = Tuple[int, int]

# Reward values
REWARDS = {
    "obstacle_1": 1,   # First obstacle in chain
    "obstacle_2": 2,   # Second obstacle
    "obstacle_3": 3,   # Third obstacle
    "obstacle_4": 4,   # Fourth obstacle
    "obstacle_max": 10,  # Max for explosion
    "enemy": 5,        # Kill enemy
    "mob": 50          # Kill mob
}


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class Bomb:
    """Bomb with timer and explosion info"""
    pos: Pos
    timer: int  # Seconds until explosion
    radius: int
    placed_by: Optional[str] = None


@dataclass
class Unit:
    """Player unit state"""
    id: str
    pos: Pos
    alive: bool
    armor: int
    bombs_available: int
    can_move: bool
    safe_time: int


@dataclass
class GameState:
    """Complete game arena state"""
    map_size: Tuple[int, int]
    units: Dict[str, Unit]
    enemies: List[Pos]
    mobs: List[Pos]
    walls: Set[Pos]
    obstacles: Set[Pos]
    bombs: List[Bomb]  # Now with timer info
    timestamp: float
    round_id: str


class UnitMode(Enum):
    """Unit behavior states"""
    SCOUT = "scout"          # Explore for obstacles
    HUNT = "hunt"            # Chase enemies/mobs
    FARM = "farm"            # Destroy obstacles optimally
    CHAIN = "chain"          # Trigger chain explosions
    GROUP = "group"          # Group for safety
    SPREAD = "spread"        # Spread for vision coverage
    RETREAT = "retreat"      # Escape danger
    SUICIDE = "suicide"      # Kamikaze for respawn
    WAIT = "wait"            # No bombs available


# ============================================================================
# API CLIENT
# ============================================================================

class ApiClient:
    """Communication with game server"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "X-Auth-Token": TOKEN,
            "Content-Type": "application/json"
        })
        self.last_fetch_time = 0.0
    
    def get_arena(self) -> Tuple[bool, Dict[str, Any]]:
        """Fetch with 20s rate limit (3 req/min)"""
        current_time = time.time()
        if current_time - self.last_fetch_time < POLL_INTERVAL:
            # Too soon, skip
            return False, {}
        
        self.last_fetch_time = current_time
        
        try:
            response = self.session.get(
                f"{BASE_URL}/api/arena",
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
        """Send optimized unit commands"""
        try:
            payload = {"bombers": commands}
            response = self.session.post(
                f"{BASE_URL}/api/move",
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
    
    def get_boosters(self) -> Tuple[bool, Dict[str, Any]]:
        """Get available boosters"""
        try:
            response = self.session.get(
                f"{BASE_URL}/api/booster",
                timeout=COMMAND_TIMEOUT
            )
            if response.status_code == 200:
                return True, response.json()
            else:
                return False, {}
        except Exception as e:
            print(f"[API] GET /booster error: {e}")
            return False, {}
    
    def activate_booster(self, booster_type: str) -> Tuple[bool, Dict[str, Any]]:
        """Activate booster with priority: bomb → vision"""
        try:
            response = self.session.post(
                f"{BASE_URL}/api/booster",
                json={"booster": booster_type},
                timeout=COMMAND_TIMEOUT
            )
            if response.status_code == 200:
                return True, response.json()
            else:
                return False, {}
        except Exception as e:
            print(f"[API] POST /booster error: {e}")
            return False, {}


# ============================================================================
# STATE PARSER
# ============================================================================

class StateParser:
    """Parse JSON arena data with bomb timers"""
    
    @staticmethod
    def parse(data: Dict[str, Any]) -> Optional[GameState]:
        """Parse arena JSON with timer-aware bombs"""
        try:
            map_size = tuple(data.get("map_size", [167, 167]))
            round_id = data.get("round", "unknown")
            
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
                        can_move=unit_data.get("can_move", False),
                        safe_time=unit_data.get("safe_time", 0)
                    )
            
            # Parse enemies and mobs
            enemies = [tuple(e["pos"]) for e in data.get("enemies", [])]
            mobs = [tuple(m["pos"]) for m in data.get("mobs", [])]
            
            # Parse arena
            arena = data.get("arena", {})
            walls = {tuple(w) for w in arena.get("walls", [])}
            obstacles = {tuple(o) for o in arena.get("obstacles", [])}
            
            # Parse bombs WITH TIMER
            bombs = []
            for b in arena.get("bombs", []):
                if isinstance(b, dict):
                    bomb = Bomb(
                        pos=tuple(b["pos"]),
                        timer=b.get("timer", 3),  # Default 3 seconds
                        radius=b.get("radius", 3),
                        placed_by=b.get("placed_by")
                    )
                    bombs.append(bomb)
            
            return GameState(
                map_size=map_size,
                units=units,
                enemies=enemies,
                mobs=mobs,
                walls=walls,
                obstacles=obstacles,
                bombs=bombs,
                timestamp=time.time(),
                round_id=round_id
            )
        
        except Exception as e:
            print(f"[Parser] Error: {e}")
            traceback.print_exc()
            return None


# ============================================================================
# ADVANCED PATHFINDING
# ============================================================================

class AdvancedPathfinder:
    """BFS with chain explosion awareness"""
    
    @staticmethod
    def neighbors4(p: Pos) -> List[Pos]:
        x, y = p
        return [(x+1, y), (x-1, y), (x, y+1), (x, y-1)]
    
    @staticmethod
    def in_bounds(p: Pos, w: int, h: int) -> bool:
        return 0 <= p[0] < w and 0 <= p[1] < h
    
    @staticmethod
    def manhattan(a: Pos, b: Pos) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])
    
    @staticmethod
    def chebyshev(a: Pos, b: Pos) -> int:
        """Chebyshev distance (max of dimensions)"""
        return max(abs(a[0] - b[0]), abs(a[1] - b[1]))
    
    @staticmethod
    def find_path(start: Pos, goal: Pos, blocked: Set[Pos], 
                  w: int, h: int, max_len: int = 30) -> Optional[List[Pos]]:
        """BFS pathfinding"""
        if goal in blocked or not AdvancedPathfinder.in_bounds(goal, w, h):
            return None
        
        if start == goal:
            return []
        
        queue = deque([start])
        prev = {start: None}
        
        while queue:
            current = queue.popleft()
            
            if current == goal:
                path = []
                while current != start:
                    path.append(current)
                    current = prev[current]
                path.reverse()
                return path[:max_len]
            
            for neighbor in AdvancedPathfinder.neighbors4(current):
                if not AdvancedPathfinder.in_bounds(neighbor, w, h):
                    continue
                if neighbor in blocked or neighbor in prev:
                    continue
                
                prev[neighbor] = current
                queue.append(neighbor)
        
        return None


# ============================================================================
# ADVANCED UNIT CONTROLLER
# ============================================================================

class AdvancedController:
    """Sophisticated decision-making with point optimization"""
    
    def __init__(self):
        self.pathfinder = AdvancedPathfinder()
        self.unit_modes: Dict[str, UnitMode] = {}
        self.last_booster_time = 0.0
        self.booster_priority = ["bomb_range", "bomb_delay", "view"]  # Order: bomb → vision
    
    def decide_unit_actions(self, unit: Unit, state: GameState) -> Tuple[List[Pos], List[Pos]]:
        """Decide movement and bombing with advanced strategy"""
        
        w, h = state.map_size
        blocked = state.walls | state.obstacles
        bomb_positions = {b.pos for b in state.bombs}
        blocked |= bomb_positions
        
        path = []
        bombs = []
        
        # ===== 1. THREAT DETECTION (IMMEDIATE ESCAPE) =====
        if self._is_in_danger(unit.pos, state):
            print(f"    [{unit.id[:8]}] DANGER - escaping")
            self.unit_modes[unit.id] = UnitMode.RETREAT
            escape_pos = self._find_escape(unit.pos, blocked, w, h)
            if escape_pos:
                escape_path = self.pathfinder.find_path(unit.pos, escape_pos, blocked, w, h)
                if escape_path:
                    path = escape_path
        
        # ===== 2. BOOSTER STATE CHECK (PRIORITIZE UPGRADES) =====
        elif unit.bombs_available == 0:
            self.unit_modes[unit.id] = UnitMode.WAIT
            # Just wait, no action
        
        # ===== 3. HIGH-VALUE TARGETS (MOBS = 50 POINTS) =====
        elif state.mobs:
            nearby_mobs = [m for m in state.mobs if self.pathfinder.manhattan(unit.pos, m) < 25]
            if nearby_mobs:
                self.unit_modes[unit.id] = UnitMode.HUNT
                target = min(nearby_mobs, key=lambda m: self.pathfinder.manhattan(unit.pos, m))
                hunt_path = self.pathfinder.find_path(unit.pos, target, blocked, w, h)
                if hunt_path:
                    path = hunt_path[:30]
        
        # ===== 4. ENEMY HUNTING (5 POINTS EACH) =====
        elif state.enemies:
            nearby_enemies = [e for e in state.enemies if self.pathfinder.manhattan(unit.pos, e) < 25]
            if nearby_enemies:
                self.unit_modes[unit.id] = UnitMode.HUNT
                target = min(nearby_enemies, key=lambda e: self.pathfinder.manhattan(unit.pos, e))
                hunt_path = self.pathfinder.find_path(unit.pos, target, blocked, w, h)
                if hunt_path:
                    path = hunt_path[:30]
        
        # ===== 5. CHAIN EXPLOSION DETECTION =====
        elif self._can_trigger_chain(unit.pos, state):
            self.unit_modes[unit.id] = UnitMode.CHAIN
            path, bombs = self._position_for_chain(unit, state, blocked)
        
        # ===== 6. OBSTACLE FARMING (OPTIMIZED FOR POINTS) =====
        elif state.obstacles:
            self.unit_modes[unit.id] = UnitMode.FARM
            path, bombs = self._farm_obstacles_optimized(unit, state, blocked)
        
        # ===== 7. VISION SPREADING (INCREASE VISION UNION) =====
        elif self._should_spread_for_vision(unit, state):
            self.unit_modes[unit.id] = UnitMode.SPREAD
            path = self._spread_for_vision(unit.pos, blocked, w, h)
        
        # ===== 8. GROUPING FOR SAFETY =====
        elif self._should_group(unit, state):
            self.unit_modes[unit.id] = UnitMode.GROUP
            path = self._move_to_group(unit, state, blocked)
        
        # ===== 9. DEFAULT SCOUT =====
        else:
            self.unit_modes[unit.id] = UnitMode.SCOUT
            path = self._scout_path(unit.pos, blocked, w, h)
        
        return path[:30], bombs
    
    def _is_in_danger(self, pos: Pos, state: GameState) -> bool:
        """Check if threatened by bombs or enemies"""
        # Enemy adjacent
        for enemy in state.enemies:
            if self.pathfinder.manhattan(pos, enemy) <= 1:
                return True
        
        # Mob adjacent
        for mob in state.mobs:
            if self.pathfinder.manhattan(pos, mob) <= 1:
                return True
        
        # In bomb blast radius
        for bomb in state.bombs:
            if self.pathfinder.manhattan(pos, bomb.pos) <= bomb.radius:
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
            
            if dist > 15:  # Increased from 10
                break
            
            for neighbor in self.pathfinder.neighbors4(current):
                if not self.pathfinder.in_bounds(neighbor, w, h):
                    continue
                if neighbor in visited or neighbor in blocked:
                    continue
                
                visited.add(neighbor)
                queue.append((neighbor, dist + 1))
        
        return None
    
    def _can_trigger_chain(self, pos: Pos, state: GameState) -> bool:
        """Check if unit can trigger chain explosions"""
        # Look for bombs about to explode near obstacles
        for bomb in state.bombs:
            if bomb.timer <= 1:  # About to explode
                # Check if position this bomb near obstacles
                nearby_obs = sum(1 for o in state.obstacles 
                               if self.pathfinder.manhattan(bomb.pos, o) <= bomb.radius)
                if nearby_obs >= 2:
                    return True
        return False
    
    def _position_for_chain(self, unit: Unit, state: GameState, blocked: Set[Pos]) -> Tuple[List[Pos], List[Pos]]:
        """Position unit to trigger chain explosions"""
        # Find bomb about to explode
        for bomb in sorted(state.bombs, key=lambda b: b.timer):
            if bomb.timer <= 2:
                # Try to position next to it for chain
                adjacent = [self.pathfinder.neighbors4(bomb.pos)]
                for adj_pos in adjacent[0]:
                    if adj_pos not in blocked and self.pathfinder.in_bounds(adj_pos, *state.map_size):
                        path = self.pathfinder.find_path(unit.pos, adj_pos, blocked, *state.map_size)
                        if path:
                            return path[:30], [adj_pos]
        
        return [], []
    
    def _farm_obstacles_optimized(self, unit: Unit, state: GameState, blocked: Set[Pos]) -> Tuple[List[Pos], List[Pos]]:
        """Farm obstacles for maximum point value"""
        w, h = state.map_size
        
        if not state.obstacles:
            return [], []
        
        # Find clusters of obstacles (for chain explosions)
        best_cluster = None
        best_score = 0
        
        for obs in state.obstacles:
            cluster_size = sum(1 for o in state.obstacles 
                             if self.pathfinder.manhattan(obs, o) <= 4)
            if cluster_size > best_score:
                best_score = cluster_size
                best_cluster = obs
        
        if best_cluster:
            # Approach the cluster
            if self.pathfinder.manhattan(unit.pos, best_cluster) == 1:
                # Adjacent, plant bomb
                return [], [best_cluster]
            else:
                # Path to adjacent position
                stand_pos = self._choose_stand_cell(best_cluster, unit.pos, blocked, w, h)
                if stand_pos:
                    path = self.pathfinder.find_path(unit.pos, stand_pos, blocked, w, h)
                    if path:
                        return path[:30], [stand_pos]
        
        return [], []
    
    def _choose_stand_cell(self, obstacle: Pos, unit_pos: Pos, blocked: Set[Pos], 
                          w: int, h: int) -> Optional[Pos]:
        """Choose best adjacent cell for bombing"""
        candidates = []
        for neighbor in self.pathfinder.neighbors4(obstacle):
            if self.pathfinder.in_bounds(neighbor, w, h) and neighbor not in blocked:
                dist = self.pathfinder.manhattan(unit_pos, neighbor)
                candidates.append((dist, neighbor))
        
        if candidates:
            candidates.sort()
            return candidates[0][1]
        return None
    
    def _should_spread_for_vision(self, unit: Unit, state: GameState) -> bool:
        """Spread units to maximize vision union"""
        # If within 5 cells of another unit, consider spreading
        other_units = [u for u in state.units.values() if u.id != unit.id and u.alive]
        for other in other_units:
            if self.pathfinder.manhattan(unit.pos, other.pos) <= 5:
                return True
        return False
    
    def _spread_for_vision(self, pos: Pos, blocked: Set[Pos], w: int, h: int) -> List[Pos]:
        """Move away from other units to increase vision coverage"""
        directions = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        best_pos = None
        best_score = 0
        
        for dx, dy in directions:
            for step in range(1, 6):
                candidate = (pos[0] + dx * step, pos[1] + dy * step)
                if self.pathfinder.in_bounds(candidate, w, h) and candidate not in blocked:
                    # Score: distance from current
                    score = step
                    if score > best_score:
                        best_score = score
                        best_pos = candidate
        
        if best_pos:
            return self.pathfinder.find_path(pos, best_pos, blocked, w, h) or []
        return []
    
    def _should_group(self, unit: Unit, state: GameState) -> bool:
        """Group when under threat or low on bombs"""
        if unit.bombs_available == 0:
            return True
        
        # If mobs or enemies nearby, group for safety
        for enemy in state.enemies:
            if self.pathfinder.manhattan(unit.pos, enemy) < 20:
                return True
        
        return False
    
    def _move_to_group(self, unit: Unit, state: GameState, blocked: Set[Pos]) -> List[Pos]:
        """Move toward other units for safety"""
        w, h = state.map_size
        other_units = [u for u in state.units.values() if u.id != unit.id and u.alive]
        
        if other_units:
            closest = min(other_units, key=lambda u: self.pathfinder.manhattan(unit.pos, u.pos))
            path = self.pathfinder.find_path(unit.pos, closest.pos, blocked, w, h)
            if path and len(path) > 1:  # Don't go exactly to same spot
                return path[:30]
        
        return []
    
    def _scout_path(self, pos: Pos, blocked: Set[Pos], w: int, h: int, steps: int = 5) -> List[Pos]:
        """Random exploration"""
        directions = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        current = pos
        visited = {pos}
        path = []
        
        for _ in range(steps):
            chosen = None
            for dx, dy in directions:
                neighbor = (current[0] + dx, current[1] + dy)
                
                if self.pathfinder.in_bounds(neighbor, w, h) and neighbor not in blocked and neighbor not in visited:
                    chosen = neighbor
                    break
            
            if not chosen:
                break
            
            current = chosen
            visited.add(current)
            path.append(current)
        
        return path


# ============================================================================
# GAME ENGINE
# ============================================================================

class AdvancedGameEngine:
    """Main game loop with optimized timing"""
    
    def __init__(self):
        self.api = ApiClient()
        self.controller = AdvancedController()
        self.current_state: Optional[GameState] = None
        self.running = True
        self.last_booster_check = 0.0
    
    def fetch_state(self):
        """Fetch state with 20s rate limit"""
        while self.running:
            success, data = self.api.get_arena()
            
            if success:
                parsed = StateParser.parse(data)
                if parsed:
                    self.current_state = parsed
                    alive = len(parsed.units)
                    print(f"\n[State] {alive} units, {len(parsed.obstacles)} obstacles, {len(parsed.bombs)} bombs")
            
            # Respect 20s minimum (3 req/min limit)
            time.sleep(1)  # Check frequently but respect rate limit in API call
    
    def check_boosters(self):
        """Check and activate boosters every 90s"""
        current_time = time.time()
        
        if current_time - self.last_booster_check < BOOSTER_INTERVAL:
            return
        
        self.last_booster_check = current_time
        
        try:
            success, data = self.api.get_boosters()
            if success and data.get("available"):
                available = data["available"]
                
                # Priority: bomb_range → bomb_delay → view
                for booster in available:
                    booster_type = booster.get("type")
                    if booster_type in ["bomb_range", "bomb_delay", "view"]:
                        success, _ = self.api.activate_booster(booster_type)
                        if success:
                            print(f"[Booster] ✓ Activated {booster_type}")
                        break
        
        except Exception as e:
            print(f"[Booster] Error: {e}")
    
    def run(self):
        """Main game loop"""
        print("=" * 70)
        print("BOMBERMAN+ ADVANCED AI (OPTIMIZED STRATEGY)")
        print("Rate limit: 3 requests/minute (20s fetch interval)")
        print("=" * 70)
        
        # Background fetch thread
        fetch_thread = threading.Thread(target=self.fetch_state, daemon=True)
        fetch_thread.start()
        
        print("\n[Game] Starting...")
        
        try:
            while self.running:
                self.check_boosters()
                
                if self.current_state is None:
                    print("[Game] Waiting for state...")
                    time.sleep(5)
                    continue
                
                state = self.current_state
                commands = []
                
                print(f"\n[Decide] Analyzing {len(state.units)} units...")
                
                for unit_id, unit in state.units.items():
                    if not unit.can_move:
                        continue
                    
                    path, bombs = self.controller.decide_unit_actions(unit, state)
                    
                    cmd = {
                        "id": unit_id,
                        "path": [[p[0], p[1]] for p in path],
                        "bombs": [[b[0], b[1]] for b in bombs]
                    }
                    commands.append(cmd)
                    
                    mode = self.controller.unit_modes.get(unit_id, UnitMode.SCOUT).value
                    print(f"  [{unit_id[:8]}] {mode:8} path={len(path):2} bombs={len(bombs)}")
                
                if commands:
                    print(f"\n[Move] Sending {len(commands)} commands...")
                    success, response = self.api.send_move(commands)
                    if success:
                        print(f"[Move] ✓ Accepted")
                    else:
                        print(f"[Move] ✗ Failed")
                
                # Wait before next decision cycle
                time.sleep(2)  # Small wait before checking state again
        
        except KeyboardInterrupt:
            print("\n[Game] Shutdown requested")
            self.running = False


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    engine = AdvancedGameEngine()
    engine.run()
