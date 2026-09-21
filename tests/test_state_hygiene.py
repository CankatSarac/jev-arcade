"""The guard against the mistake made during the spike.

That first live probe put a `note` field in the state naming the correct
column. Jev answered with confidence 0.99, which proved the transport worked
and measured nothing at all. These tests make that class of error a test
failure rather than a footnote.
"""

import pytest

from jev_arcade.games.base import BANNED_STATE_KEYS
from jev_arcade.games.snake import Snake
from jev_arcade.games.tetris import Tetris
from jev_arcade.games.twenty48 import Twenty48

GAMES = [Tetris, Snake, Twenty48]


def walk_keys(value, prefix=""):
    if isinstance(value, dict):
        for k, v in value.items():
            yield f"{prefix}{k}"
            yield from walk_keys(v, f"{prefix}{k}.")
    elif isinstance(value, list):
        for item in value:
            yield from walk_keys(item, prefix)


@pytest.mark.parametrize("factory", GAMES)
def test_state_contains_no_hint_fields(factory):
    game = factory()
    game.reset(0)
    for _ in range(5):
        if game.game_over:
            break
        keys = {k.split(".")[-1].lower() for k in walk_keys(game.to_state())}
        leaked = keys & BANNED_STATE_KEYS
        assert not leaked, f"{game.name} state leaks hint fields: {leaked}"
        game.step(game.legal_moves()[0])


@pytest.mark.parametrize("factory", GAMES)
def test_state_is_json_serialisable(factory):
    import json

    game = factory()
    game.reset(0)
    json.dumps(game.to_state())


@pytest.mark.parametrize("factory", GAMES)
def test_move_descriptions_do_not_evaluate_moves(factory):
    """Labels may say where a move goes. They may not say whether it is good."""
    evaluative = {"best", "worst", "good", "bad", "optimal", "recommended", "avoid"}
    game = factory()
    game.reset(0)
    for label in game.move_descriptions().values():
        words = set(label.lower().replace(",", " ").split())
        assert not (words & evaluative), f"evaluative label: {label!r}"
