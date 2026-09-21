"""Gym backed game tests.

Skipped entirely when gymnasium is not installed, because it is an optional
extra and a plain clone must still get a green suite.
"""

import pytest

from jev_arcade.games.base import BANNED_STATE_KEYS
from jev_arcade.games.gym_adapter import GYM_GAMES, gymnasium_available
from jev_arcade.games.registry import CORE_GAMES, GYM_BACKED, available_games, make_game
from jev_arcade.harness.runner import run_episode
from jev_arcade.players.jev_player import QUESTION_TEXT
from jev_arcade.players.random_player import RandomPlayer

needs_gym = pytest.mark.skipif(not gymnasium_available(), reason="gymnasium is not installed")


# ---- registry, no gymnasium required ----------------------------------------


def test_core_games_are_always_available():
    assert set(available_games()) >= set(CORE_GAMES)


def test_every_game_has_jev_question_text():
    """A game with no question text would crash the moment Jev played it."""
    for name in set(CORE_GAMES) | set(GYM_BACKED):
        assert name in QUESTION_TEXT, f"{name} has no question text"


def test_unknown_game_is_rejected_with_a_useful_message():
    with pytest.raises(ValueError, match="unknown game"):
        make_game("pong")


def test_a_gym_game_without_gymnasium_points_at_the_extra():
    if gymnasium_available():
        pytest.skip("gymnasium is installed, so this path cannot be reached")
    with pytest.raises(ValueError, match="gymnasium"):
        make_game("frozenlake")


# ---- the adapter ------------------------------------------------------------


@needs_gym
@pytest.mark.parametrize("name", GYM_BACKED)
def test_every_gym_game_plays_to_completion(name):
    episode = run_episode(make_game(name), RandomPlayer(0), seed=0, max_turns=40)
    assert episode.game == name
    assert episode.turns >= 1


@needs_gym
@pytest.mark.parametrize("name", GYM_BACKED)
def test_moves_are_labels_not_integers(name):
    """Jev is offered readable action names, never raw Gymnasium indices."""
    game = make_game(name)
    game.reset(0)
    for move in game.legal_moves():
        assert isinstance(move, str)
        assert not move.isdigit()


@needs_gym
@pytest.mark.parametrize("name", GYM_BACKED)
def test_state_is_decoded_rather_than_a_bare_index(name):
    """A raw observation integer tells a model nothing. It must be decoded."""
    game = make_game(name)
    game.reset(0)
    state = game.to_state()
    assert "goal" in state
    assert len(state) > 3


@needs_gym
@pytest.mark.parametrize("name", GYM_BACKED)
def test_state_contains_no_hint_fields(name):
    game = make_game(name)
    game.reset(0)
    keys = {k.lower() for k in game.to_state()}
    assert not (keys & BANNED_STATE_KEYS)


@needs_gym
@pytest.mark.parametrize("name", GYM_BACKED)
def test_same_seed_reproduces_the_episode(name):
    a = run_episode(make_game(name), RandomPlayer(1), seed=5, max_turns=25)
    b = run_episode(make_game(name), RandomPlayer(1), seed=5, max_turns=25)
    assert [m.move for m in a.moves] == [m.move for m in b.moves]
    assert a.final_score == b.final_score


@needs_gym
def test_taxi_offers_only_unmasked_actions():
    """Taxi publishes an action_mask, so illegal actions never reach criteria."""
    game = make_game("taxi")
    game.reset(0)
    legal = game.legal_moves()
    assert 0 < len(legal) < len(GYM_GAMES["taxi"].actions)


@needs_gym
def test_illegal_move_is_rejected():
    game = make_game("frozenlake")
    game.reset(0)
    with pytest.raises(ValueError, match="illegal move"):
        game.step("teleport")


@needs_gym
def test_frozenlake_marks_the_player_on_the_grid():
    game = make_game("frozenlake")
    game.reset(0)
    grid = game.to_state()["grid"]
    assert sum(row.count("P") for row in grid) == 1


@needs_gym
def test_a_finished_game_offers_no_moves():
    game = make_game("blackjack")
    game.reset(0)
    while not game.game_over:
        game.step(game.legal_moves()[0])
    assert game.legal_moves() == []
