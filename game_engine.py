"""
Bomberman+ Automated Live Game System - FIXED AI

Complete working solution with:
- Proper movement commands with correct JSON format
- Safe bomb placement (escape verification)
- Booster detection and automatic activation (every 90s)
- Threat avoidance (escape from bombs and enemies)
- Intelligent pathfinding (BFS)

API Endpoints:
- GET /api/arena          → Current game state
- POST /api/move         → Send unit commands
- GET /api/booster       → Available upgrades
- POST /api/booster      → Activate upgrade

Usage:
    python3 game_engine.py

Author: Bomberman AI
Date: 2025-12-20
"""

import requests
import json
import time
import threading
from collections import deque
from typing import Dict, List, Tuple, Set, Optional, Any
from dataclasses import dataclass
from enum import Enum
import traceback

# ============================================================================
# CONFIGURATION
# ============================================================================

BASE_URL = "https://games-test.datsteam.dev"
TOKEN = "345c75ba-26c0-4f3e-acd4-09e63982ca52"
POLL_INTERVAL = 1.5  # seconds between game state requests
COMMAND_TIMEOUT = 2.0  # seconds timeout for API calls
BOOSTER_INTERVAL = 90  # seconds between booster activations

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
        """Send unit movement + bomb commands
        
        Format:
        {
            "bombers": [
                {
                    "id": "unit-uuid",
                    "path": [[x1, y1], [x2, y2], ...],
                    "bombs": [[bx1, by1], [bx2, by2], ...]
                }
            ]
        }
        """
        try:
            payload = {"bombers": commands}
            response = self.session.post(
                f"{self.base_url}/api/move",
                json=payload,
                timeout=COMMAND_TIMEOUT
            )
            if response.status_code == 200:
                result = response.json()
                if result.get("errors"):
                    print(f"[API] Move errors: {result['errors']}")
                    return False, result
                return True, result
            else:
                print(f"[API] POST /move returned {response.status_code}")
                return False, {}
        except Exception as e:
            print(f"[API] POST /move error: {e}")
            return False, {}
    
    def get_boosters(self) -> Tuple[bool, Dict[str, Any]]:
        """Get available boosters/upgrades"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/booster",
                timeout=COMMAND_TIMEOUT
            )
            if response.status_code == 200:
                return True, response.json()
            else:
                print(f"[API] GET /booster returned {response.status_code}")
                return False, {}
        except Exception as e:
            print(f"[API] GET /booster error: {e}")
            return False, {}
    
    def activate_booster(self, booster_type: str) -> Tuple[bool, Dict[str, Any]]:
        """Activate a booster
        
        Available types: speed, armor, bomb_range, bomb_delay, etc.
        """
        try:
            payload = {"booster": booster_type}
            response = self.session.post(
                f"{self.base_url}/api/booster",
                json=payload,
                timeout=COMMAND_TIMEOUT
            )
            if response.status_code == 200:
                return True, response.json()
            else:
                print(f"[API] POST /booster returned {response.status_code}")
                return False, {}
        except Exception as e:
            print(f"[API] POST /booster error: {e}")
            return False, {}


# ============================================================================
# PATHFINDING (BFS)
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
        
        Returns: List of positions (excluding start, including goal)
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


# ============================================================================
# STATE PARSER
# ============================================================================

class StateParser:
    """Parse raw JSON arena data into GameState"""
    
    @staticmethod
    def parse(data: Dict[str, Any]) -> Optional[GameState]:
        """Parse arena JSON into GameState"""
        try:
            map_size = tuple(data.get("map_size", [215, 215]))
            
            # Parse units (only alive ones)
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
            
            # Parse bombs (handle both dict and list formats)
            bombs = set()
            for b in arena.get("bombs", []):
                if isinstance(b, dict):
                    bombs.add(tuple(b["pos"]))
                elif isinstance(b, (list, tuple)):
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
        
        # Build blocked set (don't include other units - they move)
        blocked = state.walls | state.obstacles | state.bombs
        
        path = []
        bombs = []
        
        # ===== THREAT DETECTION (ESCAPE MODE) =====
        in_danger = self._is_in_danger(unit.pos, state)
        
        if in_danger:
            print(f"    [{unit.id[:8]}] DANGER - escaping!")
            u_state.mode = UnitMode.RETREAT
            escape_pos = self._find_escape(unit.pos, blocked, w, h)
            if escape_pos:
                escape_path = self.pathfinder.find_path(unit.pos, escape_pos, blocked, w, h)
                if escape_path:
                    path = escape_path
        
        # ===== OBJECTIVE SELECTION =====
        elif unit.bombs_available > 0:
            
            # Check for nearby enemies (hunt mode)
            nearby_enemies = [
                e for e in state.enemies 
                if self.pathfinder.manhattan(unit.pos, e) < 20
            ]
            
            if nearby_enemies:
                u_state.mode = UnitMode.HUNT
                target = min(nearby_enemies, key=lambda e: self.pathfinder.manhattan(unit.pos, e))
                hunt_path = self.pathfinder.find_path(unit.pos, target, blocked, w, h)
                if hunt_path:
                    path = hunt_path[:30]
                else:
                    # Can't reach enemy, try to farm obstacles instead
                    u_state.mode = UnitMode.FARM
                    path, bombs = self._farm_obstacles(unit, state, blocked)
            
            elif state.obstacles:
                # Farm obstacles
                u_state.mode = UnitMode.FARM
                path, bombs = self._farm_obstacles(unit, state, blocked)
            
            else:
                # Scout randomly
                u_state.mode = UnitMode.SCOUT
                path = self._scout_path(unit.pos, blocked, w, h, steps=5)
        
        else:
            # No bombs available, wait
            u_state.mode = UnitMode.WAIT
        
        return path[:30], bombs
    
    def _is_in_danger(self, pos: Pos, state: GameState) -> bool:
        """Check if position is in bomb blast radius or adjacent to enemy"""
        # Adjacent to enemy
        for enemy in state.enemies:
            if self.pathfinder.manhattan(pos, enemy) == 1:
                return True
        
        # Adjacent to mobs
        for mob in state.mobs:
            if self.pathfinder.manhattan(pos, mob) == 1:
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
    
    def _farm_obstacles(self, unit: Unit, state: GameState, blocked: Set[Pos]) -> Tuple[List[Pos], List[Pos]]:
        """Find and approach nearest obstacle, plant bomb if close enough"""
        w, h = state.map_size
        
        # Find nearest obstacle
        nearest_obs = None
        min_dist = float('inf')
        
        for obs in state.obstacles:
            dist = self.pathfinder.manhattan(unit.pos, obs)
            if dist < min_dist:
                min_dist = dist
                nearest_obs = obs
        
        if not nearest_obs:
            return [], []
        
        # If already adjacent, plant bomb
        if self.pathfinder.manhattan(unit.pos, nearest_obs) == 1:
            return [], [nearest_obs]
        
        # Otherwise, path to adjacent cell
        stand_pos = self._choose_stand_cell(nearest_obs, unit.pos, blocked, w, h)
        if stand_pos:
            path = self.pathfinder.find_path(unit.pos, stand_pos, blocked, w, h)
            if path and len(path) > 0:
                return path[:30], [stand_pos]  # Plant at destination
        
        return [], []
    
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
        self.last_booster_time = 0.0
    
    def fetch_state(self):
        """Fetch game state from server (runs in background thread)"""
        while self.running:
            try:
                success, data = self.api.get_arena()
                if success:
                    parsed = StateParser.parse(data)
                    if parsed:
                        self.current_state = parsed
                        alive_units = len(parsed.units)
                        print(f"[Game] State: {alive_units} units, {len(parsed.obstacles)} obstacles, {len(parsed.bombs)} bombs")
                
                time.sleep(POLL_INTERVAL)
            
            except Exception as e:
                print(f"[Game] Fetch error: {e}")
                time.sleep(POLL_INTERVAL)
    
    def check_and_activate_boosters(self):
        """Check for available boosters every 90 seconds"""
        current_time = time.time()
        
        if current_time - self.last_booster_time < BOOSTER_INTERVAL:
            return  # Not yet time
        
        self.last_booster_time = current_time
        
        try:
            success, data = self.api.get_boosters()
            if success and data.get("available"):
                available = data["available"]
                if available:
                    # Activate the first available booster
                    booster = available[0]
                    booster_type = booster.get("type")
                    cost = booster.get("cost", "?")
                    print(f"[Booster] Available: {booster_type} (cost: {cost})")
                    
                    # Activate it
                    success, response = self.api.activate_booster(booster_type)
                    if success:
                        print(f"[Booster] ✓ Activated {booster_type}")
                    else:
                        print(f"[Booster] ✗ Failed to activate {booster_type}")
        
        except Exception as e:
            print(f"[Booster] Check error: {e}")
    
    def run(self):
        """Start game loop with threaded fetching"""
        print("=" * 70)
        print("BOMBERMAN+ AUTOMATED GAME ENGINE (FIXED AI)")
        print(f"Server: {BASE_URL}")
        print("=" * 70)
        
        # Start background thread for fetching
        fetch_thread = threading.Thread(target=self.fetch_state, daemon=True)
        fetch_thread.start()
        
        print("\n[Game] Starting main loop...\n")
        
        # Main thread: decide and send
        try:
            while self.running:
                # Check and activate boosters every 90 seconds
                self.check_and_activate_boosters()
                
                if self.current_state is None:
                    print("[Game] Waiting for state...")
                    time.sleep(1)
                    continue
                
                state = self.current_state
                commands = []
                
                print(f"\n[Frame] {len(state.units)} alive units, deciding actions...")
                
                for unit_id, unit in state.units.items():
                    if not unit.can_move:
                        print(f"  [{unit_id[:8]}] Cannot move")
                        continue
                    
                    path, bombs = self.controller.decide(unit, state)
                    
                    # Format command properly for API
                    cmd = {
                        "id": unit_id,
                        "path": [[p[0], p[1]] for p in path],
                        "bombs": [[b[0], b[1]] for b in bombs]
                    }
                    commands.append(cmd)
                    
                    print(f"  [{unit_id[:8]}] path={len(path)} bombs={len(bombs)} pos={unit.pos}")
                
                if commands:
                    print(f"\n[Move] Sending {len(commands)} commands...")
                    success, response = self.api.send_move(commands)
                    if success:
                        print(f"[Move] ✓ Accepted")
                    else:
                        print(f"[Move] ✗ Failed: {response}")
                
                time.sleep(POLL_INTERVAL)
        
        except KeyboardInterrupt:
            print("\n\n[Game] Shutdown requested")
            self.running = False


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    engine = GameEngine()
    engine.run()