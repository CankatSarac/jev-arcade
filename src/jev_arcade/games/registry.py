"""One place that knows which games exist.

Before this the game list was duplicated in bench.py, web/race.py and
analysis.py, which is three places to forget. Adding an environment now means
touching this file and the question text, nothing else.

Gym backed games appear only when gymnasium is installed. The core package
stays standard library only, so a plain clone still runs the three hand
written engines with no install step at all.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from jev_arcade.games.snake import Snake
from jev_arcade.games.tetris import Tetris
from jev_arcade.games.twenty48 import Twenty48

__all__ = ["CORE_GAMES", "GYM_BACKED", "available_games", "make_game", "is_gym_game"]

CORE_GAMES: dict[str, Callable[[], Any]] = {
    "tetris": Tetris,
    "snake": Snake,
    "2048": Twenty48,
}

GYM_BACKED = ("frozenlake", "cliffwalking", "taxi", "blackjack")


def is_gym_game(name: str) -> bool:
    return name in GYM_BACKED


def available_games() -> dict[str, Callable[[], Any]]:
    """Core games always, plus the gym backed ones when gymnasium is present."""
    from jev_arcade.games.gym_adapter import GymGame, gymnasium_available

    games = dict(CORE_GAMES)
    if gymnasium_available():
        for name in GYM_BACKED:
            games[name] = (lambda n=name: GymGame(n))  # bind the name per entry
    return games


def make_game(name: str) -> Any:
    games = available_games()
    if name not in games:
        if is_gym_game(name):
            from jev_arcade.games.gym_adapter import INSTALL_HINT

            raise ValueError(f"{name} needs gymnasium. {INSTALL_HINT}")
        raise ValueError(f"unknown game {name!r}. Choose from {', '.join(games)}")
    return games[name]()
