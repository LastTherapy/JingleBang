from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import time
from typing import Iterable, Sequence

import numpy as np
import pyvista as pv


@dataclass(frozen=True)
class Player:
    """Координаты игрока в клетках (x, y). y — номер строки, x — номер столбца."""
    x: int
    y: int

import time
import queue
import multiprocessing as mp


def _viz_process_main(state_q: mp.Queue, stop, cell_size: float = 1.0):
    # Внутри процесса импортируем pyvista (лучше так, чем вверху файла)
    import pyvista as pv

    # твой класс
    viewer = Arena2DViewerMeshes(cell_size=cell_size)

    viewer.show_window(block=False)

    latest_grid = None
    latest_players = None

    target_dt = 1.0 / 60.0  # 60 FPS
    last_frame = time.perf_counter()

    while not stop.is_set():
        # 1) Забираем ВСЕ обновления из очереди, оставляем только последнее
        try:
            while True:
                msg = state_q.get_nowait()
                if msg is None:          # sentinel на закрытие
                    stop.set()
                    break
                if msg["type"] == "state":
                    latest_grid = msg["grid"]
                    latest_players = msg.get("players", [])
                elif msg["type"] == "close":
                    stop.set()
                    break
        except queue.Empty:
            pass

        # 2) Применяем последнее состояние (если оно пришло)
        if latest_grid is not None:
            viewer.update_state_json(latest_grid)
            latest_grid = None  # применили — сбросили

        # 3) Плавный рендер/ивенты каждый кадр
        if viewer._plotter is not None:
            viewer._plotter.update()

        # 4) ограничение FPS
        now = time.perf_counter()
        dt = now - last_frame
        if dt < target_dt:
            time.sleep(target_dt - dt)
        last_frame = now

    viewer.close_window()


class ArenaVizProcess:
    def __init__(self, cell_size: float = 1.0):
        # На macOS/Windows лучше spawn, VTK/GUI с fork часто чудит
        self._ctx = mp.get_context("spawn")
        self._q: mp.Queue = self._ctx.Queue(maxsize=5)   # маленькая, чтобы не копить лаг
        self._stop: mp.Event = self._ctx.Event()
        self._p: mp.Process = self._ctx.Process(
            target=_viz_process_main,
            args=(self._q, self._stop, cell_size),
            daemon=True,
        )

    def start(self):
        self._p.start()

    def set_state(self, jsonka):
        """
        grid: list[list[int]]
        players_xy: list[tuple[int,int]]  например [(1,1),(4,3)]
        """
        msg = {"type": "state", "grid": jsonka}

        # Если очередь забита, выбрасываем старое состояние — чтобы не лагало
        try:
            self._q.put_nowait(msg)
        except queue.Full:
            try:
                _ = self._q.get_nowait()
            except queue.Empty:
                pass
            try:
                self._q.put_nowait(msg)
            except queue.Full:
                pass

    def close(self):
        try:
            self._q.put_nowait({"type": "close"})
        except Exception:
            pass
        self._stop.set()
        if self._p.is_alive():
            self._p.join(timeout=2.0)


# class Arena2DViewer:
#     """
#     2D-арена в PyVista:
#       - статический слой: grid[y][x] (0 = пусто, 1 = стена, 2 = препятствие, ... любые ваши коды)
#       - динамический слой: players (список игроков, отрисовываются поверх)
#     """

#     class BlockType(Enum):
#         EMTPY = 0
#         WALL = 1
#         OBSTACLE = 2
#         PLAYER = 3

#     def __init__(
#         self,
#         cell_size: float = 1.0,
#         player_z: float = 0.05,
#         show_edges: bool = True,
#         window_title: str = "Arena",
#     ):
#         pv.global_theme.allow_empty_mesh = True

#         self.cell_size = float(cell_size)
#         self.player_z = float(player_z)
#         self.show_edges = bool(show_edges)
#         self.window_title = window_title

#         self._plotter: pv.Plotter | None = None
#         self._grid_mesh: pv.PolyData | None = None
#         self._cell_scalars: np.ndarray | None = None
#         self._grid_actor = None

#         self._players_poly: pv.PolyData | None = None
#         self._players_actor = None

#         self._shape: tuple[int, int] | None = None  # (rows, cols)
#         self._shown: bool = False

#     # ---------- public API ----------

#     def show_window(self) -> None:
#         """Отобразить окно (не закрывается автоматически; можно обновлять через update_state)."""
#         if self._plotter is not None and self._shown:
#             return

#         if self._plotter is None:
#             self._plotter = pv.Plotter(title=self.window_title)

#         # Если состояние ещё не задавали — покажем пустую 1x1
#         if self._grid_mesh is None:
#             self.update_state(grid=[[0]])

#         # Важно: interactive_update=True позволяет потом дергать plotter.update()
#         self._plotter.show(auto_close=False, interactive_update=True)

#         # Камера строго сверху, ортографическая проекция — как “2D”
#         self._plotter.view_xy()
#         self._plotter.enable_parallel_projection()

#         self._shown = True

#     def update_state_json(self, grid):
#         obstacles = grid["arena"]["obstacles"]
#         walls = grid["arena"]["walls"]
#         # arenaWidth = max(map(lambda a: a[0], obstacles)) + 1
#         # arenaHeight = max(map(lambda a: a[1], obstacles)) + 1        
#         arenaWidth = grid["map_size"][0]
#         arenaHeight = grid["map_size"][1]

#         curMap = [[0 for _ in range(arenaHeight)] for _ in range(arenaWidth)]
#         for cur in obstacles:
#             curMap[cur[0]][cur[1]] = 2
#         for cur in walls:
#             curMap[cur[0]][cur[1]] = 1

#         players = [Player(1, 1), Player(4, 3)]

#         self.update_state(curMap, players)

#     def update_state(self, grid: Sequence[Sequence[int]]) -> None:
#         """
#         Изменить состояние арены: размер/содержимое/игроки.

#         grid: 2D массив [rows][cols] с кодами клеток (int).
#         players: координаты игроков в клетках.
#         """
#         grid_np = self._normalize_grid(grid)  # shape (rows, cols)
#         rows, cols = grid_np.shape

#         # Пересоздание геометрии, если изменился размер
#         if self._shape != (rows, cols) or self._grid_mesh is None:
#             self._build_scene(rows=rows, cols=cols)

#         # Обновляем скаляры клеток
#         cell_scalars = grid_np.astype(np.int32).ravel(order="C")  # y,x -> flatten
#         assert self._grid_mesh is not None
#         self._grid_mesh.cell_data["cell_type"] = cell_scalars

#         # Обновляем игроков
#         # self._update_players(players=players, rows=rows, cols=cols)

#         # Если окно уже показано — отрисовываем изменения
#         if self._plotter is not None and self._shown:
#             cell_scalars_view = grid_np.astype(np.int32, copy=False).ravel(order="C")
#             assert self._cell_scalars is not None
#             self._cell_scalars[:] = cell_scalars_view
#             self._plotter.update()

#     def close_window(self) -> None:
#         """Закрыть окно и освободить ресурсы."""
#         if self._plotter is not None:
#             self._plotter.close()

#         self._plotter = None
#         self._grid_mesh = None
#         self._grid_actor = None
#         self._players_poly = None
#         self._players_actor = None
#         self._shape = None
#         self._shown = False

#     # ---------- internals ----------

#     def _normalize_grid(self, grid: Sequence[Sequence[int]]) -> np.ndarray:
#         grid_np = np.asarray(grid, dtype=np.int32)
#         if grid_np.ndim != 2:
#             raise ValueError(f"grid должен быть 2D, получено ndim={grid_np.ndim}")
#         if grid_np.shape[0] == 0 or grid_np.shape[1] == 0:
#             raise ValueError("grid не должен быть пустым")
#         return grid_np

#     def _build_scene(self, rows: int, cols: int) -> None:
#         self._shape = (rows, cols)

#         if self._plotter is None:
#             self._plotter = pv.Plotter(title=self.window_title)

#         self._plotter.clear()

#         # Плоскость с cols*rows клетками (квадраты).
#         width = cols * self.cell_size
#         height = rows * self.cell_size

#         plane = pv.Plane(
#             center=(width / 2.0, height / 2.0, 0.0),
#             i_size=width,
#             j_size=height,
#             i_resolution=cols,
#             j_resolution=rows,
#             direction=(0, 0, 1),
#         )

#         # Инициализируем cell_data
#         self._cell_scalars = np.zeros(plane.n_cells, dtype=np.int32)
#         plane.cell_data["cell_type"] = self._cell_scalars

#         self._grid_mesh = plane
#         self._grid_actor = self._plotter.add_mesh(
#             self._grid_mesh,
#             scalars="cell_type",
#             show_edges=self.show_edges,
#             # Для “категорий” можно оставить стандартную палитру;
#             # при желании замените cmap/opacity по своим правилам.
#         )

#         # Инициализируем игроков
#         self._players_poly = pv.PolyData(np.empty((0, 3), dtype=np.float32))
#         self._players_actor = self._plotter.add_mesh(
#             self._players_poly,
#             color="crimson",
#             render_points_as_spheres=True,
#             point_size=14,
#         )

#         # Подстрахуемся камерой (если show_window вызовут после update_state)
#         self._plotter.view_xy()
#         self._plotter.enable_parallel_projection()

#     def _update_players(self, players: Iterable[Player], rows: int, cols: int) -> None:
#         pts = []
#         for p in players:
#             if not (0 <= p.x < cols and 0 <= p.y < rows):
#                 # Игрок вне поля — просто пропускаем (или можете raise)
#                 continue
#             x = (p.x + 0.5) * self.cell_size
#             y = (p.y + 0.5) * self.cell_size
#             pts.append((x, y, self.player_z))

#         points = np.asarray(pts, dtype=np.float32)
#         if points.size == 0:
#             points = np.empty((0, 3), dtype=np.float32)

#         assert self._players_poly is not None
#         if self._players_poly.n_points == points.shape[0]:
#             # in-place
#             if points.shape[0] > 0:
#                 self._players_poly.points[:] = points
#         else:
#             # только когда кол-во игроков изменилось
#             self._players_poly.points = points



class Arena2DViewerMeshes:
    """
    Простая 3D-визуализация 2D арены:
      - grid[y][x] : 0 пусто, 1 стена, 2 препятствие (можно расширить)
      - стены/препятствия: кубы
      - игроки: сферы
    """

    class BlockType(Enum):
        EMTPY = 0
        WALL = 1
        OBSTACLE = 2
        PLAYER = 3

    def __init__(self, cell_size: float = 1.0, wall_h: float = 1.0, obstacle_h: float = 0.6):
        pv.global_theme.allow_empty_mesh = True
        self.cell_size = float(cell_size)
        self.wall_h = float(wall_h)
        self.obstacle_h = float(obstacle_h)

        self._plotter: pv.Plotter | None = None
        self._shown = False
        self._shape: tuple[int, int] | None = None

        self._floor_actor = None
        self._walls_actor = None
        self._obstacles_actor = None
        self._players_actor = None

    # --- API ---
    def show_window(self, block: bool = False) -> None:
        if self._plotter is None:
            self._plotter = pv.Plotter(title="Arena (Meshes)")

        # если ничего не задавали — пустая сцена 1x1
        if self._shape is None:
            self.update_state([[0]], [])

        # 2D-вид сверху, но с “высотой” объектов
        self._plotter.view_xy()
        self._plotter.enable_parallel_projection()

        # НЕ блокируем по умолчанию (как ты делал с анимацией)
        self._plotter.show(auto_close=False, interactive_update=not block)
        self._shown = not block

    def update_state_json(self, grid):
        obstacles = grid["arena"]["obstacles"]
        walls = grid["arena"]["walls"]
        # arenaWidth = max(map(lambda a: a[0], obstacles)) + 1
        # arenaHeight = max(map(lambda a: a[1], obstacles)) + 1        
        arenaWidth = grid["map_size"][0]
        arenaHeight = grid["map_size"][1]

        curMap = [[0 for _ in range(arenaHeight)] for _ in range(arenaWidth)]
        for cur in obstacles:
            curMap[cur[0]][cur[1]] = 2
        for cur in walls:
            curMap[cur[0]][cur[1]] = 1
            
        players = [Player(1, 1), Player(4, 3)]

        self.update_state(curMap, players)


    def update_state(self, grid: Sequence[Sequence[int]], players: Iterable[Player]) -> None:
        grid_np = np.asarray(grid, dtype=np.int32)
        if grid_np.ndim != 2 or grid_np.size == 0:
            raise ValueError("grid должен быть непустым 2D массивом")

        rows, cols = grid_np.shape
        if self._plotter is None:
            self._plotter = pv.Plotter(title="Arena (Meshes)")

        # пересобираем “пол” при смене размера
        if self._shape != (rows, cols):
            self._shape = (rows, cols)
            self._plotter.clear()
            self._build_floor(rows, cols)
            # акторы под динамику “обнулим”
            self._walls_actor = None
            self._obstacles_actor = None
            self._players_actor = None

        # 1) стены
        walls_pts = self._cells_to_points(grid_np == 1)
        walls_mesh = self._glyph_cubes(walls_pts, z=self.wall_h / 2.0, height=self.wall_h)

        if self._walls_actor is not None:
            self._plotter.remove_actor(self._walls_actor)
        self._walls_actor = self._plotter.add_mesh(walls_mesh, color="slategray")

        # 2) препятствия
        obs_pts = self._cells_to_points(grid_np == 2)
        obs_mesh = self._glyph_cubes(obs_pts, z=self.obstacle_h / 2.0, height=self.obstacle_h)

        if self._obstacles_actor is not None:
            self._plotter.remove_actor(self._obstacles_actor)
        self._obstacles_actor = self._plotter.add_mesh(obs_mesh, color="sienna")

        # 3) игроки
        pl_pts = []
        for p in players:
            if 0 <= p.x < cols and 0 <= p.y < rows:
                pl_pts.append(((p.x + 0.5) * self.cell_size, (p.y + 0.5) * self.cell_size))
        pl_mesh = self._glyph_spheres(np.asarray(pl_pts, dtype=np.float32), z=0.35)

        if self._players_actor is not None:
            self._plotter.remove_actor(self._players_actor)
        self._players_actor = self._plotter.add_mesh(pl_mesh, color="crimson")

        # рендер кадра (если окно неблокирующее)
        # if self._shown and self._plotter is not None:
        #     self._plotter.update()

    def close_window(self) -> None:
        if self._plotter is not None:
            self._plotter.close()
        self._plotter = None
        self._shown = False
        self._shape = None
        self._floor_actor = None
        self._walls_actor = None
        self._obstacles_actor = None
        self._players_actor = None

    # --- internals ---
    def _build_floor(self, rows: int, cols: int) -> None:
        assert self._plotter is not None
        w = cols * self.cell_size
        h = rows * self.cell_size

        floor = pv.Plane(
            center=(w / 2.0, h / 2.0, 0.0),
            i_size=w,
            j_size=h,
            i_resolution=cols,
            j_resolution=rows,
            direction=(0, 0, 1),
        )
        self._floor_actor = self._plotter.add_mesh(floor, color="white", show_edges=True, opacity=0.25)
        self._plotter.view_xy()                      # камера строго сверху
        self._plotter.enable_parallel_projection()   # ортографика (как карта)
        self._plotter.enable_2d_style()              # ВАЖНО: отключает вращение, оставляет pan/zoom

    def _cells_to_points(self, mask: np.ndarray) -> np.ndarray:
        """mask shape (rows, cols) -> точки центров клеток (N, 2)."""
        ys, xs = np.nonzero(mask)
        if xs.size == 0:
            return np.empty((0, 2), dtype=np.float32)
        pts = np.stack([(xs + 0.5) * self.cell_size, (ys + 0.5) * self.cell_size], axis=1)
        return pts.astype(np.float32, copy=False)

    def _glyph_cubes(self, xy: np.ndarray, z: float, height: float) -> pv.PolyData:
        if xy.size == 0:
            return pv.PolyData()  # пусто — просто не будет кубов
        pts3 = np.column_stack([xy, np.full((xy.shape[0],), z, dtype=np.float32)])
        cloud = pv.PolyData(pts3)
        cube = pv.Cube(
            center=(0, 0, 0),
            x_length=self.cell_size,
            y_length=self.cell_size,
            z_length=height,
        )
        return cloud.glyph(geom=cube, scale=False, orient=False)

    def _glyph_spheres(self, xy: np.ndarray, z: float) -> pv.PolyData:
        if xy.size == 0:
            return pv.PolyData()
        pts3 = np.column_stack([xy, np.full((xy.shape[0],), z, dtype=np.float32)])
        cloud = pv.PolyData(pts3)
        sphere = pv.Sphere(radius=self.cell_size * 0.28, center=(0, 0, 0))
        return cloud.glyph(geom=sphere, scale=False, orient=False)


# ------------------ пример использования ------------------
if __name__ == "__main__":
    viewer = Arena2DViewer(cell_size=1.0, window_title="2D Arena (PyVista)")

    grid = [
        [1, 1, 1, 1, 1, 1],
        [1, 0, 0, 2, 0, 1],
        [1, 0, 0, 0, 0, 1],
        [1, 0, 2, 0, 0, 1],
        [1, 0, 0, 0, 0, 1],
        [1, 1, 1, 1, 1, 1],
    ]

    with open("/Users/ohaggard/trash/JingleBang/visualizer/test.json", "r") as f:
        loadedJson = json.loads(f.read())
    viewer.update_state_json(grid=loadedJson)
    # viewer.update_state(grid=grid)
    viewer.show_window()

    while True:
        viewer._plotter.update()
        time.sleep(0.016)  # ~60 FPS