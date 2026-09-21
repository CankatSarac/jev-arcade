"""The Game protocol.

A game is a pure, seeded state machine. It knows nothing about players, about
Jev, or about rendering. That one way dependency is what lets the whole test
suite run without a network.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from jev_arcade.types import Move

__all__ = ["Game", "BANNED_STATE_KEYS"]

# Serialized state must describe what is on the board and nothing else. A key
# that evaluates the position or suggests a move would leak the answer into the
# question, which is how a benchmark quietly stops measuring anything. Enforced
# by tests/test_state_hygiene.py.
BANNED_STATE_KEYS = frozenset(
    {"note", "hint", "suggestion", "suggested", "best", "best_move", "advice", "answer", "tip"}
)


@runtime_checkable
class Game(Protocol):
    name: str

    def reset(self, seed: int) -> None:
        """Start a fresh episode. Same seed always yields the same episode."""
        ...

    def legal_moves(self) -> list[Move]:
        """Every move that is valid right now. Never empty unless game_over."""
        ...

    def move_descriptions(self) -> dict[Move, str]:
        """Human readable label per legal move, used as Jev Choice criteria."""
        ...

    def step(self, move: Move) -> None:
        """Apply a move. Raises ValueError if the move is not legal."""
        ...

    def to_state(self) -> dict[str, Any]:
        """JSON serializable view of observable facts only."""
        ...

    @property
    def score(self) -> int: ...

    @property
    def game_over(self) -> bool: ...
