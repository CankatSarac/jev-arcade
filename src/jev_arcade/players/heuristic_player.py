"""Deterministic, game specific heuristics.

Two jobs. It is the strong baseline Jev is measured against, and it is the
fallback Jev delegates to when its confidence is too low to act on.

Every strategy works from the serialized state only, never from the game
object. That is deliberate: the heuristic sees exactly what Jev sees, so a
comparison between them is a comparison of judgement rather than of access.
"""

from __future__ import annotations

from typing import Any

from jev_arcade.games.snake import DIRECTIONS
from jev_arcade.games.tetris import ROTATIONS
from jev_arcade.types import Decision, Move

__all__ = ["HeuristicPlayer"]

# Weights from the widely reproduced Tetris feature set: aggregate height,
# completed lines, holes and bumpiness. Holes are punished hardest because a
# buried gap costs many future pieces to undo.
W_HEIGHT = -0.510066
W_LINES = 0.760666
W_HOLES = -0.356630
W_BUMPINESS = -0.184483


def _board_from_state(rows: list[str]) -> list[list[int]]:
    return [[1 if ch == "#" else 0 for ch in row] for row in rows]


def _features(board: list[list[int]]) -> tuple[int, int, int]:
    """Aggregate height, hole count and bumpiness for a settled board."""
    height = len(board)
    width = len(board[0])
    heights = []
    holes = 0
    for c in range(width):
        col_height = 0
        seen = False
        for r in range(height):
            if board[r][c]:
                if not seen:
                    col_height = height - r
                    seen = True
            elif seen:
                holes += 1
        heights.append(col_height)
    bumpiness = sum(abs(heights[i] - heights[i + 1]) for i in range(width - 1))
    return sum(heights), holes, bumpiness


def _place(board: list[list[int]], cells: tuple[tuple[int, int], ...], col: int) -> list[list[int]] | None:
    """Drop a piece into a column and return the resulting board, or None."""
    height, width = len(board), len(board[0])

    def fits(row: int) -> bool:
        for dr, dc in cells:
            r, c = row + dr, col + dc
            if r < 0 or r >= height or c < 0 or c >= width or board[r][c]:
                return False
        return True

    if not fits(0):
        return None
    row = 0
    while fits(row + 1):
        row += 1
    out = [r[:] for r in board]
    for dr, dc in cells:
        out[row + dr][col + dc] = 1
    return out


def _clear(board: list[list[int]]) -> tuple[list[list[int]], int]:
    kept = [row for row in board if not all(row)]
    cleared = len(board) - len(kept)
    width = len(board[0])
    return [[0] * width for _ in range(cleared)] + kept, cleared


class HeuristicPlayer:
    """One class, one strategy per game, selected by name."""

    def __init__(self, game_name: str) -> None:
        self.game_name = game_name
        self.name = f"heuristic_{game_name}"
        self._strategies = {
            "tetris": self._tetris,
            "snake": self._snake,
            "2048": self._twenty48,
        }
        if game_name not in self._strategies:
            raise ValueError(f"no heuristic for game {game_name!r}")

    def choose(
        self,
        state: dict[str, Any],
        legal_moves: list[Move],
        descriptions: dict[Move, str],
    ) -> Decision:
        move = self._strategies[self.game_name](state, legal_moves)
        return Decision(move=move, source="heuristic")

    # ---- Tetris ----------------------------------------------------------

    def _tetris(self, state: dict[str, Any], legal_moves: list[Move]) -> Move:
        board = _board_from_state(state["board"])
        piece = state["current_piece"]
        best_move, best_value = legal_moves[0], float("-inf")
        for move in legal_moves:
            rot_s, col_s = move[1:].split("c", 1)
            cells = ROTATIONS[piece][int(rot_s)]
            placed = _place(board, cells, int(col_s))
            if placed is None:
                continue
            settled, lines = _clear(placed)
            agg, holes, bump = _features(settled)
            value = W_HEIGHT * agg + W_LINES * lines + W_HOLES * holes + W_BUMPINESS * bump
            if value > best_value:
                best_move, best_value = move, value
        return best_move

    # ---- Snake -----------------------------------------------------------

    def _snake(self, state: dict[str, Any], legal_moves: list[Move]) -> Move:
        grid = state["grid"]
        size = state["size"]
        head = (state["head"]["row"], state["head"]["col"])
        food = (state["food"]["row"], state["food"]["col"])
        blocked = {
            (r, c) for r in range(size) for c in range(size) if grid[r][c] in ("o", "H")
        }

        def survives(cell: tuple[int, int]) -> bool:
            r, c = cell
            return 0 <= r < size and 0 <= c < size and cell not in blocked

        def free_space(start: tuple[int, int]) -> int:
            """Flood fill from a cell. Prefers moves that keep room to move."""
            seen = {start}
            stack = [start]
            while stack:
                r, c = stack.pop()
                for dr, dc in DIRECTIONS.values():
                    nxt = (r + dr, c + dc)
                    if nxt not in seen and survives(nxt):
                        seen.add(nxt)
                        stack.append(nxt)
            return len(seen)

        def distance(cell: tuple[int, int]) -> int:
            return abs(cell[0] - food[0]) + abs(cell[1] - food[1])

        safe = []
        for move in legal_moves:
            dr, dc = DIRECTIONS[move]
            cell = (head[0] + dr, head[1] + dc)
            if survives(cell):
                safe.append((move, cell))
        if not safe:
            return legal_moves[0]  # cornered, any move loses

        # Take room first, then distance to food. Chasing food into a dead end
        # is the single most common way a greedy snake kills itself.
        best = max(safe, key=lambda mc: (free_space(mc[1]), -distance(mc[1])))
        return best[0]

    # ---- 2048 ------------------------------------------------------------

    def _twenty48(self, state: dict[str, Any], legal_moves: list[Move]) -> Move:
        from jev_arcade.games.twenty48 import Twenty48

        best_move, best_value = legal_moves[0], float("-inf")
        for move in legal_moves:
            sim = Twenty48()
            sim._grid = [row[:] for row in state["grid"]]
            grid, gained = sim._apply(move)
            value = gained + self._board_value(grid)
            if value > best_value:
                best_move, best_value = move, value
        return best_move

    @staticmethod
    def _board_value(grid: list[list[int]]) -> float:
        size = len(grid)
        flat = [v for row in grid for v in row]
        empty = sum(1 for v in flat if v == 0)
        largest = max(flat)

        monotonic = 0
        for row in grid:
            values = [v for v in row if v]
            if values == sorted(values) or values == sorted(values, reverse=True):
                monotonic += 1
        for c in range(size):
            column = [grid[r][c] for r in range(size) if grid[r][c]]
            if column == sorted(column) or column == sorted(column, reverse=True):
                monotonic += 1

        corners = (grid[0][0], grid[0][-1], grid[-1][0], grid[-1][-1])
        corner_bonus = largest * 2 if largest in corners else 0
        return empty * 12 + monotonic * 8 + corner_bonus
