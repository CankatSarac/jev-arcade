"""Drives one episode: ask the player, apply the move, record what happened."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from jev_arcade.games.base import Game
from jev_arcade.players.base import Player
from jev_arcade.types import Episode, MoveRecord

__all__ = ["run_episode", "DEFAULT_MAX_TURNS"]

DEFAULT_MAX_TURNS = 2000

StepHook = Callable[[Game, MoveRecord], None]


def run_episode(
    game: Game,
    player: Player,
    seed: int,
    max_turns: int = DEFAULT_MAX_TURNS,
    on_step: StepHook | None = None,
    meta: dict[str, Any] | None = None,
) -> Episode:
    """Play one full game and return the record of it.

    The turn cap exists so a player that finds a safe loop cannot run forever.
    Snake has its own starvation rule, but 2048 and Tetris rely on this.
    """
    game.reset(seed)
    records: list[MoveRecord] = []

    while not game.game_over and len(records) < max_turns:
        legal = game.legal_moves()
        if not legal:
            break
        started = time.perf_counter()
        decision = player.choose(game.to_state(), legal, game.move_descriptions())
        elapsed_ms = (time.perf_counter() - started) * 1000.0

        if decision.move not in legal:
            raise ValueError(
                f"player {player.name} returned illegal move {decision.move!r}; "
                f"legal moves were {legal}"
            )

        game.step(decision.move)
        record = MoveRecord(
            turn=len(records),
            move=decision.move,
            source=decision.source,
            confidence=decision.confidence,
            score_after=game.score,
            latency_ms=decision.latency_ms if decision.latency_ms is not None else elapsed_ms,
        )
        records.append(record)
        if on_step is not None:
            on_step(game, record)

    return Episode(
        game=game.name,
        player=player.name,
        seed=seed,
        final_score=game.score,
        turns=len(records),
        moves=records,
        meta=meta or {},
    )
