"""A scripted player, so the harness can be tested without a network."""

from __future__ import annotations

from collections import deque
from typing import Any

from jev_arcade.types import Decision, Move

__all__ = ["MockPlayer"]


class MockPlayer:
    name = "mock"

    def __init__(self, moves: list[Move] | None = None, confidence: float | None = None) -> None:
        self._queue: deque[Move] = deque(moves or [])
        self._confidence = confidence

    def choose(
        self,
        state: dict[str, Any],
        legal_moves: list[Move],
        descriptions: dict[Move, str],
    ) -> Decision:
        while self._queue:
            move = self._queue.popleft()
            if move in legal_moves:
                return Decision(move=move, source="mock", confidence=self._confidence)
        return Decision(move=legal_moves[0], source="mock", confidence=self._confidence)
