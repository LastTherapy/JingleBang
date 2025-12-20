# Bomberman+ Advanced AI - Strategic Guide

## 📊 Point Optimization System

### Reward Structure
```
Obstacle Destruction:
  - 1st obstacle in chain: 1 point
  - 2nd obstacle in chain: 2 points
  - 3rd obstacle in chain: 3 points
  - 4th obstacle in chain: 4 points
  - Max for single explosion: 10 points

Enemy Kill: 5 points each
Mob Kill: 50 points each
```

**Strategy**: Cluster obstacle destruction to maximize points (4+ obstacles = 10 points)

---

## 🎯 Intelligent Decision Priority

```
PRIORITY 1: ESCAPE DANGER
  IF in bomb radius (≤3 cells) OR enemy/mob adjacent (≤1 cell):
    → RETREAT: BFS to safe cell within 15 steps

PRIORITY 2: RECOVER BOMBS
  IF bombs_available == 0:
    → WAIT: Stay in place (or group for safety)

PRIORITY 3: HIGH-VALUE TARGETS
  IF mobs visible (<25 cells):
    → HUNT: Chase mob (50 points!)
  
  ELSE IF enemies visible (<25 cells):
    → HUNT: Chase enemy (5 points)

PRIORITY 4: CHAIN EXPLOSIONS
  IF bomb about to explode (timer ≤ 1 sec) near obstacles:
    → CHAIN: Position to trigger chain reaction

PRIORITY 5: OBSTACLE CLUSTERING
  IF obstacles form clusters (3+ within 4 cells):
    → FARM: Approach cluster for multi-bomb destruction
  
  ELSE IF obstacles available:
    → FARM: Approach nearest obstacle

PRIORITY 6: VISION SPREADING
  IF multiple units in close proximity (<5 cells):
    → SPREAD: Move away to increase vision union
    → (Vision = union of circles around each unit)

PRIORITY 7: SAFE GROUPING
  IF low on bombs OR enemies nearby:
    → GROUP: Move toward other units

PRIORITY 8: EXPLORATION
  → SCOUT: Random walk to discover obstacles/enemies
```

---

## ⏱️ Bomb Timer Strategy (Fuse Awareness)

### Parsing Bomb Timer
```json
{
  "bombs": [
    {
      "pos": [50, 50],
      "timer": 3,      // Seconds until explosion
      "radius": 3      // Blast radius
    }
  ]
}
```

### Chain Explosion Detection
```python
if bomb.timer <= 1:  # About to explode
    nearby_obstacles = count(obstacles within radius)
    if nearby_obstacles >= 2:
        # Perfect for chain reaction!
        # Position adjacent unit to place bomb
```

### Multi-Bomb Coordination
- Unit 1 places bomb (timer = 3s)
- Unit 2 positions adjacent to Unit 1's bomb
- When Unit 1's bomb explodes, Unit 2 can trigger chain
- Maximize points with coordinated timing

---

## 👥 Unit Grouping vs Spreading

### When to Group
- No bombs available (wait for recovery together)
- Enemies/mobs nearby (safety in numbers)
- About to respawn (last 3 units die → all 6 respawn)

### When to Spread
- Multiple units within 5 cells → separate for vision coverage
- Goal: Maximize vision union
  ```
  Vision Union = Circle around unit1 ∪ Circle around unit2 ∪ ...
  Better spread = more area visible
  ```

### Vision Strategy
- Spread units across map to see more
- Find all obstacles and enemies faster
- Enables faster target acquisition

---

## 💣 Suicide Protocol (Respawn Strategy)

### When to Suicide
**Trigger condition**: Only 3 or fewer units alive

**Benefit**: All 6 units respawn (tactical reset)

### Implementation
```python
def should_suicide(units, alive_count):
    if alive_count <= 3:
        # Send remaining units toward mobs/bombs
        # Intentional exposure to damage
        # All units respawn after death
        return True
    return False
```

### Respawn Mechanics
- Entire team (6 units) spawns at starting position
- Full bomb recovery for all units
- Good when:
  - Trapped in corner
  - All units have low armor
  - Strategic reset needed

---

## 🎁 Booster Priority Strategy

### Activation Order (Every 90 seconds)

```
PRIORITY 1: Bomb Range/Delay
  - bomb_range: Increase explosion radius (better for cluster farming)
  - bomb_delay: Slow fuse for chain coordination
  
PRIORITY 2: Vision
  - view: Increase sight range (find obstacles faster)
  
PRIORITY 3: Speed
  - speed: Move faster (nice to have)
  
PRIORITY 4: Armor
  - armor: Reduce damage (useful but lower priority)
```

### Implementation
```python
booster_priority = ["bomb_range", "bomb_delay", "view", "speed", "armor"]

# Get available boosters
available = api.get_boosters()["available"]

# Activate first in priority list
for booster_type in booster_priority:
    if any(b["type"] == booster_type for b in available):
        api.activate_booster(booster_type)
        break
```

---

## ⏱️ API Rate Limiting (CRITICAL)

### Constraint: 3 Requests per Minute

```
Rate Limit: 3 req/min = 1 request every 20 seconds

Game Loop Timing:
  T=0s:   GET /api/arena     ✓ (fetch state)
  T=0.1s: Decide actions (local computation)
  T=0.5s: POST /api/move     ✓ (send commands)
  
  T=20s:  GET /api/arena     ✓ (fetch new state)
  T=20.1s: Decide actions
  T=20.5s: POST /api/move    ✓
  
  T=90s:  GET /api/booster   ✓ (check upgrades)
  T=90.5s: POST /api/booster ✓ (activate)
```

### Key Rules
- **Minimum 20 seconds** between arena fetches
- **Booster check every 90 seconds** (separate rate limit tier)
- **Move commands after each fetch** (don't waste state)
- **Cache state locally** between fetches

### Implementation
```python
class ApiClient:
    def __init__(self):
        self.last_fetch_time = 0.0
    
    def get_arena(self):
        current = time.time()
        
        # Enforce 20s minimum
        if current - self.last_fetch_time < 20.0:
            return False, {}  # Skip this request
        
        self.last_fetch_time = current
        
        # Make actual API call
        response = requests.get(f"{BASE_URL}/api/arena", ...)
        return True, response.json()
```

---

## 🔢 State Caching Between Fetches

### During 20-Second Intervals

```
T=0s:  Fetch state → current_state = data
       Analyze & decide → send commands
       All units act on T=0 state

T=5s:  Refresh state? NO (rate limit)
       Use cached current_state
       Local path updates only

T=10s: Refresh state? NO
       Use cached current_state

T=20s: Fetch new state → current_state = fresh_data
       Analyze & decide → send commands
```

### Implications
- Units may not have latest info between fetches
- Predict opponent/bomb movements
- Account for execution time in paths

---

## 📍 Precise Positioning

### Obstacle Approach
```python
# Don't plant on obstacle directly
# Plant ADJACENT to obstacle

# ❌ WRONG
bombs = [obstacle_pos]

# ✅ CORRECT
adjacent_pos = adjacent_to(obstacle_pos)
bombs = [adjacent_pos]
```

### Safe Cell Validation
```python
def is_safe_for_planting(pos, bombs):
    for bomb in bombs:
        if manhattan(pos, bomb.pos) <= bomb.radius:
            return False  # Not safe
    return True
```

### Escape Path Verification
```python
# Before planting bomb, verify escape route
escape_path = bfs(unit_pos, safe_cell, obstacles)
if escape_path and len(escape_path) > 0:
    plant_bomb = True  # Safe to plant
else:
    plant_bomb = False  # Might be trapped
```

---

## 🎯 Vision Union Strategy

### Calculate Current Vision Coverage

```python
def calculate_vision_union(units, view_range):
    """Union of all unit vision circles"""
    visible = set()
    
    for unit in units:
        for cell in map_cells:
            if manhattan(unit.pos, cell) <= view_range:
                visible.add(cell)
    
    return visible
```

### Optimize Spreading

```python
def should_spread(units):
    """Return True if units are clustered"""
    for u1 in units:
        for u2 in units:
            if u1.id != u2.id:
                if manhattan(u1.pos, u2.pos) <= 5:
                    return True  # Too close, spread
    return False
```

---

## 📈 Cluster Detection for Farming

### Find Obstacle Clusters

```python
def find_clusters(obstacles, cluster_radius=4):
    """Group nearby obstacles"""
    clusters = []
    visited = set()
    
    for obs in obstacles:
        if obs in visited:
            continue
        
        # BFS to find cluster
        cluster = []
        queue = deque([obs])
        
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            
            visited.add(current)
            cluster.append(current)
            
            for neighbor in obstacles:
                if manhattan(current, neighbor) <= cluster_radius:
                    if neighbor not in visited:
                        queue.append(neighbor)
        
        clusters.append(cluster)
    
    return clusters
```

### Score Clusters

```python
# Farm largest clusters first
clusters.sort(key=lambda c: len(c), reverse=True)

# Approaching cluster[0] = maximum points
```

---

## 📋 Complete Decision Tree

```
State arrives every 20 seconds

For each unit:
  1. Can move? NO → skip
  
  2. In danger? YES → ESCAPE
     NO → continue
  
  3. Have bombs? NO → WAIT (or GROUP)
     YES → continue
  
  4. Mobs visible? YES → HUNT mob
     NO → continue
  
  5. Enemies visible? YES → HUNT enemy
     NO → continue
  
  6. Bomb about to explode near obstacles? YES → CHAIN
     NO → continue
  
  7. Obstacle clusters exist? YES → FARM cluster
     NO → continue
  
  8. Units too close (<5 cells)? YES → SPREAD
     NO → continue
  
  9. Low bombs or enemies near? YES → GROUP
     NO → continue
  
  10. Default → SCOUT
```

---

## 🔧 Configuration

In `game_engine.py`:

```python
# RATE LIMITING (CRITICAL)
POLL_INTERVAL = 20.0          # Fetch every 20 seconds (3 req/min)
BOOSTER_INTERVAL = 90         # Check boosters every 90 seconds

# STRATEGY PARAMETERS
CLUSTER_RADIUS = 4            # Cells for obstacle clustering
VISION_RANGE = 20             # Unit vision range
HUNT_RANGE = 25               # Range to hunt mobs/enemies
ESCAPE_RADIUS = 15            # Max BFS distance for escape
GROUPING_DISTANCE = 5         # Units closer than this should spread

# REWARDS
OBSTACLE_POINTS = [1,2,3,4,10]  # Chain destruction rewards
ENEMY_POINTS = 5
MOB_POINTS = 50
```

---

## ✅ Expected Console Output

```
======================================================================
BOMBERMAN+ ADVANCED AI (OPTIMIZED STRATEGY)
Rate limit: 3 requests/minute (20s fetch interval)
======================================================================

[Game] Starting...

[State] 6 units, 45 obstacles, 2 bombs

[Decide] Analyzing 6 units...
  [unit-1] farm     path=12 bombs=1
  [unit-2] spread   path=8 bombs=0
  [unit-3] hunt     path=15 bombs=1
  [unit-4] escape   path=3 bombs=0
  [unit-5] group    path=2 bombs=0
  [unit-6] scout    path=5 bombs=0

[Move] Sending 6 commands...
[Move] ✓ Accepted

... (15 seconds of caching) ...

[State] 6 units, 42 obstacles, 1 bombs
[Decide] Analyzing 6 units...
  [unit-1] farm     path=10 bombs=1
  [unit-2] spread   path=7 bombs=0
  ...
[Move] ✓ Accepted
```

---

## 🎮 How to Run

```bash
python3 game_engine.py
python3 web_visualizer.py
# Open http://localhost:5000
```

---

**Status**: Advanced Strategy Implemented  
**Date**: December 20, 2025
