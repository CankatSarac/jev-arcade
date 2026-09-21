"""Run two players over the same seed in lockstep and yield combined frames.

Both sides get an identical starting board and an identical piece sequence,
because the games are seeded. That is what makes the comparison fair and what
makes the difference visible: on Snake the two boards track each other, on
Tetris you watch one stack top out while the other keeps clearing.

Each side advances independently once started, so a player that dies early
simply stops while the other plays on.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

from jev_arcade.games.snake import Snake
from jev_arcade.games.tetris import Tetris
from jev_arcade.games.twenty48 import Twenty48
from jev_arcade.players.heuristic_player import HeuristicPlayer
from jev_arcade.players.jev_client import JevAuthError, JevClient, JevError
from jev_arcade.players.jev_player import JevPlayer
from jev_arcade.players.random_player import RandomPlayer

__all__ = ["GAMES", "PLAYER_KINDS", "build_player", "race_frames"]

GAMES = {"tetris": Tetris, "snake": Snake, "2048": Twenty48}
PLAYER_KINDS = ("jev", "heuristic", "random")

# Top N options to show as probability bars in the browser.
TOP_OPTIONS = 5


def build_player(kind: str, game_name: str, seed: int, threshold: float) -> Any:
    if kind == "heuristic":
        return HeuristicPlayer(game_name)
    if kind == "random":
        return RandomPlayer(seed)
    if kind == "jev":
        return JevPlayer(
            game_name, JevClient.from_env(), HeuristicPlayer(game_name), threshold
        )
    raise ValueError(f"unknown player {kind!r}")


def _side(game: Any) -> dict[str, Any]:
    return {"state": game.to_state(), "score": game.score, "over": game.game_over}


def _advance(game: Any, player: Any) -> dict[str, Any]:
    """Take one turn and describe it. Never raises for an ordinary failure."""
    if game.game_over:
        return {"over": True}
    legal = game.legal_moves()
    if not legal:
        return {"over": True}

    started = time.perf_counter()
    decision = player.choose(game.to_state(), legal, game.move_descriptions())
    elapsed = (time.perf_counter() - started) * 1000.0
    game.step(decision.move)

    raw = decision.raw or {}
    probabilities = raw.get("probabilities") or {}
    top = sorted(probabilities.items(), key=lambda kv: kv[1], reverse=True)[:TOP_OPTIONS]
    return {
        "move": decision.move,
        "source": decision.source,
        "confidence": decision.confidence,
        "latency_ms": round(decision.latency_ms or elapsed, 1),
        "top_options": [{"move": m, "p": round(p, 3)} for m, p in top],
        "danger": raw.get("danger"),
        "health": raw.get("health"),
        "fallback_reason": raw.get("fallback_reason"),
        "over": game.game_over,
    }


def race_frames(
    game_name: str,
    left_kind: str = "jev",
    right_kind: str = "heuristic",
    seed: int = 0,
    max_turns: int = 60,
    threshold: float = 0.0,
) -> Iterator[dict[str, Any]]:
    """Yield one frame per turn, plus an opening frame and a closing summary."""
    if game_name not in GAMES:
        raise ValueError(f"unknown game {game_name!r}")
    for kind in (left_kind, right_kind):
        if kind not in PLAYER_KINDS:
            raise ValueError(f"unknown player {kind!r}")

    left_game, right_game = GAMES[game_name](), GAMES[game_name]()
    left_game.reset(seed)
    right_game.reset(seed)
    try:
        left_player = build_player(left_kind, game_name, seed, threshold)
        right_player = build_player(right_kind, game_name, seed, threshold)
    except JevAuthError as exc:
        yield {"type": "error", "message": str(exc)}
        return

    yield {
        "type": "start",
        "game": game_name,
        "seed": seed,
        "max_turns": max_turns,
        "threshold": threshold,
        "left_name": left_kind,
        "right_name": right_kind,
        "left": _side(left_game),
        "right": _side(right_game),
    }

    for turn in range(max_turns):
        if left_game.game_over and right_game.game_over:
            break
        try:
            left_move = _advance(left_game, left_player)
            right_move = _advance(right_game, right_player)
        except JevError as exc:
            yield {"type": "error", "message": f"TypeSafe call failed: {exc}"}
            return

        yield {
            "type": "frame",
            "turn": turn,
            "left": {**_side(left_game), "last": left_move},
            "right": {**_side(right_game), "last": right_move},
        }

    fallbacks = {}
    for name, player in (("left", left_player), ("right", right_player)):
        if isinstance(player, JevPlayer):
            fallbacks[name] = dict(player.fallback_reasons)

    yield {
        "type": "done",
        "left_score": left_game.score,
        "right_score": right_game.score,
        "left_over": left_game.game_over,
        "right_over": right_game.game_over,
        "fallbacks": fallbacks,
    }
