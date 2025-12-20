# Bot architecture + GUI

## Install
pip install -U fastapi uvicorn requests

## Run
python main.py --gui-host 127.0.0.1 --gui-port 8000

Open: http://127.0.0.1:8000

## Strategies
- idle
- farm_obstacles (approach obstacle -> bomb -> run)
- evade_bomb_mobs (avoid awake mobs, try to bomb them "on place" when aligned)

Assignments persist in `assignments.json`.
