"""2048 on a 4 by 4 grid.

Included because it also appears in lmgame-Bench, which gives one directly
comparable number between an LLM and a System One model on the same game.
"""

from __future__ import annotations

import random
from typing import Any

from jev_arcade.types import Move

__all__ = ["Twenty48", "SIZE"]

SIZE = 4
MOVES: tuple[Move, ...] = ("up", "down", "left", "right")
FOUR_PROBABILITY = 0.1


def _compress(row: list[int]) -> tuple[list[int], int]:
    """Slide and merge one row leftwards. Returns the new row and points gained.

    Each tile merges at most once per move, which is why the merged value is
    appended and the loop then skips its partner rather than reconsidering it.
    """
    tiles = [v for v in row if v]
    out: list[int] = []
    gained = 0
    i = 0
    while i < len(tiles):
        if i + 1 < len(tiles) and tiles[i] == tiles[i + 1]:
            merged = tiles[i] * 2
            out.append(merged)
            gained += merged
            i += 2
        else:
            out.append(tiles[i])
            i += 1
    out.extend([0] * (len(row) - len(out)))
    return out, gained


class Twenty48:
    """A seeded 2048 board."""

    name = "2048"

    def __init__(self, size: int = SIZE) -> None:
        self.size = size
        self._grid: list[list[int]] = []
        self._rng = random.Random(0)
        self._score = 0
        self.reset(0)

    def reset(self, seed: int) -> None:
        self._rng = random.Random(seed)
        self._grid = [[0] * self.size for _ in range(self.size)]
        self._score = 0
        self._spawn()
        self._spawn()

    def _spawn(self) -> None:
        empty = [
            (r, c) for r in range(self.size) for c in range(self.size) if not self._grid[r][c]
        ]
        if not empty:
            return
        r, c = self._rng.choice(empty)
        self._grid[r][c] = 4 if self._rng.random() < FOUR_PROBABILITY else 2

    def _rows_for(self, move: Move) -> list[list[int]]:
        """Project the grid into rows that a leftward compress will handle."""
        g = self._grid
        if move == "left":
            return [row[:] for row in g]
        if move == "right":
            return [row[::-1] for row in g]
        if move == "up":
            return [[g[r][c] for r in range(self.size)] for c in range(self.size)]
        return [[g[r][c] for r in range(self.size)][::-1] for c in range(self.size)]

    def _write_back(self, move: Move, rows: list[list[int]]) -> list[list[int]]:
        grid = [[0] * self.size for _ in range(self.size)]
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                if move == "left":
                    grid[i][j] = value
                elif move == "right":
                    grid[i][self.size - 1 - j] = value
                elif move == "up":
                    grid[j][i] = value
                else:
                    grid[self.size - 1 - j][i] = value
        return grid

    def _apply(self, move: Move) -> tuple[list[list[int]], int]:
        rows = self._rows_for(move)
        gained = 0
        new_rows = []
        for row in rows:
            compressed, points = _compress(row)
            gained += points
            new_rows.append(compressed)
        return self._write_back(move, new_rows), gained

    def legal_moves(self) -> list[Move]:
        """A move is legal only if it actually changes the board."""
        return [m for m in MOVES if self._apply(m)[0] != self._grid]

    def move_descriptions(self) -> dict[Move, str]:
        return {m: f"slide all tiles {m}" for m in self.legal_moves()}

    def step(self, move: Move) -> None:
        if move not in self.legal_moves():
            raise ValueError(f"illegal move {move!r}")
        self._grid, gained = self._apply(move)
        self._score += gained
        self._spawn()

    def to_state(self) -> dict[str, Any]:
        flat = [v for row in self._grid for v in row]
        return {
            "grid": [row[:] for row in self._grid],
            "grid_legend": "row 0 is the top. 0 means an empty cell.",
            "size": self.size,
            "max_tile": max(flat),
            "empty_cells": sum(1 for v in flat if v == 0),
            "score": self._score,
        }

    @property
    def score(self) -> int:
        return self._score

    @property
    def game_over(self) -> bool:
        return not self.legal_moves()

    @property
    def grid(self) -> list[list[int]]:
        return [row[:] for row in self._grid]
