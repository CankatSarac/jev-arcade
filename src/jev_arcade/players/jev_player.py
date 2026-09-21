"""The System One player.

One request per move. The request carries the whole legal move set as Choice
criteria, plus two speculative questions that are never needed to pick the
move but are recorded as telemetry.

Two design rules hold this together.

Questions in one request cannot see each other's answers, so no question may
depend on another. That is why the companion questions ask about the board as
it stands rather than about the move that was chosen.

The Choice criteria are built from the game's own legal move list, so an
illegal move is not something to validate against. It cannot be expressed.
"""

from __future__ import annotations

import logging
from typing import Any

from jev_arcade.players.base import Player
from jev_arcade.players.jev_client import JevAuthError, JevClient, JevError
from jev_arcade.types import Decision, Move

__all__ = ["JevPlayer", "DEFAULT_CONFIDENCE_THRESHOLD", "QUESTION_TEXT"]

logger = logging.getLogger(__name__)

DEFAULT_CONFIDENCE_THRESHOLD = 0.0  # act on every answer unless told otherwise
MAX_CHOICE_OPTIONS = 255  # TypeSafe limit


QUESTION_TEXT: dict[str, dict[str, Any]] = {
    "tetris": {
        "move": (
            "Choose where to drop the current piece. Prefer placements that complete "
            "full rows, keep the stack low and flat, and do not leave an empty cell "
            "covered by a filled cell."
        ),
        "danger": "The stack has grown close to the top and the game is about to end.",
        "health": {
            "instructions": "Rate the current state of the stack.",
            "criteria": [
                "Low and flat, with no covered empty cells",
                "Moderate height or slightly uneven, with few covered cells",
                "High or badly uneven, with many covered empty cells",
            ],
        },
    },
    "snake": {
        "move": (
            "Choose the direction to move the head. Prefer the direction that gets "
            "closer to the food without moving into a wall or into the snake's own "
            "body, and that keeps an escape route open."
        ),
        "danger": "The snake is about to trap itself with no safe move available next turn.",
        "health": {
            "instructions": "Rate how much open space the head still has around it.",
            "criteria": [
                "Wide open, many directions available",
                "Somewhat enclosed by walls or body",
                "Nearly boxed in, very little room left",
            ],
        },
    },
    "2048": {
        "move": (
            "Choose which way to slide the tiles. Prefer the slide that merges the "
            "most value, keeps the largest tile in a corner, and keeps tile values "
            "ordered along rows and columns."
        ),
        "danger": "The board is nearly full and about to lock up with no legal move.",
        "health": {
            "instructions": "Rate the current shape of the board.",
            "criteria": [
                "Plenty of empty cells and values well ordered",
                "Filling up or partly disordered",
                "Nearly full and disordered, close to locking up",
            ],
        },
    },
}


class JevPlayer:
    """Plays by asking Jev one batched question set per move."""

    def __init__(
        self,
        game_name: str,
        client: JevClient,
        fallback: Player,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ) -> None:
        if game_name not in QUESTION_TEXT:
            raise ValueError(f"no question set for game {game_name!r}")
        self.game_name = game_name
        self.name = "jev"
        self._client = client
        self._fallback = fallback
        self.confidence_threshold = confidence_threshold
        self.fallback_reasons: dict[str, int] = {}

    # ---- request construction -------------------------------------------

    def build_questions(
        self, legal_moves: list[Move], descriptions: dict[Move, str]
    ) -> dict[str, dict[str, Any]]:
        text = QUESTION_TEXT[self.game_name]
        criteria = {m: descriptions.get(m, m) for m in legal_moves}
        if len(criteria) > MAX_CHOICE_OPTIONS:
            raise ValueError(
                f"{len(criteria)} legal moves exceeds the Choice limit of "
                f"{MAX_CHOICE_OPTIONS}"
            )
        return {
            "move": {"type": "choice", "instructions": text["move"], "criteria": criteria},
            "danger": {"type": "noul", "instructions": text["danger"]},
            "health": {
                "type": "score",
                "instructions": text["health"]["instructions"],
                "criteria": text["health"]["criteria"],
            },
        }

    # ---- Player protocol -------------------------------------------------

    def choose(
        self,
        state: dict[str, Any],
        legal_moves: list[Move],
        descriptions: dict[Move, str],
    ) -> Decision:
        if len(legal_moves) == 1:
            # Nothing to decide. Spending a request here would buy nothing.
            return Decision(move=legal_moves[0], source="jev", confidence=1.0)

        questions = self.build_questions(legal_moves, descriptions)
        try:
            body, latency_ms = self._client.ask(state, questions)
        except JevAuthError:
            # A rejected key is a setup error, not a bad turn. Stop the run.
            raise
        except JevError as exc:
            logger.warning("falling back after transport failure: %s", exc)
            return self._fall_back(state, legal_moves, descriptions, "transport_error")

        answers = body.get("answers", {})
        move_answer = answers.get("move", {})
        choice = move_answer.get("choice")
        confidence = move_answer.get("confidence")

        if choice not in legal_moves:
            logger.error("Jev returned a move outside the legal set: %r", choice)
            return self._fall_back(state, legal_moves, descriptions, "illegal_answer")

        if confidence is not None and confidence < self.confidence_threshold:
            return self._fall_back(
                state, legal_moves, descriptions, "low_confidence", latency_ms
            )

        return Decision(
            move=choice,
            source="jev",
            confidence=confidence,
            latency_ms=latency_ms,
            raw={
                "probabilities": move_answer.get("probabilities"),
                "danger": answers.get("danger", {}).get("noul"),
                "health": answers.get("health", {}).get("score"),
                "health_confidence": answers.get("health", {}).get("confidence"),
                "usage": body.get("usage"),
                "model": body.get("model"),
            },
        )

    def _fall_back(
        self,
        state: dict[str, Any],
        legal_moves: list[Move],
        descriptions: dict[Move, str],
        reason: str,
        latency_ms: float | None = None,
    ) -> Decision:
        self.fallback_reasons[reason] = self.fallback_reasons.get(reason, 0) + 1
        decision = self._fallback.choose(state, legal_moves, descriptions)
        return Decision(
            move=decision.move,
            source="heuristic",
            confidence=None,
            latency_ms=latency_ms,
            raw={"fallback_reason": reason},
        )
