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
    app = FastAPI(title="Bot Control")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
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
        assignments.set_default(str(payload["strategy_id"]))
        return {"ok": True}

    @app.get("/api/control")
    def get_control() -> dict[str, Any]:
        return {"paused": control.paused, "tick_sec": control.tick_sec}

    @app.post("/api/control")
    def set_control(payload: dict[str, Any]) -> dict[str, Any]:
        if "paused" in payload:
            control.paused = bool(payload["paused"])
        if "tick_sec" in payload:
            control.tick_sec = float(payload["tick_sec"])
        return {"ok": True}

    @app.get("/api/state")
    def get_state() -> dict[str, Any]:
        st = cache.get_state()
        return {
            "state": asdict(st) if st else None,
            "move_response": cache.get_move_response(),
            "error": cache.get_error(),
            "tick_ms": cache.get_tick_ms(),
            "age_s": cache.get_state_age_s(),
        }

    return app


_INDEX_HTML = r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Bot Control</title>
  <style>
    :root{
      --bg:#0b0f14; --card:#101826; --text:#e7eef8; --muted:#93a4b8;
      --line:rgba(255,255,255,.10); --accent:#64d2ff; --good:#2ee59d; --bad:#ff6b6b;
    }
    body{ margin:0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial;
          background:var(--bg); color:var(--text); }
    .wrap{ max-width: 1100px; margin: 18px auto; padding: 0 14px; }
    .top{ display:flex; gap:14px; flex-wrap:wrap; align-items:stretch; }
    .card{ background:var(--card); border:1px solid var(--line); border-radius: 14px; padding: 14px; }
    .card h3{ margin:0 0 10px; font-size: 14px; letter-spacing:.3px; color: var(--muted); font-weight:600;}
    .stats{ display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 16px; }
    .kv{ display:flex; justify-content:space-between; gap: 12px; }
    .k{ color: var(--muted); }
    .v{ font-variant-numeric: tabular-nums; }
    .bad{ color: var(--bad); }
    .good{ color: var(--good); }
    button{ background: transparent; color: var(--text); border: 1px solid var(--line); padding: 8px 10px; border-radius: 10px; cursor:pointer; }
    button:hover{ border-color: rgba(255,255,255,.25); }
    input, select{ background: rgba(255,255,255,.04); color: var(--text); border:1px solid var(--line);
                  padding: 8px 10px; border-radius: 10px; }
    input[type="number"]{ width: 110px; }
    table{ width:100%; border-collapse: collapse; }
    th, td{ padding: 10px 8px; border-bottom:1px solid var(--line); text-align:left; vertical-align: middle; }
    th{ color: var(--muted); font-weight:600; font-size: 13px; }
    .pill{ display:inline-block; padding: 2px 8px; border-radius:999px; border: 1px solid var(--line); font-size: 12px; color: var(--muted); }
    .row-actions{ display:flex; gap: 10px; align-items:center; flex-wrap:wrap; }
    .mono{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    .small{ font-size: 12px; color: var(--muted); }
    .hint{ color: var(--muted); font-size: 12px; margin-top: 8px;}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="top">
      <div class="card" style="flex:1; min-width: 340px;">
        <h3>Текущая статистика</h3>
        <div class="stats">
          <div class="kv"><div class="k">Round</div><div class="v mono" id="round">-</div></div>
          <div class="kv"><div class="k">Score</div><div class="v mono" id="score">-</div></div>
          <div class="kv"><div class="k">Bombers</div><div class="v mono"><span id="alive">-</span>/<span id="total">-</span></div></div>
          <div class="kv"><div class="k">State age</div><div class="v mono" id="age">-</div></div>
          <div class="kv"><div class="k">Tick</div><div class="v mono" id="tick">-</div></div>
          <div class="kv"><div class="k">Last error</div><div class="v mono bad" id="err">-</div></div>
        </div>
        <div style="margin-top:12px;" class="row-actions">
          <label class="small">Paused <input type="checkbox" id="paused"/></label>
          <label class="small">Tick (sec) <input type="number" step="0.1" min="0.5" id="tickSec"/></label>
          <button id="apply">Apply</button>
          <span class="pill">Важно: максимум 1 GET/сек + 1 MOVE/сек</span>
        </div>
      </div>

      <div class="card" style="min-width: 340px;">
        <h3>Стратегии</h3>
        <div class="row-actions">
          <label class="small">Default strategy
            <select id="defaultStrategy"></select>
          </label>
          <button id="applyDefault">Set</button>
          <span class="small">Новые стратегии подхватываются авто-дискавери из папки <span class="mono">strategies/</span>.</span>
        </div>
        <div class="hint">
          Этот сервис отдаёт <span class="mono">/api/state</span>, чтобы твой отдельный сервис карты мог брать состояние отсюда без лишнего дёрганья игрового API.
        </div>
      </div>
    </div>

    <div class="card" style="margin-top:14px;">
      <h3>Бомберы и назначение стратегий</h3>
      <table id="bombersTable">
        <thead>
          <tr>
            <th>Bomber</th><th>Alive</th><th>Can move</th><th>Pos</th><th>Strategy</th>
          </tr>
        </thead>
        <tbody id="bombersBody"></tbody>
      </table>
      <div class="hint">
        Подсказка: если бомбер <span class="mono">can_move=false</span>, стратегия не применяется, чтобы не плодить команды.
      </div>
    </div>
  </div>

<script>
const el = (id) => document.getElementById(id);

async function apiGet(url){ return (await fetch(url)).json(); }
async function apiPost(url, body){
  return (await fetch(url, {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(body)})).json();
}

let STRATEGIES = [];
let ASSIGNMENTS = {};
let DEFAULT_STRATEGY = "farm_obstacles";

// Кэш DOM-строк: bomber_id -> {tr, cells..., select}
const ROWS = new Map();
// Локальная блокировка на время ручного выбора / POST
let UI_LOCKED = false;

// ========== helpers ==========
function setText(id, value){
  const node = el(id);
  if(!node) return;
  const s = (value === undefined || value === null) ? "-" : String(value);
  if(node.textContent !== s) node.textContent = s;
}

function fillSelectOptions(select, currentValue){
  // не пересоздаём если список не менялся
  const key = STRATEGIES.join("|");
  if(select.dataset.optsKey !== key){
    select.innerHTML = "";
    for(const s of STRATEGIES){
      const opt = document.createElement("option");
      opt.value = s;
      opt.textContent = s;
      select.appendChild(opt);
    }
    select.dataset.optsKey = key;
  }
  // выставляем value без пересоздания
  if(currentValue && select.value !== currentValue){
    select.value = currentValue;
  }
}

function upsertRow(b){
  const body = el("bombersBody");
  let row = ROWS.get(b.id);

  if(!row){
    const tr = document.createElement("tr");

    const tdId = document.createElement("td");
    tdId.className = "mono";
    tdId.textContent = b.id.slice(0,8) + "…";

    const tdAlive = document.createElement("td");
    const tdCan = document.createElement("td");
    const tdPos = document.createElement("td");
    tdPos.className = "mono";

    const tdStrat = document.createElement("td");
    const sel = document.createElement("select");

    sel.addEventListener("focus", () => { UI_LOCKED = true; });
    sel.addEventListener("blur",  () => { UI_LOCKED = false; });

    sel.addEventListener("change", async () => {
      UI_LOCKED = true;
      const chosen = sel.value;

      // мгновенно применяем локально, чтобы не мигало
      ASSIGNMENTS[b.id] = chosen;

      try{
        await apiPost("/api/control/assignments", {bomber_id: b.id, strategy_id: chosen});
        // подгружаем assignments, чтобы быть уверенными что сервер сохранил
        await refreshAssignments(false);
      } finally {
        UI_LOCKED = false;
      }
    });

    tdStrat.appendChild(sel);

    tr.appendChild(tdId);
    tr.appendChild(tdAlive);
    tr.appendChild(tdCan);
    tr.appendChild(tdPos);
    tr.appendChild(tdStrat);

    body.appendChild(tr);

    row = {tr, tdAlive, tdCan, tdPos, sel};
    ROWS.set(b.id, row);
  }

  // обновляем содержимое ячеек (без пересоздания)
  row.tdAlive.innerHTML = b.alive ? "<span class='good'>true</span>" : "<span class='bad'>false</span>";
  row.tdCan.innerHTML   = b.can_move ? "<span class='good'>true</span>" : "<span class='pill'>false</span>";
  row.tdPos.textContent = "[" + b.pos[0] + "," + b.pos[1] + "]";

  const strat = ASSIGNMENTS[b.id] || DEFAULT_STRATEGY;
  fillSelectOptions(row.sel, strat);
}

function removeMissingRows(currentIds){
  for(const [id, row] of ROWS.entries()){
    if(!currentIds.has(id)){
      row.tr.remove();
      ROWS.delete(id);
    }
  }
}

// ========== data refresh ==========
async function refreshStrategies(){
  const data = await apiGet("/api/control/strategies");
  STRATEGIES = data.strategies || [];
  if(!STRATEGIES.includes(DEFAULT_STRATEGY) && STRATEGIES.length) DEFAULT_STRATEGY = STRATEGIES[0];
  const ds = el("defaultStrategy");
  fillSelectOptions(ds, DEFAULT_STRATEGY);
}

async function refreshAssignments(updateDefaultSelect=true){
  const data = await apiGet("/api/control/assignments");
  ASSIGNMENTS = data.assignments || {};
  DEFAULT_STRATEGY = data.default || DEFAULT_STRATEGY;

  if(updateDefaultSelect){
    fillSelectOptions(el("defaultStrategy"), DEFAULT_STRATEGY);
  } else {
    // если список стратегий тот же — просто выставим value
    if(el("defaultStrategy").value !== DEFAULT_STRATEGY){
      el("defaultStrategy").value = DEFAULT_STRATEGY;
    }
  }
}

async function refreshControl(){
  const c = await apiGet("/api/control");
  el("paused").checked = !!c.paused;
  el("tickSec").value = c.tick_sec;
}

async function refreshState(){
  if(UI_LOCKED) return;

  const data = await apiGet("/api/state");
  const state = data.state;

  if(state){
    setText("round", state.round);
    setText("score", state.raw_score);
    setText("alive", state.bombers.filter(b=>b.alive).length);
    setText("total", state.bombers.length);
  } else {
    setText("round", "-");
    setText("score", "-");
    setText("alive", "-");
    setText("total", "-");
  }

  setText("age", ((data.age_s ?? 0).toFixed(1)) + "s");
  setText("tick", ((data.tick_ms ?? 0).toFixed(1)) + "ms");
  setText("err", data.error || "-");

  if(!state) return;

  // патчим таблицу
  const ids = new Set();
  for(const b of state.bombers){
    ids.add(b.id);
    upsertRow(b);
  }
  removeMissingRows(ids);
}

// ========== actions ==========
el("apply").addEventListener("click", async () => {
  UI_LOCKED = true;
  try{
    await apiPost("/api/control", {
      paused: el("paused").checked,
      tick_sec: parseFloat(el("tickSec").value),
    });
  } finally {
    UI_LOCKED = false;
  }
});

el("applyDefault").addEventListener("click", async () => {
  UI_LOCKED = true;
  try{
    const sid = el("defaultStrategy").value;
    await apiPost("/api/control/default", {strategy_id: sid});
    await refreshAssignments(false);
  } finally {
    UI_LOCKED = false;
  }
});

async function init(){
  await refreshStrategies();
  await refreshAssignments(true);
  await refreshControl();

  await refreshState();
  setInterval(refreshState, 1000);
}
init();
</script>
</body>
</html>
"""
