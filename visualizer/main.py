from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
import pyvista as pv


@dataclass(frozen=True)
class Player:
    """Координаты игрока в клетках (x, y). y — номер строки, x — номер столбца."""
    x: int
    y: int


class Arena2DViewer:
    """
    2D-арена в PyVista:
      - статический слой: grid[y][x] (0 = пусто, 1 = стена, 2 = препятствие, ... любые ваши коды)
      - динамический слой: players (список игроков, отрисовываются поверх)
    """

    def __init__(
        self,
        cell_size: float = 1.0,
        player_z: float = 0.05,
        show_edges: bool = True,
        window_title: str = "Arena",
    ):
        self.cell_size = float(cell_size)
        self.player_z = float(player_z)
        self.show_edges = bool(show_edges)
        self.window_title = window_title

        self._plotter: pv.Plotter | None = None
        self._grid_mesh: pv.PolyData | None = None
        self._grid_actor = None

        self._players_poly: pv.PolyData | None = None
        self._players_actor = None

        self._shape: tuple[int, int] | None = None  # (rows, cols)
        self._shown: bool = False

    # ---------- public API ----------

    def show_window(self) -> None:
        """Отобразить окно (не закрывается автоматически; можно обновлять через update_state)."""
        if self._plotter is not None and self._shown:
            return

        if self._plotter is None:
            self._plotter = pv.Plotter(title=self.window_title)

        # Если состояние ещё не задавали — покажем пустую 1x1
        if self._grid_mesh is None:
            self.update_state(grid=[[0]], players=[])

        # Важно: interactive_update=True позволяет потом дергать plotter.update()
        self._plotter.show(auto_close=False, interactive_update=True)

        # Камера строго сверху, ортографическая проекция — как “2D”
        self._plotter.view_xy()
        self._plotter.enable_parallel_projection()

        self._shown = True

    def update_state(self, grid: Sequence[Sequence[int]], players: Iterable[Player]) -> None:
        """
        Изменить состояние арены: размер/содержимое/игроки.

        grid: 2D массив [rows][cols] с кодами клеток (int).
        players: координаты игроков в клетках.
        """
        grid_np = self._normalize_grid(grid)  # shape (rows, cols)
        rows, cols = grid_np.shape

        # Пересоздание геометрии, если изменился размер
        if self._shape != (rows, cols) or self._grid_mesh is None:
            self._build_scene(rows=rows, cols=cols)

        # Обновляем скаляры клеток
        cell_scalars = grid_np.astype(np.int32).ravel(order="C")  # y,x -> flatten
        assert self._grid_mesh is not None
        self._grid_mesh.cell_data["cell_type"] = cell_scalars

        # Обновляем игроков
        self._update_players(players=players, rows=rows, cols=cols)

        # Если окно уже показано — отрисовываем изменения
        if self._plotter is not None and self._shown:
            self._plotter.update()

    def close_window(self) -> None:
        """Закрыть окно и освободить ресурсы."""
        if self._plotter is not None:
            self._plotter.close()

        self._plotter = None
        self._grid_mesh = None
        self._grid_actor = None
        self._players_poly = None
        self._players_actor = None
        self._shape = None
        self._shown = False

    # ---------- internals ----------

    def _normalize_grid(self, grid: Sequence[Sequence[int]]) -> np.ndarray:
        grid_np = np.asarray(grid, dtype=np.int32)
        if grid_np.ndim != 2:
            raise ValueError(f"grid должен быть 2D, получено ndim={grid_np.ndim}")
        if grid_np.shape[0] == 0 or grid_np.shape[1] == 0:
            raise ValueError("grid не должен быть пустым")
        return grid_np

    def _build_scene(self, rows: int, cols: int) -> None:
        self._shape = (rows, cols)

        if self._plotter is None:
            self._plotter = pv.Plotter(title=self.window_title)

        self._plotter.clear()

        # Плоскость с cols*rows клетками (квадраты).
        width = cols * self.cell_size
        height = rows * self.cell_size

        plane = pv.Plane(
            center=(width / 2.0, height / 2.0, 0.0),
            i_size=width,
            j_size=height,
            i_resolution=cols,
            j_resolution=rows,
            direction=(0, 0, 1),
        )

        # Инициализируем cell_data
        plane.cell_data["cell_type"] = np.zeros(plane.n_cells, dtype=np.int32)

        self._grid_mesh = plane
        self._grid_actor = self._plotter.add_mesh(
            self._grid_mesh,
            scalars="cell_type",
            show_edges=self.show_edges,
            # Для “категорий” можно оставить стандартную палитру;
            # при желании замените cmap/opacity по своим правилам.
        )

        # Инициализируем игроков
        self._players_poly = pv.PolyData(np.empty((0, 3), dtype=np.float32))
        self._players_actor = self._plotter.add_mesh(
            self._players_poly,
            color="crimson",
            render_points_as_spheres=True,
            point_size=14,
        )

        # Подстрахуемся камерой (если show_window вызовут после update_state)
        self._plotter.view_xy()
        self._plotter.enable_parallel_projection()

    def _update_players(self, players: Iterable[Player], rows: int, cols: int) -> None:
        pts = []
        for p in players:
            if not (0 <= p.x < cols and 0 <= p.y < rows):
                # Игрок вне поля — просто пропускаем (или можете raise)
                continue
            x = (p.x + 0.5) * self.cell_size
            y = (p.y + 0.5) * self.cell_size
            pts.append((x, y, self.player_z))

        points = np.asarray(pts, dtype=np.float32)
        if points.size == 0:
            points = np.empty((0, 3), dtype=np.float32)

        assert self._players_poly is not None
        self._players_poly.points = points


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
    players = [Player(1, 1), Player(4, 3)]

    viewer.update_state(grid=grid, players=players)
    viewer.show_window()

    # Дальше можете в цикле вызывать viewer.update_state(...)
    # viewer.close_window() по завершению