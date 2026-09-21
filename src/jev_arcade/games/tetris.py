"""Tetris: 10 wide by 20 tall, seven piece bag, placement level moves.

A move here is a final placement, not a keypress. `r1c4` means "rotation 1,
left edge at column 4, hard drop". That is the right granularity for a player
that thinks once per piece rather than once per frame, and it makes an illegal
move impossible to express.
"""

from __future__ import annotations

import random
from typing import Any

from jev_arcade.types import Move

__all__ = ["Tetris", "WIDTH", "HEIGHT"]

WIDTH = 10
HEIGHT = 20

LINE_SCORES = {0: 0, 1: 100, 2: 300, 3: 500, 4: 800}

# Rotation 0 of each tetromino as (row, col) cells. Every other rotation is
# derived by rotating this set, so there is no hand written rotation table to
# get subtly wrong.
BASE_SHAPES: dict[str, list[tuple[int, int]]] = {
    "I": [(0, 0), (0, 1), (0, 2), (0, 3)],
    "O": [(0, 0), (0, 1), (1, 0), (1, 1)],
    "T": [(0, 0), (0, 1), (0, 2), (1, 1)],
    "S": [(0, 1), (0, 2), (1, 0), (1, 1)],
    "Z": [(0, 0), (0, 1), (1, 1), (1, 2)],
    "J": [(0, 0), (1, 0), (1, 1), (1, 2)],
    "L": [(0, 2), (1, 0), (1, 1), (1, 2)],
}

Cells = tuple[tuple[int, int], ...]


def _normalise(cells: list[tuple[int, int]]) -> Cells:
    """Shift a cell set so its top left corner sits at (0, 0)."""
    min_r = min(r for r, _ in cells)
    min_c = min(c for _, c in cells)
    return tuple(sorted((r - min_r, c - min_c) for r, c in cells))


def _rotate_cw(cells: Cells) -> Cells:
    """Rotate a cell set 90 degrees clockwise: (r, c) becomes (c, maxR - r)."""
    max_r = max(r for r, _ in cells)
    return _normalise([(c, max_r - r) for r, c in cells])


def _rotations(name: str) -> list[Cells]:
    """All distinct rotations of a piece, in clockwise order.

    O yields one, I S and Z yield two, T J and L yield four. Deduplication is
    what makes that fall out automatically.
    """
    out: list[Cells] = []
    current = _normalise(BASE_SHAPES[name])
    for _ in range(4):
        if current not in out:
            out.append(current)
        current = _rotate_cw(current)
    return out


ROTATIONS: dict[str, list[Cells]] = {name: _rotations(name) for name in BASE_SHAPES}


class Tetris:
    """A seeded Tetris board driven one placement at a time."""

    name = "tetris"

    def __init__(self, width: int = WIDTH, height: int = HEIGHT) -> None:
        self.width = width
        self.height = height
        self._board: list[list[int]] = []
        self._rng = random.Random(0)
        self._bag: list[str] = []
        self._current = "I"
        self._next = "I"
        self._score = 0
        self._lines = 0
        self._pieces_placed = 0
        self.reset(0)

    # ---- lifecycle -------------------------------------------------------

    def reset(self, seed: int) -> None:
        self._board = [[0] * self.width for _ in range(self.height)]
        self._rng = random.Random(seed)
        self._bag = []
        self._score = 0
        self._lines = 0
        self._pieces_placed = 0
        self._current = self._draw()
        self._next = self._draw()

    def _draw(self) -> str:
        """Seven piece bag: every piece appears once before any repeats."""
        if not self._bag:
            self._bag = list(BASE_SHAPES)
            self._rng.shuffle(self._bag)
        return self._bag.pop()

    # ---- geometry --------------------------------------------------------

    def _fits(self, cells: Cells, row: int, col: int) -> bool:
        for dr, dc in cells:
            r, c = row + dr, col + dc
            if r < 0 or r >= self.height or c < 0 or c >= self.width:
                return False
            if self._board[r][c]:
                return False
        return True

    def _landing_row(self, cells: Cells, col: int) -> int | None:
        """Lowest row the piece can rest at in this column, or None if blocked."""
        if not self._fits(cells, 0, col):
            return None
        row = 0
        while self._fits(cells, row + 1, col):
            row += 1
        return row

    # ---- Game protocol ---------------------------------------------------

    def legal_moves(self) -> list[Move]:
        moves: list[Move] = []
        for rot, cells in enumerate(ROTATIONS[self._current]):
            span = max(c for _, c in cells) + 1
            for col in range(self.width - span + 1):
                if self._landing_row(cells, col) is not None:
                    moves.append(f"r{rot}c{col}")
        return moves

    def move_descriptions(self) -> dict[Move, str]:
        """Labels offered to a player as Choice criteria.

        Deliberately descriptive and not evaluative. It says where the piece
        goes, never whether going there is a good idea.
        """
        out: dict[Move, str] = {}
        for move in self.legal_moves():
            rot, col = self._parse(move)
            cells = ROTATIONS[self._current][rot]
            span = max(c for _, c in cells) + 1
            right = col + span - 1
            cols = f"column {col}" if span == 1 else f"columns {col} to {right}"
            out[move] = f"rotation {rot}, {cols}"
        return out

    def _parse(self, move: Move) -> tuple[int, int]:
        try:
            rot_s, col_s = move[1:].split("c", 1)
            return int(rot_s), int(col_s)
        except (ValueError, IndexError) as exc:
            raise ValueError(f"malformed tetris move: {move!r}") from exc

    def step(self, move: Move) -> None:
        if move not in self.legal_moves():
            raise ValueError(f"illegal move {move!r}")
        rot, col = self._parse(move)
        cells = ROTATIONS[self._current][rot]
        row = self._landing_row(cells, col)
        assert row is not None  # guaranteed by the legality check above
        piece_id = list(BASE_SHAPES).index(self._current) + 1
        for dr, dc in cells:
            self._board[row + dr][col + dc] = piece_id

        cleared = self._clear_lines()
        self._lines += cleared
        self._score += LINE_SCORES[cleared]
        self._pieces_placed += 1
        self._current, self._next = self._next, self._draw()

    def _clear_lines(self) -> int:
        kept = [row for row in self._board if not all(row)]
        cleared = self.height - len(kept)
        if cleared:
            empty = [[0] * self.width for _ in range(cleared)]
            self._board = empty + kept
        return cleared

    # ---- derived views ---------------------------------------------------

    def _column_heights(self) -> list[int]:
        heights = []
        for c in range(self.width):
            h = 0
            for r in range(self.height):
                if self._board[r][c]:
                    h = self.height - r
                    break
            heights.append(h)
        return heights

    def _holes(self) -> int:
        """Empty cells with at least one filled cell somewhere above them."""
        total = 0
        for c in range(self.width):
            seen_block = False
            for r in range(self.height):
                if self._board[r][c]:
                    seen_block = True
                elif seen_block:
                    total += 1
        return total

    def to_state(self) -> dict[str, Any]:
        return {
            "board": ["".join("#" if v else "." for v in row) for row in self._board],
            "board_legend": "row 0 is the top. '.' is empty, '#' is filled.",
            "width": self.width,
            "height": self.height,
            "current_piece": self._current,
            "next_piece": self._next,
            "column_heights": self._column_heights(),
            "holes": self._holes(),
            "lines_cleared": self._lines,
            "score": self._score,
        }

    @property
    def score(self) -> int:
        return self._score

    @property
    def game_over(self) -> bool:
        return not self.legal_moves()

    # ---- helpers for players and tests -----------------------------------

    @property
    def board(self) -> list[list[int]]:
        """Copy of the board. Callers cannot mutate the engine through it."""
        return [row[:] for row in self._board]

    @property
    def current_piece(self) -> str:
        return self._current
