"""Snake on a 12 by 12 grid.

The cleanest possible Choice question: at most four options, every one of them
a direction. If a model cannot play this, the problem is not the action space.
"""

from __future__ import annotations

import random
from typing import Any

from jev_arcade.types import Move

__all__ = ["Snake", "SIZE", "STARVATION_LIMIT"]

SIZE = 12
STARVATION_LIMIT = 400  # steps without food before the episode is cut off
FOOD_SCORE = 10

DIRECTIONS: dict[Move, tuple[int, int]] = {
    "up": (-1, 0),
    "down": (1, 0),
    "left": (0, -1),
    "right": (0, 1),
}


class Snake:
    """A seeded snake. The body is a list from head to tail."""

    name = "snake"

    def __init__(self, size: int = SIZE) -> None:
        self.size = size
        self._body: list[tuple[int, int]] = []
        self._direction: Move = "right"
        self._food: tuple[int, int] = (0, 0)
        self._rng = random.Random(0)
        self._score = 0
        self._steps_since_food = 0
        self._dead = False
        self.reset(0)

    def reset(self, seed: int) -> None:
        self._rng = random.Random(seed)
        mid = self.size // 2
        self._body = [(mid, mid), (mid, mid - 1), (mid, mid - 2)]
        self._direction = "right"
        self._score = 0
        self._steps_since_food = 0
        self._dead = False
        self._place_food()

    def _place_food(self) -> None:
        occupied = set(self._body)
        free = [
            (r, c) for r in range(self.size) for c in range(self.size) if (r, c) not in occupied
        ]
        self._food = self._rng.choice(free) if free else self._body[0]

    def _neck_move(self) -> Move | None:
        """The direction that would reverse straight into the second segment."""
        if len(self._body) < 2:
            return None
        hr, hc = self._body[0]
        nr, nc = self._body[1]
        for move, (dr, dc) in DIRECTIONS.items():
            if (hr + dr, hc + dc) == (nr, nc):
                return move
        return None

    def legal_moves(self) -> list[Move]:
        if self._dead:
            return []
        banned = self._neck_move()
        return [m for m in DIRECTIONS if m != banned]

    def move_descriptions(self) -> dict[Move, str]:
        return {m: f"move {m}" for m in self.legal_moves()}

    def step(self, move: Move) -> None:
        if move not in self.legal_moves():
            raise ValueError(f"illegal move {move!r}")
        dr, dc = DIRECTIONS[move]
        hr, hc = self._body[0]
        head = (hr + dr, hc + dc)
        self._direction = move

        out_of_bounds = not (0 <= head[0] < self.size and 0 <= head[1] < self.size)
        # The tail vacates this turn, so hitting the current tail cell is fine
        # unless the snake is about to grow into it.
        eating = head == self._food
        body_to_check = self._body if eating else self._body[:-1]
        if out_of_bounds or head in body_to_check:
            self._dead = True
            return

        self._body.insert(0, head)
        if eating:
            self._score += FOOD_SCORE
            self._steps_since_food = 0
            self._place_food()
        else:
            self._body.pop()
            self._steps_since_food += 1
            if self._steps_since_food >= STARVATION_LIMIT:
                self._dead = True

    def to_state(self) -> dict[str, Any]:
        grid = [["." for _ in range(self.size)] for _ in range(self.size)]
        for r, c in self._body[1:]:
            grid[r][c] = "o"
        hr, hc = self._body[0]
        if 0 <= hr < self.size and 0 <= hc < self.size:
            grid[hr][hc] = "H"
        fr, fc = self._food
        grid[fr][fc] = "*"
        return {
            "grid": ["".join(row) for row in grid],
            "grid_legend": "'H' is the head, 'o' is the body, '*' is food, '.' is empty.",
            "size": self.size,
            "head": {"row": hr, "col": hc},
            "food": {"row": fr, "col": fc},
            "body_length": len(self._body),
            "facing": self._direction,
            "steps_since_food": self._steps_since_food,
            "score": self._score,
        }

    @property
    def score(self) -> int:
        return self._score

    @property
    def game_over(self) -> bool:
        return self._dead

    @property
    def body(self) -> list[tuple[int, int]]:
        return list(self._body)

    @property
    def food(self) -> tuple[int, int]:
        return self._food
