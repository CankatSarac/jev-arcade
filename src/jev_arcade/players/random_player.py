"""Uniform random play. The null baseline every other number is read against.

lmgame-Bench found LLM scores on Tetris sitting close to random, so this is
not a throwaway control. It is the bar the experiment exists to check.
"""

from __future__ import annotations

import random
from typing import Any

from jev_arcade.types import Decision, Move

__all__ = ["RandomPlayer"]


class RandomPlayer:
    name = "random"

    def __init__(self, seed: int = 0) -> None:
        self._rng = random.Random(seed)

    def choose(
        self,
        state: dict[str, Any],
        legal_moves: list[Move],
        descriptions: dict[Move, str],
    ) -> Decision:
        return Decision(move=self._rng.choice(legal_moves), source="random")
