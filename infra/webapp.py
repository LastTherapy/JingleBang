from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.assignments import AssignmentStore
from app.registry import StrategyRegistry
from app.state_cache import StateCache
from infra.bot_runner import BotControl


def create_app(cache: StateCache, assignments: AssignmentStore, registry: StrategyRegistry, control: BotControl) -> FastAPI:
    app = FastAPI(title="DatsJingleBang Control")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        # минимальный GUI: шапка + canvas + таблица бомберов и селект стратегии
        return _INDEX_HTML

    @app.get("/api/control/strategies")
    def list_strategies() -> dict[str, Any]:
        return {"strategies": registry.list_ids()}

    @app.get("/api/control/assignments")
    def get_assignments() -> dict[str, Any]:
        return {"default": assignments.get_default(), "assignments": assignments.dump()}

    @app.post("/api/control/assignments")
    def set_assignment(payload: dict[str, Any]) -> dict[str, Any]:
        bomber_id = str(payload["bomber_id"])
        strategy_id = str(payload["strategy_id"])
        assignments.set_for(bomber_id, strategy_id)
        return {"ok": True}

    @app.post("/api/control/default")
    def set_default(payload: dict[str, Any]) -> dict[str, Any]:
        strategy_id = str(payload["strategy_id"])
        assignments.set_default(strategy_id)
        return {"ok": True}

    @app.get("/api/state")
    def get_state() -> dict[str, Any]:
        st = cache.get_state()
        booster = cache.get_booster()
        return {
            "state": asdict(st) if st else None,
            "booster": asdict(booster) if booster else None,
            "move_response": cache.get_move_response(),
            "error": cache.get_error(),
            "tick_ms": cache.get_tick_ms(),
        }

    @app.get("/api/control")
    def get_control() -> dict[str, Any]:
        return {"paused": control.paused, "loop_delay": control.loop_delay, "booster_refresh_s": control.booster_refresh_s}

    @app.post("/api/control")
    def set_control(payload: dict[str, Any]) -> dict[str, Any]:
        if "paused" in payload:
            control.paused = bool(payload["paused"])
        if "loop_delay" in payload:
            control.loop_delay = float(payload["loop_delay"])
        if "booster_refresh_s" in payload:
            control.booster_refresh_s = float(payload["booster_refresh_s"])
        return {"ok": True}

    return app


_INDEX_HTML = r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>DatsJingleBang Control</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 12px; }
    .row { display: flex; gap: 16px; align-items: flex-start; }
    .card { border: 1px solid #4443; border-radius: 10px; padding: 12px; }
    canvas { border: 1px solid #4443; border-radius: 10px; }
    table { border-collapse: collapse; }
    td, th { border-bottom: 1px solid #4443; padding: 6px 8px; text-align: left; }
    .muted { opacity: 0.7; }
    .danger { color: #b00020; }
    .ok { color: #0a7; }
    input[type="number"]{ width: 100px; }
  </style>
</head>
<body>
  <h2>Bot control</h2>

  <div class="row">
    <div class="card" style="min-width: 420px;">
      <div><b>Round:</b> <span id="round">-</span></div>
      <div><b>Score:</b> <span id="score">-</span></div>
      <div><b>Bombers:</b> <span id="alive">-</span>/<span id="total">-</span></div>
      <div><b>Tick:</b> <span id="tick">-</span> ms</div>
      <div><b>Booster:</b> range=<span id="br">-</span>, delay=<span id="bd">-</span>ms, points=<span id="bp">-</span></div>
      <div class="muted"><b>Last error:</b> <span id="err">-</span></div>

      <hr/>

      <div style="display:flex; gap:12px; align-items:center;">
        <label>Paused <input type="checkbox" id="paused"/></label>
        <label>Loop delay <input type="number" step="0.05" id="loopDelay"/></label>
        <label>Booster refresh <input type="number" step="0.1" id="boosterRefresh"/></label>
        <button id="apply">Apply</button>
      </div>

      <hr/>

      <div>
        <label>Default strategy:
          <select id="defaultStrategy"></select>
        </label>
        <button id="applyDefault">Set</button>
      </div>

      <h3>Bombers</h3>
      <table id="bombersTable">
        <thead><tr><th>id</th><th>alive</th><th>pos</th><th>can_move</th><th>strategy</th></tr></thead>
        <tbody></tbody>
      </table>
    </div>

    <div class="card">
      <canvas id="map" width="720" height="720"></canvas>
      <div class="muted">Walls=dark, Obstacles=gray, Bombs=red, Mobs=purple, My bombers=green</div>
    </div>
  </div>

<script>
const el = (id) => document.getElementById(id);

let STRATEGIES = [];
let ASSIGNMENTS = {};
let DEFAULT_STRATEGY = "farm_obstacles";

async function apiGet(url){ return (await fetch(url)).json(); }
async function apiPost(url, body){
  return (await fetch(url, {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(body)})).json();
}

function fillStrategies(select, strategies, current){
  select.innerHTML = "";
  for(const s of strategies){
    const opt = document.createElement("option");
    opt.value = s;
    opt.textContent = s;
    if(s === current) opt.selected = true;
    select.appendChild(opt);
  }
}

function drawMap(state){
  const canvas = el("map");
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0,0,canvas.width,canvas.height);

  if(!state) return;
  const w = state.map_size[0], h = state.map_size[1];
  const cell = Math.floor(Math.min(canvas.width / w, canvas.height / h));
  const ox = Math.floor((canvas.width - cell*w)/2);
  const oy = Math.floor((canvas.height - cell*h)/2);

  function rect(p, fill){
    const x = ox + p[0]*cell;
    const y = oy + p[1]*cell;
    ctx.fillStyle = fill;
    ctx.fillRect(x, y, cell, cell);
  }

  // walls
  for(const p of state.arena.walls) rect(p, "#222");
  // obstacles
  for(const p of state.arena.obstacles) rect(p, "#777");
  // bombs
  for(const b of state.arena.bombs) rect(b.pos, "#b00020");
  // mobs (awake)
  for(const m of state.mobs){
    const fill = (m.safe_time > 0) ? "#a77" : "#7a1fa2";
    rect(m.pos, fill);
  }
  // bombers
  for(const b of state.bombers){
    const fill = b.alive ? "#0a7" : "#77cc99";
    rect(b.pos, fill);
  }
}

function renderBombersTable(state){
  const tbody = el("bombersTable").querySelector("tbody");
  tbody.innerHTML = "";
  if(!state) return;

  for(const b of state.bombers){
    const tr = document.createElement("tr");
    const strat = ASSIGNMENTS[b.id] || DEFAULT_STRATEGY;

    tr.innerHTML = `
      <td class="muted">${b.id.slice(0,8)}...</td>
      <td>${b.alive}</td>
      <td>[${b.pos[0]},${b.pos[1]}]</td>
      <td>${b.can_move}</td>
      <td></td>
    `;
    const td = tr.querySelectorAll("td")[4];
    const sel = document.createElement("select");
    fillStrategies(sel, STRATEGIES, strat);
    sel.addEventListener("change", async () => {
      await apiPost("/api/control/assignments", {bomber_id: b.id, strategy_id: sel.value});
      await refreshAssignments();
    });
    td.appendChild(sel);
    tbody.appendChild(tr);
  }
}

async function refreshStrategies(){
  const data = await apiGet("/api/control/strategies");
  STRATEGIES = data.strategies || [];
  fillStrategies(el("defaultStrategy"), STRATEGIES, DEFAULT_STRATEGY);
}

async function refreshAssignments(){
  const data = await apiGet("/api/control/assignments");
  ASSIGNMENTS = data.assignments || {};
  DEFAULT_STRATEGY = data.default || DEFAULT_STRATEGY;
  fillStrategies(el("defaultStrategy"), STRATEGIES, DEFAULT_STRATEGY);
}

async function refreshControl(){
  const c = await apiGet("/api/control");
  el("paused").checked = !!c.paused;
  el("loopDelay").value = c.loop_delay;
  el("boosterRefresh").value = c.booster_refresh_s;
}

async function refreshState(){
  const data = await apiGet("/api/state");
  const state = data.state;

  if(state){
    el("round").textContent = state.round;
    el("score").textContent = state.raw_score;
    const alive = state.bombers.filter(b=>b.alive).length;
    el("alive").textContent = alive;
    el("total").textContent = state.bombers.length;
  }
  el("tick").textContent = (data.tick_ms ?? "-").toFixed ? data.tick_ms.toFixed(1) : data.tick_ms;

  const booster = data.booster;
  if(booster){
    el("br").textContent = booster.bomb_range;
    el("bd").textContent = booster.bomb_delay;
    el("bp").textContent = booster.points;
  }

  el("err").textContent = data.error || "-";
  drawMap(state);
  renderBombersTable(state);
}

el("apply").addEventListener("click", async () => {
  await apiPost("/api/control", {
    paused: el("paused").checked,
    loop_delay: parseFloat(el("loopDelay").value),
    booster_refresh_s: parseFloat(el("boosterRefresh").value),
  });
});

el("applyDefault").addEventListener("click", async () => {
  await apiPost("/api/control/default", {strategy_id: el("defaultStrategy").value});
  await refreshAssignments();
});

async function init(){
  await refreshStrategies();
  await refreshAssignments();
  await refreshControl();

  await refreshState();
  setInterval(refreshState, 1000);
}

init();
</script>
</body>
</html>
"""
