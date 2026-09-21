"""Benchmark runner and live viewer.

    python3 -m jev_arcade serve
    python3 -m jev_arcade watch --game tetris --player heuristic
    python3 -m jev_arcade bench --game all --player random,heuristic --episodes 10
    python3 -m jev_arcade bench --game 2048 --player jev --episodes 3 --max-turns 60
"""

from __future__ import annotations

import argparse
import logging
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from jev_arcade.games.snake import Snake
from jev_arcade.games.tetris import Tetris
from jev_arcade.games.twenty48 import Twenty48
from jev_arcade.harness.recorder import write_jsonl
from jev_arcade.harness.render import clear_screen, render
from jev_arcade.harness.runner import run_episode
from jev_arcade.players.heuristic_player import HeuristicPlayer
from jev_arcade.players.jev_client import JevAuthError, JevClient
from jev_arcade.players.jev_player import JevPlayer
from jev_arcade.players.random_player import RandomPlayer
from jev_arcade.types import Episode

__all__ = ["main"]

logger = logging.getLogger("jev_arcade")

GAMES = {"tetris": Tetris, "snake": Snake, "2048": Twenty48}
PLAYERS = ("random", "heuristic", "jev")

# Jev spends one API call per turn, so the cap is a budget as much as a rule.
# 150 turns is roughly a minute and a half of wall clock per episode.
DEFAULT_MAX_TURNS = 150


def load_dotenv(path: str | Path = ".env") -> None:
    """Minimal .env reader. Avoids a dependency for four lines of parsing."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def build_player(kind: str, game_name: str, seed: int, threshold: float) -> Any:
    if kind == "random":
        return RandomPlayer(seed)
    if kind == "heuristic":
        return HeuristicPlayer(game_name)
    if kind == "jev":
        client = JevClient.from_env()
        return JevPlayer(game_name, client, HeuristicPlayer(game_name), threshold)
    raise ValueError(f"unknown player {kind!r}")


def watch(game_name: str, player_kind: str, seed: int, max_turns: int,
          threshold: float, delay: float) -> Episode:
    """Play one episode and draw every frame."""
    game = GAMES[game_name]()
    player = build_player(player_kind, game_name, seed, threshold)

    def on_step(g: Any, record: Any) -> None:
        sys.stdout.write(clear_screen())
        sys.stdout.write(render(g.to_state(), game_name) + "\n")
        confidence = "n/a" if record.confidence is None else f"{record.confidence:.2f}"
        sys.stdout.write(
            f"turn {record.turn}  move {record.move}  by {record.source}  "
            f"confidence {confidence}  {record.latency_ms:.0f} ms\n"
        )
        sys.stdout.flush()
        if delay:
            time.sleep(delay)

    episode = run_episode(game, player, seed, max_turns=max_turns, on_step=on_step)
    print(f"\nfinished: score {episode.final_score} over {episode.turns} turns")
    return episode


def bench(game_names: list[str], player_kinds: list[str], episodes: int,
          max_turns: int, threshold: float, seed_start: int) -> dict[str, list[Episode]]:
    results: dict[str, list[Episode]] = {}
    for game_name in game_names:
        for kind in player_kinds:
            key = f"{game_name}/{kind}"
            runs: list[Episode] = []
            for i in range(episodes):
                seed = seed_start + i
                player = build_player(kind, game_name, seed, threshold)
                meta = {
                    "max_turns": max_turns,
                    "threshold": threshold if kind == "jev" else None,
                }
                episode = run_episode(
                    GAMES[game_name](), player, seed, max_turns=max_turns, meta=meta
                )
                if kind == "jev":
                    episode.meta["fallback_reasons"] = dict(player.fallback_reasons)
                runs.append(episode)
                print(
                    f"  {key} seed {seed}: score {episode.final_score} "
                    f"({episode.turns} turns)",
                    flush=True,
                )
            results[key] = runs
    return results


def results_table(results: dict[str, list[Episode]], max_turns: int) -> str:
    games = sorted({k.split("/")[0] for k in results})
    kinds = [k for k in PLAYERS if any(key.endswith(f"/{k}") for key in results)]

    header = "| game | " + " | ".join(kinds) + " | jev fallback rate |"
    divider = "| --- | " + " | ".join("---" for _ in kinds) + " | --- |"
    lines = [
        f"Mean score over {max_turns} turns per episode.",
        "",
        header,
        divider,
    ]
    for game in games:
        cells = []
        for kind in kinds:
            runs = results.get(f"{game}/{kind}")
            if not runs:
                cells.append("n/a")
            else:
                cells.append(f"{statistics.mean(r.final_score for r in runs):.0f}")
        jev_runs = results.get(f"{game}/jev")
        fallback = (
            "n/a" if not jev_runs
            else f"{statistics.mean(r.fallback_rate for r in jev_runs) * 100:.0f}%"
        )
        lines.append(f"| {game} | " + " | ".join(cells) + f" | {fallback} |")
    return "\n".join(lines)


def confidence_report(results: dict[str, list[Episode]]) -> str:
    """Bucket Jev moves by reported confidence. The calibration view."""
    buckets: dict[str, list[float]] = {"0.0 to 0.5": [], "0.5 to 0.8": [], "0.8 to 1.0": []}
    total = 0
    for key, runs in results.items():
        if not key.endswith("/jev"):
            continue
        for run in runs:
            for move in run.moves:
                if move.source != "jev" or move.confidence is None:
                    continue
                total += 1
                label = (
                    "0.0 to 0.5" if move.confidence < 0.5
                    else "0.5 to 0.8" if move.confidence < 0.8
                    else "0.8 to 1.0"
                )
                buckets[label].append(move.confidence)
    if not total:
        return ""
    lines = [
        "",
        "Jev confidence distribution:",
        "",
        "| bucket | moves | share |",
        "| --- | --- | --- |",
    ]
    for label, values in buckets.items():
        lines.append(f"| {label} | {len(values)} | {len(values) / total * 100:.0f}% |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="jev_arcade", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--game", default="tetris", help="tetris, snake, 2048 or all")
    common.add_argument("--player", default="heuristic", help="random, heuristic, jev or all")
    common.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    common.add_argument("--threshold", type=float, default=0.0,
                        help="confidence below this falls back to the heuristic")

    w = sub.add_parser("watch", parents=[common], help="play one episode and draw it")
    w.add_argument("--seed", type=int, default=0)
    w.add_argument("--delay", type=float, default=0.05)

    a = sub.add_parser("analyse", help="calibration report over recorded replays")
    a.add_argument("--replays", default="replays")

    s = sub.add_parser("serve", help="local web viewer, jev against a baseline side by side")
    s.add_argument("--host", default="127.0.0.1",
                   help="stays on this machine by default; this process holds your API key")
    s.add_argument("--port", type=int, default=8765)

    b = sub.add_parser("bench", parents=[common], help="run many episodes and tabulate")
    b.add_argument("--episodes", type=int, default=5)
    b.add_argument("--seed-start", type=int, default=0)
    b.add_argument("--out", default="results")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    if args.command == "serve":
        from jev_arcade.web.server import serve

        serve(args.host, args.port)
        return 0

    if args.command == "analyse":
        from jev_arcade.analysis import analyse_replays, format_report

        print(format_report(analyse_replays(args.replays)))
        return 0

    game_names = list(GAMES) if args.game == "all" else args.game.split(",")
    for name in game_names:
        if name not in GAMES:
            parser.error(f"unknown game {name!r}. Choose from {', '.join(GAMES)} or all.")

    try:
        if args.command == "watch":
            watch(game_names[0], args.player, args.seed, args.max_turns,
                  args.threshold, args.delay)
            return 0

        kinds = list(PLAYERS) if args.player == "all" else args.player.split(",")
        for kind in kinds:
            if kind not in PLAYERS:
                parser.error(f"unknown player {kind!r}. Choose from {', '.join(PLAYERS)} or all.")

        started = time.time()
        results = bench(game_names, kinds, args.episodes, args.max_turns,
                        args.threshold, args.seed_start)
        table = results_table(results, args.max_turns) + confidence_report(results)
        print("\n" + table)

        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        (out_dir / f"results_{stamp}.md").write_text(table + "\n", encoding="utf-8")
        for key, runs in results.items():
            safe = key.replace("/", "_")
            write_jsonl(Path("replays") / f"{safe}_{stamp}.jsonl", runs)
        print(f"\nwrote results to {out_dir}/results_{stamp}.md "
              f"and replays to replays/ in {time.time() - started:.1f}s")
        return 0
    except JevAuthError as exc:
        print(f"\nauth error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
