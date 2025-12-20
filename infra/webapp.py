from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.assignments import AssignmentStore
from app.registry import StrategyRegistry
from app.state_cache import StateCache
from infra.bot_runner import BotControl


def create_app(cache: StateCache, assignments: AssignmentStore, registry: StrategyRegistry, control: BotControl) -> FastAPI:
    app = FastAPI(title="DatsJingleBang Bot GUI")

    # чтобы можно было открыть API/GUI с другого компа
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _INDEX_HTML

    @app.get("/api/control/strategies")
    def list_strategies() -> list[dict[str, str]]:
        return registry.list()

    @app.get("/api/control/assignments")
    def get_assignments() -> dict:
        return assignments.dump()

    @app.post("/api/control/assignments")
    def set_assignment(payload: dict) -> dict:
        # payload: {"bomber_id":"...", "strategy_id":"..."} OR {"default":"..."}
        if "default" in payload:
            sid = str(payload["default"])
            if sid not in registry.list_ids():
                raise HTTPException(status_code=400, detail=f"unknown strategy_id={sid}")
            assignments.set_default(sid)
            return assignments.dump()

        bomber_id = payload.get("bomber_id")
        strategy_id = payload.get("strategy_id")
        if not bomber_id or not strategy_id:
            raise HTTPException(status_code=400, detail="expected bomber_id and strategy_id")
        bomber_id = str(bomber_id)
        strategy_id = str(strategy_id)

        if strategy_id not in registry.list_ids():
            raise HTTPException(status_code=400, detail=f"unknown strategy_id={strategy_id}")

        assignments.set_for(bomber_id, strategy_id)
        return assignments.dump()

    @app.get("/api/control/status")
    def get_status() -> dict:
        return {
            "paused": control.paused,
            "loop_delay": control.loop_delay,
            "assignments": assignments.dump(),
        }

    @app.post("/api/control/status")
    def set_status(payload: dict) -> dict:
        if "paused" in payload:
            control.paused = bool(payload["paused"])
        if "loop_delay" in payload:
            control.loop_delay = float(payload["loop_delay"])
        return get_status()

    @app.get("/api/state")
    def get_state() -> dict:
        st = cache.get_state()
        meta = cache.get_state_meta()
        last_move = cache.get_move_response()

        if st is None:
            return {"meta": meta, "state": None, "last_move": last_move}

        alive = sum(1 for b in st.bombers if b.alive)
        return {
            "meta": meta,
            "summary": {
                "player": st.player,
                "round": st.round,
                "raw_score": st.raw_score,
                "alive": alive,
                "total": len(st.bombers),
                "errors": st.errors,
                "code": st.code,
                "map_size": list(st.map_size),
                "obstacles": len(st.arena.obstacles),
                "walls": len(st.arena.walls),
                "bombs": len(st.arena.bombs),
            },
            "state": st.to_dict(),
            "last_move": last_move,
            "control": {"paused": control.paused, "loop_delay": control.loop_delay},
            "assignments": assignments.dump(),
        }

    return app


_INDEX_HTML = r"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Bot GUI</title>
  <style>
    body { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial; margin: 0; padding: 0; background: #0b0f14; color: #e6edf3; }
    header { padding: 12px 16px; background: #111827; border-bottom: 1px solid #1f2937; display: flex; gap: 16px; flex-wrap: wrap; align-items: center; }
    .pill { padding: 6px 10px; border: 1px solid #334155; border-radius: 999px; background: #0b1220; }
    .row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
    .muted { color: #9ca3af; }
    main { display: grid; grid-template-columns: 1fr 420px; gap: 12px; padding: 12px; }
    @media (max-width: 1100px) { main { grid-template-columns: 1fr; } }
    .card { background: #0b1220; border: 1px solid #1f2937; border-radius: 12px; overflow: hidden; }
    .card h2 { margin: 0; padding: 10px 12px; font-size: 14px; border-bottom: 1px solid #1f2937; background: #0f172a; }
    .card .content { padding: 12px; }
    table { width: 100%; border-collapse: collapse; font-size: 12px; }
    th, td { border-bottom: 1px solid #1f2937; padding: 8px 6px; vertical-align: top; }
    th { text-align: left; color: #cbd5e1; font-weight: 600; }
    select, input[type="number"] { background: #0b0f14; color: #e6edf3; border: 1px solid #334155; border-radius: 8px; padding: 6px 8px; }
    button { background: #1f2937; color: #e6edf3; border: 1px solid #334155; border-radius: 10px; padding: 8px 10px; cursor: pointer; }
    button:hover { background: #273449; }
    canvas { width: 100%; height: 100%; background: #06090d; display: block; }
    .canvas-wrap { height: calc(100vh - 120px); min-height: 520px; }
    .small { font-size: 12px; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .label { display: inline-block; min-width: 120px; color: #9ca3af; }
    .ok { color: #22c55e; }
    .warn { color: #f59e0b; }
    .bad { color: #ef4444; }
  </style>
</head>
<body>
  <header>
    <div class="row">
      <div class="pill"><span class="muted">Round:</span> <b id="round">—</b></div>
      <div class="pill"><span class="muted">Score:</span> <b id="score">—</b></div>
      <div class="pill"><span class="muted">Bombers:</span> <b id="bombers">—</b></div>
      <div class="pill"><span class="muted">Req:</span> <b id="tick">—</b></div>
      <div class="pill"><span class="muted">Bot:</span> <b id="botStatus">—</b></div>
    </div>

    <div class="row">
      <button id="pauseBtn">Pause</button>
      <span class="small"><span class="label">Loop delay</span><input id="loopDelay" type="number" step="0.05" min="0.05" value="0.35"/></span>
      <button id="applyDelayBtn">Apply</button>
      <span class="small"><label><input id="follow" type="checkbox" checked /> follow</label></span>
      <span class="small"><label><input id="showDanger" type="checkbox" checked /> danger</label></span>
    </div>
  </header>

  <main>
    <div class="card">
      <h2>Map</h2>
      <div class="content canvas-wrap">
        <canvas id="map"></canvas>
      </div>
    </div>

    <div class="card">
      <h2>Control</h2>
      <div class="content">
        <div class="grid">
          <div>
            <div class="small"><span class="label">Default strategy</span></div>
            <select id="defaultStrategy"></select>
          </div>
          <div>
            <div class="small"><span class="label">Last error</span></div>
            <div id="lastError" class="small muted">—</div>
          </div>
        </div>

        <div style="height: 10px"></div>

        <div class="small muted">Per bomber strategies:</div>
        <div style="height: 8px"></div>
        <div id="tableWrap"></div>

        <div style="height: 10px"></div>
        <details>
          <summary class="small muted">Last move response</summary>
          <pre id="moveResp" class="small" style="white-space: pre-wrap; word-break: break-word;"></pre>
        </details>
      </div>
    </div>
  </main>

  <script>
    const $ = (id) => document.getElementById(id);

    let STRATS = [];
    let assignments = { default: "idle", per_bomber: {} };

    async function apiGet(path) {
      const r = await fetch(path);
      if (!r.ok) throw new Error(`${path}: ${r.status}`);
      return r.json();
    }

    async function apiPost(path, payload) {
      const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      if (!r.ok) throw new Error(`${path}: ${r.status}`);
      return r.json();
    }

    async function loadStrategies() {
      STRATS = await apiGet("/api/control/strategies");
      const sel = $("defaultStrategy");
      sel.innerHTML = "";
      for (const s of STRATS) {
        const opt = document.createElement("option");
        opt.value = s.id;
        opt.textContent = s.description ? `${s.id} — ${s.description}` : s.id;
        sel.appendChild(opt);
      }
    }

    function setHeader(summary, meta, control) {
      $("round").textContent = summary?.round ?? "—";
      $("score").textContent = summary?.raw_score ?? "—";
      $("bombers").textContent = summary ? `${summary.alive}/${summary.total}` : "—";

      const tickMs = meta?.last_tick_ms ?? 0;
      $("tick").textContent = tickMs ? `${tickMs.toFixed(0)} ms` : "—";

      const paused = control?.paused ? "paused" : "running";
      $("botStatus").textContent = paused;
      $("botStatus").className = control?.paused ? "warn" : "ok";
      $("lastError").textContent = (meta?.last_error && meta.last_error.trim()) ? meta.last_error : "—";
      $("lastError").className = (meta?.last_error && meta.last_error.trim()) ? "small bad" : "small muted";
    }

    function makeStrategySelect(current, onChange) {
      const sel = document.createElement("select");
      for (const s of STRATS) {
        const opt = document.createElement("option");
        opt.value = s.id;
        opt.textContent = s.id;
        if (s.id === current) opt.selected = true;
        sel.appendChild(opt);
      }
      sel.addEventListener("change", () => onChange(sel.value));
      return sel;
    }

    function renderTable(state) {
      const wrap = $("tableWrap");
      if (!state) { wrap.innerHTML = '<div class="small muted">no state yet</div>'; return; }

      const bombers = state.bombers ?? [];
      const tbl = document.createElement("table");
      tbl.innerHTML = `
        <thead>
          <tr>
            <th>id</th>
            <th>alive</th>
            <th>can_move</th>
            <th>pos</th>
            <th>bombs</th>
            <th>strategy</th>
          </tr>
        </thead>
      `;
      const tbody = document.createElement("tbody");

      for (const b of bombers) {
        const tr = document.createElement("tr");
        const strategyId = assignments.per_bomber?.[b.id] ?? assignments.default;

        const tdId = document.createElement("td");
        tdId.textContent = b.id.slice(0, 8) + "…";
        tdId.title = b.id;

        const tdAlive = document.createElement("td");
        tdAlive.textContent = b.alive ? "yes" : "no";
        tdAlive.className = b.alive ? "ok" : "muted";

        const tdCan = document.createElement("td");
        tdCan.textContent = b.can_move ? "yes" : "no";
        tdCan.className = b.can_move ? "ok" : "muted";

        const tdPos = document.createElement("td");
        tdPos.textContent = `[${b.pos[0]}, ${b.pos[1]}]`;

        const tdBombs = document.createElement("td");
        tdBombs.textContent = String(b.bombs_available);

        const tdStrat = document.createElement("td");
        tdStrat.appendChild(makeStrategySelect(strategyId, async (newId) => {
          await apiPost("/api/control/assignments", { bomber_id: b.id, strategy_id: newId });
          assignments.per_bomber[b.id] = newId;
        }));

        tr.appendChild(tdId);
        tr.appendChild(tdAlive);
        tr.appendChild(tdCan);
        tr.appendChild(tdPos);
        tr.appendChild(tdBombs);
        tr.appendChild(tdStrat);
        tbody.appendChild(tr);
      }

      tbl.appendChild(tbody);
      wrap.innerHTML = "";
      wrap.appendChild(tbl);
    }

    // ===== Map render =====
    const canvas = $("map");
    const ctx = canvas.getContext("2d");

    const view = {
      scale: 6,      // px per cell
      ox: 10, oy: 10,
      dragging: false,
      lastX: 0, lastY: 0
    };

    function resizeCanvas() {
      const rect = canvas.getBoundingClientRect();
      canvas.width = Math.floor(rect.width * devicePixelRatio);
      canvas.height = Math.floor(rect.height * devicePixelRatio);
      ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
    }
    window.addEventListener("resize", resizeCanvas);

    canvas.addEventListener("mousedown", (e) => {
      view.dragging = true;
      view.lastX = e.clientX;
      view.lastY = e.clientY;
    });
    window.addEventListener("mouseup", () => view.dragging = false);
    window.addEventListener("mousemove", (e) => {
      if (!view.dragging) return;
      const dx = e.clientX - view.lastX;
      const dy = e.clientY - view.lastY;
      view.ox += dx;
      view.oy += dy;
      view.lastX = e.clientX;
      view.lastY = e.clientY;
    });

    canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      const factor = (e.deltaY < 0) ? 1.12 : 1/1.12;
      const newScale = Math.min(32, Math.max(2, view.scale * factor));
      view.scale = newScale;
    }, { passive: false });

    function worldToScreen(x, y) {
      return [view.ox + x * view.scale, view.oy + y * view.scale];
    }

    function drawCell(x, y) {
      const [sx, sy] = worldToScreen(x, y);
      ctx.fillRect(sx, sy, view.scale, view.scale);
    }

    function recenterOnBombers(state) {
      const bombers = (state?.bombers ?? []).filter(b => b.alive);
      if (!bombers.length) return;
      const xs = bombers.map(b => b.pos[0]);
      const ys = bombers.map(b => b.pos[1]);
      const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
      const cy = (Math.min(...ys) + Math.max(...ys)) / 2;

      const rect = canvas.getBoundingClientRect();
      const w = rect.width, h = rect.height;
      view.ox = w/2 - cx * view.scale;
      view.oy = h/2 - cy * view.scale;
    }

    function renderMap(state, dangerSet) {
      if (!state) return;
      const arena = state.arena;
      const mapSize = state.map_size;

      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // background grid is omitted for perf

      // walls
      ctx.globalAlpha = 1.0;
      ctx.fillStyle = "#334155";
      for (const [x,y] of arena.walls) drawCell(x,y);

      // obstacles (destructible)
      ctx.fillStyle = "#6b7280";
      for (const [x,y] of arena.obstacles) drawCell(x,y);

      // danger overlay
      if ($("showDanger").checked && dangerSet) {
        ctx.globalAlpha = 0.22;
        ctx.fillStyle = "#ef4444";
        for (const key of dangerSet) {
          const parts = key.split(",");
          drawCell(parseInt(parts[0]), parseInt(parts[1]));
        }
        ctx.globalAlpha = 1.0;
      }

      // bombs
      ctx.fillStyle = "#f59e0b";
      for (const b of arena.bombs) drawCell(b.pos[0], b.pos[1]);

      // enemies
      ctx.fillStyle = "#ef4444";
      for (const e of (state.enemies ?? [])) drawCell(e.pos[0], e.pos[1]);

      // mobs
      ctx.fillStyle = "#a855f7";
      for (const m of (state.mobs ?? [])) drawCell(m.pos[0], m.pos[1]);

      // bombers
      for (const b of (state.bombers ?? [])) {
        ctx.fillStyle = b.alive ? "#22c55e" : "#86efac";
        drawCell(b.pos[0], b.pos[1]);
      }
    }

    function makeDangerSet(state, timerThreshold=2.5) {
      // простая оценка опасности прямо в JS: клетки креста бомб с timer <= threshold
      // (для визуализации, логика бота в python)
      if (!state) return null;
      const walls = new Set(state.arena.walls.map(p => `${p[0]},${p[1]}`));
      const obstacles = new Set(state.arena.obstacles.map(p => `${p[0]},${p[1]}`));
      const bombStops = new Set(state.arena.bombs.map(b => `${b.pos[0]},${b.pos[1]}`));
      const w = state.map_size[0], h = state.map_size[1];

      const inside = (x,y) => x>=0 && y>=0 && x<w && y<h;

      const out = new Set();
      for (const b of state.arena.bombs) {
        if (b.timer > timerThreshold) continue;
        const x0=b.pos[0], y0=b.pos[1];
        out.add(`${x0},${y0}`);
        const dirs = [[1,0],[-1,0],[0,1],[0,-1]];
        for (const [dx,dy] of dirs) {
          for (let i=1;i<=b.range;i++) {
            const x=x0+dx*i, y=y0+dy*i;
            if (!inside(x,y)) break;
            const key = `${x},${y}`;
            out.add(key);
            if (walls.has(key) || obstacles.has(key) || bombStops.has(key)) break;
          }
        }
      }
      return out;
    }

    // ===== polling =====
    async function tick() {
      try {
        const st = await apiGet("/api/state");
        const meta = st.meta;
        const summary = st.summary;
        const control = st.control;
        assignments = st.assignments ?? assignments;

        // header
        setHeader(summary, meta, control);

        // default strategy select
        const defSel = $("defaultStrategy");
        defSel.value = assignments.default ?? "idle";

        // table
        renderTable(st.state);

        // move response
        $("moveResp").textContent = st.last_move ? JSON.stringify(st.last_move, null, 2) : "";

        // map
        if ($("follow").checked) {
          recenterOnBombers(st.state);
        }
        const dangerSet = makeDangerSet(st.state, 2.5);
        renderMap(st.state, dangerSet);
      } catch (e) {
        console.error(e);
      } finally {
        setTimeout(tick, 1000);
      }
    }

    // ===== controls =====
    $("pauseBtn").addEventListener("click", async () => {
      const status = await apiGet("/api/control/status");
      const paused = !status.paused;
      await apiPost("/api/control/status", { paused });
    });

    $("applyDelayBtn").addEventListener("click", async () => {
      const val = parseFloat($("loopDelay").value);
      if (!isFinite(val) || val <= 0) return;
      await apiPost("/api/control/status", { loop_delay: val });
    });

    $("defaultStrategy").addEventListener("change", async () => {
      await apiPost("/api/control/assignments", { default: $("defaultStrategy").value });
    });

    // init
    (async () => {
      resizeCanvas();
      await loadStrategies();
      const a = await apiGet("/api/control/assignments");
      assignments = a;
      $("defaultStrategy").value = assignments.default ?? "idle";
      const status = await apiGet("/api/control/status");
      $("loopDelay").value = String(status.loop_delay ?? 0.35);
      tick();
    })();
  </script>
</body>
</html>"""
