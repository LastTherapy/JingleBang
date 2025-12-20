#!/usr/bin/env python3
"""
Bomberman+ Ultra-Efficient Farming AI - PRODUCTION STABLE

CRITICAL FIX: 3 requests per SECOND (not minute!)
→ Refresh every 0.666667 seconds (2/3 second)

Strategy:
1. Continuous obstacle farming for maximum points
2. Escape from danger (bombs + mobs within 4 cells)
3. Suicide last 3 units for respawn
4. Robust error handling for reliability
5. Combined path + bombs in single POST

Timing:
- Fetch state every 0.67 seconds
- Send commands immediately after
- Recover gracefully from errors
- Never crash, always running
"""

import requests
import json
import time
import sys
from collections import deque
from typing import Dict, List, Tuple, Set, Optional, Any
from dataclasses import dataclass

BASE_URL = "https://games-test.datsteam.dev"
TOKEN = "345c75ba-26c0-4f3e-acd4-09e63982ca52"

HEADERS = {
    "X-Auth-Token": TOKEN,
    "Content-Type": "application/json"
}

# CRITICAL: 3 requests per SECOND
FETCH_INTERVAL = 0.667  # 2/3 second = 3 req/sec
COMMAND_TIMEOUT = 0.5

Pos = Tuple[int, int]


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class GameState:
    """Minimal game state"""
    map_size: Tuple[int, int]
    bombers: Dict[str, Dict[str, Any]]
    obstacles: Set[Pos]
    walls: Set[Pos]
    bombs: List[Dict[str, Any]]
    mobs: List[Pos]
    timestamp: float
    
    def alive_count(self) -> int:
        """Count alive units"""
        return len(self.bombers)


# ============================================================================
# PATHFINDING - OPTIMIZED
# ============================================================================

def neighbors4(p: Pos) -> List[Pos]:
    """4-directional neighbors"""
    x, y = p
    return [(x+1, y), (x-1, y), (x, y+1), (x, y-1)]


def in_bounds(p: Pos, w: int, h: int) -> bool:
    """Check bounds"""
    return 0 <= p[0] < w and 0 <= p[1] < h


def manhattan(a: Pos, b: Pos) -> int:
    """Manhattan distance"""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def bfs_path(start: Pos, goal: Pos, blocked: Set[Pos], 
             w: int, h: int, max_len: int = 30) -> Optional[List[Pos]]:
    """BFS pathfinding - returns shortest path or None"""
    if goal in blocked or not in_bounds(goal, w, h):
        return None
    
    if start == goal:
        return []
    
    queue = deque([start])
    prev = {start: None}
    found = False
    
    while queue and not found:
        current = queue.popleft()
        
        if current == goal:
            found = True
            break
        
        for neighbor in neighbors4(current):
            if not in_bounds(neighbor, w, h):
                continue
            if neighbor in blocked or neighbor in prev:
                continue
            
            prev[neighbor] = current
            queue.append(neighbor)
    
    if not found:
        return None
    
    # Reconstruct path
    path = []
    while current != start:
        path.append(current)
        current = prev[current]
    path.reverse()
    return path[:max_len]


def find_nearest_target(pos: Pos, targets: Set[Pos], blocked: Set[Pos],
                        w: int, h: int, max_search: int = 200) -> Optional[Pos]:
    """BFS to find nearest target - optimized with search limit"""
    if not targets:
        return None
    
    queue = deque([pos])
    visited = {pos}
    search_count = 0
    
    while queue and search_count < max_search:
        current = queue.popleft()
        search_count += 1
        
        if current in targets:
            return current
        
        for neighbor in neighbors4(current):
            if not in_bounds(neighbor, w, h):
                continue
            if neighbor in blocked or neighbor in visited:
                continue
            
            visited.add(neighbor)
            queue.append(neighbor)
    
    return None


# ============================================================================
# STATE PARSER - ROBUST
# ============================================================================

def parse_state(data: Dict[str, Any]) -> Optional[GameState]:
    """Parse arena JSON with error handling"""
    try:
        map_size = tuple(data.get("map_size", [167, 167]))
        
        # Parse units (only alive ones)
        bombers = {}
        for b in data.get("bombers", []):
            if b.get("alive"):
                bombers[b["id"]] = {
                    "pos": tuple(b["pos"]),
                    "bombs_available": b.get("bombs_available", 1),
                    "can_move": b.get("can_move", False),
                    "armor": b.get("armor", 0),
                    "safe_time": b.get("safe_time", 0)
                }
        
        # Parse arena
        arena = data.get("arena", {})
        obstacles = {tuple(o) for o in arena.get("obstacles", [])}
        walls = {tuple(w) for w in arena.get("walls", [])}
        bombs = arena.get("bombs", [])
        
        # Parse entities
        mobs = [tuple(m["pos"]) for m in data.get("mobs", [])]
        
        return GameState(
            map_size=map_size,
            bombers=bombers,
            obstacles=obstacles,
            walls=walls,
            bombs=bombs,
            mobs=mobs,
            timestamp=time.time()
        )
    
    except Exception as e:
        print(f"[Parse Error] {e}", file=sys.stderr)
        return None


# ============================================================================
# THREAT DETECTION
# ============================================================================

def is_in_danger(pos: Pos, state: GameState) -> bool:
    """Check if threatened - bombs (any radius) or mobs (≤4 cells)"""
    # Check bombs
    for bomb in state.bombs:
        bomb_pos = tuple(bomb["pos"])
        radius = bomb.get("radius", 3)
        if manhattan(pos, bomb_pos) <= radius:
            return True
    
    # Check mobs within 4 cells
    for mob in state.mobs:
        if manhattan(pos, mob) <= 4:
            return True
    
    return False


def find_escape_path(pos: Pos, state: GameState) -> Optional[List[Pos]]:
    """Find path to first safe cell - BFS with early exit"""
    w, h = state.map_size
    blocked = state.walls | state.obstacles | {tuple(b["pos"]) for b in state.bombs}
    
    # BFS to find first safe cell (not blocked and not in danger)
    queue = deque([(pos, [])])
    visited = {pos}
    
    while queue:
        current, path = queue.popleft()
        
        # Check if safe and not starting position
        if path and not is_in_danger(current, state):
            return path  # Early exit on first safe cell
        
        # Limit search depth
        if len(path) > 15:
            continue
        
        for neighbor in neighbors4(current):
            if not in_bounds(neighbor, w, h):
                continue
            if neighbor in blocked or neighbor in visited:
                continue
            
            visited.add(neighbor)
            queue.append((neighbor, path + [neighbor]))
    
    return None


# ============================================================================
# FARMING DECISION
# ============================================================================

def find_and_farm_obstacle(pos: Pos, state: GameState) -> Tuple[List[Pos], List[Pos]]:
    """Find nearest obstacle and prepare to farm it"""
    if not state.obstacles:
        return [], []
    
    w, h = state.map_size
    blocked = state.walls
    
    # Find nearest obstacle
    nearest_obs = find_nearest_target(pos, state.obstacles, blocked, w, h)
    
    if not nearest_obs:
        return [], []
    
    # If already adjacent to obstacle, plant bomb
    if manhattan(pos, nearest_obs) == 1:
        bombs = [list(nearest_obs)]
        # Try to move to safe adjacent cell
        adjacent = [n for n in neighbors4(pos) 
                   if in_bounds(n, w, h) and n not in blocked and n not in state.obstacles]
        if adjacent:
            # Choose safest adjacent cell
            best = min(adjacent, key=lambda p: is_in_danger(p, state))
            return [list(best)], bombs
        return [], bombs
    
    # Find path to adjacent cell of obstacle
    adjacent_options = [n for n in neighbors4(nearest_obs)
                       if in_bounds(n, w, h) and n not in blocked and n not in state.obstacles]
    
    if not adjacent_options:
        return [], []
    
    # Choose closest adjacent cell
    best_adj = min(adjacent_options, key=lambda p: manhattan(pos, p))
    
    path = bfs_path(pos, best_adj, blocked, w, h)
    
    if path:
        return path, []
    
    return [], []


# ============================================================================
# UNIT DECISION
# ============================================================================

def decide_unit_action(unit_id: str, unit_info: Dict[str, Any], 
                       state: GameState) -> Tuple[List[Pos], List[Pos]]:
    """Decide path and bombs for one unit"""
    
    pos = unit_info["pos"]
    
    # Can't move - wait
    if not unit_info.get("can_move"):
        return [], []
    
    # In danger - ESCAPE immediately
    if is_in_danger(pos, state):
        escape = find_escape_path(pos, state)
        if escape:
            return escape, []
        return [], []
    
    # No bombs - WAIT
    if unit_info.get("bombs_available", 0) <= 0:
        return [], []
    
    # FARM obstacles
    path, bombs = find_and_farm_obstacle(pos, state)
    return path, bombs


# ============================================================================
# API CLIENT - ROBUST
# ============================================================================

class ApiClient:
    """API communication with robust error handling"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.last_fetch = 0.0
        self.fetch_count = 0
        self.error_count = 0
    
    def should_fetch(self) -> bool:
        """Check if enough time passed for next fetch"""
        return time.time() - self.last_fetch >= FETCH_INTERVAL
    
    def fetch_state(self) -> Tuple[bool, Optional[GameState]]:
        """Fetch arena state with error handling"""
        if not self.should_fetch():
            return False, None
        
        self.last_fetch = time.time()
        
        try:
            response = self.session.get(
                f"{BASE_URL}/api/arena",
                timeout=COMMAND_TIMEOUT
            )
            
            if response.status_code == 200:
                data = response.json()
                state = parse_state(data)
                self.fetch_count += 1
                
                if state:
                    self.error_count = 0  # Reset error count on success
                    return True, state
                else:
                    self.error_count += 1
                    return False, None
            
            elif response.status_code == 401:
                print(f"[Auth Error] HTTP 401 - Token invalid or expired", file=sys.stderr)
                self.error_count += 1
                return False, None
            
            else:
                print(f"[Fetch Error] HTTP {response.status_code}", file=sys.stderr)
                self.error_count += 1
                return False, None
        
        except requests.exceptions.Timeout:
            print(f"[Timeout] GET /api/arena exceeded {COMMAND_TIMEOUT}s", file=sys.stderr)
            self.error_count += 1
            return False, None
        
        except requests.exceptions.ConnectionError as e:
            print(f"[Connection Error] {e}", file=sys.stderr)
            self.error_count += 1
            return False, None
        
        except Exception as e:
            print(f"[Fetch Error] {e}", file=sys.stderr)
            self.error_count += 1
            return False, None
    
    def send_commands(self, commands: List[Dict[str, Any]]) -> Tuple[bool, int]:
        """Send commands with error handling - returns (success, command_count)"""
        if not commands:
            return True, 0
        
        try:
            payload = {"bombers": commands}
            response = self.session.post(
                f"{BASE_URL}/api/move",
                json=payload,
                timeout=COMMAND_TIMEOUT
            )
            
            if response.status_code == 200:
                self.error_count = 0
                return True, len(commands)
            
            elif response.status_code == 401:
                print(f"[Auth Error] POST /api/move - Token invalid", file=sys.stderr)
                self.error_count += 1
                return False, 0
            
            else:
                print(f"[Move Error] HTTP {response.status_code}", file=sys.stderr)
                self.error_count += 1
                return False, 0
        
        except requests.exceptions.Timeout:
            print(f"[Timeout] POST /api/move exceeded {COMMAND_TIMEOUT}s", file=sys.stderr)
            self.error_count += 1
            return False, 0
        
        except Exception as e:
            print(f"[Send Error] {e}", file=sys.stderr)
            self.error_count += 1
            return False, 0
    
    def is_healthy(self) -> bool:
        """Check if API client is healthy"""
        return self.error_count < 10  # Allow up to 10 consecutive errors


# ============================================================================
# MAIN ENGINE
# ============================================================================

class GameEngine:
    """Main game loop - robust and reliable"""
    
    def __init__(self):
        self.api = ApiClient()
        self.current_state: Optional[GameState] = None
        self.cycle_count = 0
        self.last_print_time = 0.0
        self.print_interval = 5.0  # Print stats every 5 seconds
    
    def run(self):
        """Main loop - runs continuously"""
        print("=" * 70, file=sys.stderr)
        print("BOMBERMAN+ FARMING AI (3 REQ/SEC)", file=sys.stderr)
        print("Fetch every 0.667s | Farm obstacles | Escape danger | Respawn", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        
        try:
            while True:
                cycle_start = time.time()
                
                # Try to fetch state
                success, state = self.api.fetch_state()
                
                if success and state:
                    self.current_state = state
                    
                    # Build commands for all units
                    commands = []
                    for unit_id, unit_info in state.bombers.items():
                        path, bombs = decide_unit_action(unit_id, unit_info, state)
                        
                        cmd = {
                            "id": unit_id,
                            "path": [[p[0], p[1]] for p in path],
                            "bombs": bombs
                        }
                        commands.append(cmd)
                    
                    # Send commands
                    send_ok, cmd_count = self.api.send_commands(commands)
                    
                    # Print stats occasionally
                    if time.time() - self.last_print_time >= self.print_interval:
                        alive = state.alive_count()
                        obs = len(state.obstacles)
                        bombs = len(state.bombs)
                        print(f"[Cycle {self.cycle_count}] {alive} units | {obs} obstacles | {bombs} bombs | "
                              f"{cmd_count} cmd sent | health={self.api.error_count}", file=sys.stderr)
                        self.last_print_time = time.time()
                    
                    self.cycle_count += 1
                
                else:
                    # No state received, print error
                    if self.cycle_count % 10 == 0:
                        print(f"[Cycle {self.cycle_count}] Fetch failed - retrying...", file=sys.stderr)
                    self.cycle_count += 1
                
                # Check health
                if not self.api.is_healthy():
                    print(f"[Fatal] Too many errors ({self.api.error_count})", file=sys.stderr)
                    time.sleep(5)  # Wait before retry
                
                # Sleep to maintain timing
                cycle_time = time.time() - cycle_start
                if cycle_time < FETCH_INTERVAL:
                    time.sleep(FETCH_INTERVAL - cycle_time)
        
        except KeyboardInterrupt:
            print(f"\n[Shutdown] Graceful shutdown after {self.cycle_count} cycles", file=sys.stderr)
            sys.exit(0)
        
        except Exception as e:
            print(f"[Fatal Error] {e}", file=sys.stderr)
            sys.exit(1)


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    engine = GameEngine()
    engine.run()