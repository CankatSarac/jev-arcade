"""Calibration analysis over recorded replays.

The question this answers: does Jev's reported confidence carry signal about
whether its move was any good?

No API calls are needed. A replay stores the seed and the move sequence, and
the games are deterministic, so every episode can be re-simulated exactly. At
each turn that reconstructs the board Jev actually saw, which is enough to ask
two things of every move it made.

**Agreement.** What would the heuristic have chosen from the same position?
The heuristic is not ground truth, but it is the strongest reference available
and it sees exactly the same serialized state.

**Consequence.** For Tetris, how many holes did the move create and how much
did the stack rise? This needs no reference player at all, which makes it the
stronger of the two measures.

If confidence is informative, both should improve as confidence rises.
"""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import Any

from jev_arcade.games.snake import Snake
from jev_arcade.games.tetris import Tetris
from jev_arcade.games.twenty48 import Twenty48
from jev_arcade.harness.recorder import read_jsonl
from jev_arcade.players.heuristic_player import HeuristicPlayer
from jev_arcade.types import Episode

__all__ = ["analyse_replays", "collect_moves", "format_report", "BUCKETS"]

GAMES = {"tetris": Tetris, "snake": Snake, "2048": Twenty48}

# Chosen to match the distribution reported by bench, not tuned after the fact.
BUCKETS: list[tuple[str, float, float]] = [
    ("0.0 to 0.3", 0.0, 0.3),
    ("0.3 to 0.5", 0.3, 0.5),
    ("0.5 to 0.8", 0.5, 0.8),
    ("0.8 to 1.0", 0.8, 1.0001),
]


def collect_moves(episode: Episode) -> list[dict[str, Any]]:
    """Re-simulate one episode and describe every real decision Jev made.

    Two kinds of turn are skipped. Fallback moves were played by the heuristic,
    so scoring them against the heuristic would compare it with itself. Turns
    with a single legal move were never sent to the API at all.
    """
    if episode.game not in GAMES:
        return []
    game = GAMES[episode.game]()
    game.reset(episode.seed)
    reference = HeuristicPlayer(episode.game)
    rows: list[dict[str, Any]] = []

    for record in episode.moves:
        if game.game_over:
            break
        legal = game.legal_moves()
        if record.move not in legal:
            break  # replay and engine disagree, stop rather than guess
        state_before = game.to_state()

        # A position with one legal move is not a decision. JevPlayer plays it
        # without sending a request and reports confidence 1.0, which would
        # otherwise stack the top bucket with forced moves.
        if record.source == "jev" and record.confidence is not None and len(legal) > 1:
            choice = reference.choose(state_before, legal, game.move_descriptions())
            game.step(record.move)
            state_after = game.to_state()
            rows.append(
                {
                    "game": episode.game,
                    "confidence": record.confidence,
                    "agrees": record.move == choice.move,
                    "holes_created": (
                        state_after.get("holes", 0) - state_before.get("holes", 0)
                        if episode.game == "tetris"
                        else None
                    ),
                    "height_delta": (
                        max(state_after["column_heights"]) - max(state_before["column_heights"])
                        if episode.game == "tetris"
                        else None
                    ),
                    "options": len(legal),
                }
            )
        else:
            game.step(record.move)
    return rows


def analyse_replays(directory: str | Path = "replays") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(Path(directory).glob("*.jsonl")):
        for episode in read_jsonl(path):
            if episode.player == "jev":
                rows.extend(collect_moves(episode))
    return rows


def _bucket_of(confidence: float) -> str:
    for label, low, high in BUCKETS:
        if low <= confidence < high:
            return label
    return BUCKETS[-1][0]


def format_report(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No Jev moves found in replays. Run a bench with --player jev first."

    lines: list[str] = []
    games = sorted({r["game"] for r in rows})

    lines.append("## Agreement with the heuristic, by Jev confidence")
    lines.append("")
    lines.append("Share of Jev moves that matched what the heuristic chose from the same board.")
    lines.append("Random agreement is one over the number of legal options, shown for comparison.")
    lines.append("")
    lines.append("| game | bucket | moves | agrees | chance |")
    lines.append("| --- | --- | --- | --- | --- |")
    for game in games:
        game_rows = [r for r in rows if r["game"] == game]
        for label, _, _ in BUCKETS:
            bucket = [r for r in game_rows if _bucket_of(r["confidence"]) == label]
            if not bucket:
                continue
            agree = sum(1 for r in bucket if r["agrees"]) / len(bucket)
            chance = statistics.mean(1 / r["options"] for r in bucket)
            lines.append(
                f"| {game} | {label} | {len(bucket)} | {agree * 100:.0f}% | {chance * 100:.0f}% |"
            )

    tetris = [r for r in rows if r["game"] == "tetris"]
    if tetris:
        lines.append("")
        lines.append("## Consequence of the move, Tetris only")
        lines.append("")
        lines.append("Holes created and stack rise caused by each move. Lower is better on both.")
        lines.append("This needs no reference player, so it is the stronger measure.")
        lines.append("")
        lines.append("| bucket | moves | mean holes created | mean stack rise |")
        lines.append("| --- | --- | --- | --- |")
        for label, _, _ in BUCKETS:
            bucket = [r for r in tetris if _bucket_of(r["confidence"]) == label]
            if not bucket:
                continue
            holes = statistics.mean(r["holes_created"] for r in bucket)
            rise = statistics.mean(r["height_delta"] for r in bucket)
            lines.append(f"| {label} | {len(bucket)} | {holes:+.2f} | {rise:+.2f} |")

    return "\n".join(lines)
