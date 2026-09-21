"""The Player protocol.

A player sees the serialized state, the legal moves and their labels. It never
sees the game object, so it cannot cheat by simulating through private state.
The heuristic players get around this honestly: they rebuild a board from the
serialized state, exactly as Jev would have to.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from jev_arcade.types import Decision, Move

__all__ = ["Player"]


@runtime_checkable
class Player(Protocol):
    name: str

    def choose(
        self,
        state: dict[str, Any],
        legal_moves: list[Move],
        descriptions: dict[Move, str],
    ) -> Decision:
        """Pick one of legal_moves. Must never return a move outside that list."""
        ...
