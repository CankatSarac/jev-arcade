"""Core value types shared by games, players and the harness.

Everything here is immutable. Games own mutable state internally, but every
value that crosses a module boundary is frozen so a player cannot reach back
into the engine and change it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

__all__ = ["Move", "Source", "Decision", "MoveRecord", "Episode"]

# A move is an opaque key. It is always a member of the game's legal_moves()
# list, which is also exactly what gets offered to Jev as Choice criteria.
Move = str

Source = Literal["jev", "heuristic", "random", "mock"]


@dataclass(frozen=True)
class Decision:
    """What a player decided, and how much it believed in it."""

    move: Move
    source: Source
    confidence: float | None = None
    raw: dict[str, Any] | None = None
    latency_ms: float | None = None


@dataclass(frozen=True)
class MoveRecord:
    """One turn of an episode, as written to the replay log."""

    turn: int
    move: Move
    source: Source
    confidence: float | None
    score_after: int
    latency_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn": self.turn,
            "move": self.move,
            "source": self.source,
            "confidence": self.confidence,
            "score_after": self.score_after,
            "latency_ms": self.latency_ms,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MoveRecord:
        return cls(
            turn=int(d["turn"]),
            move=str(d["move"]),
            source=d["source"],
            confidence=d["confidence"],
            score_after=int(d["score_after"]),
            latency_ms=d.get("latency_ms"),
        )


@dataclass(frozen=True)
class Episode:
    """A complete run of one game by one player at one seed."""

    game: str
    player: str
    seed: int
    final_score: int
    turns: int
    moves: list[MoveRecord] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def fallback_rate(self) -> float:
        """Fraction of turns that did not come from the player's primary source.

        For a JevPlayer this is the share of moves the heuristic had to cover,
        either because confidence was low or because a request failed.
        """
        if not self.moves:
            return 0.0
        primary = "jev" if self.player.startswith("jev") else self.moves[0].source
        other = sum(1 for m in self.moves if m.source != primary)
        return other / len(self.moves)

    def to_dict(self) -> dict[str, Any]:
        return {
            "game": self.game,
            "player": self.player,
            "seed": self.seed,
            "final_score": self.final_score,
            "turns": self.turns,
            "moves": [m.to_dict() for m in self.moves],
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Episode:
        return cls(
            game=d["game"],
            player=d["player"],
            seed=int(d["seed"]),
            final_score=int(d["final_score"]),
            turns=int(d["turns"]),
            moves=[MoveRecord.from_dict(m) for m in d.get("moves", [])],
            meta=d.get("meta", {}),
        )
