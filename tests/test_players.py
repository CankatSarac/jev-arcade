"""Player tests that need no network."""

import pytest

from jev_arcade.games.snake import Snake
from jev_arcade.games.tetris import Tetris
from jev_arcade.games.twenty48 import Twenty48
from jev_arcade.harness.runner import run_episode
from jev_arcade.players.heuristic_player import HeuristicPlayer
from jev_arcade.players.mock_player import MockPlayer
from jev_arcade.players.random_player import RandomPlayer

GAMES = [(Tetris, "tetris"), (Snake, "snake"), (Twenty48, "2048")]


@pytest.mark.parametrize("factory,name", GAMES)
def test_players_only_ever_return_a_legal_move(factory, name):
    for player in (RandomPlayer(0), HeuristicPlayer(name), MockPlayer([])):
        game = factory()
        game.reset(2)
        for _ in range(30):
            if game.game_over:
                break
            legal = game.legal_moves()
            decision = player.choose(game.to_state(), legal, game.move_descriptions())
            assert decision.move in legal
            game.step(decision.move)


def test_random_player_is_seeded():
    a = run_episode(Twenty48(), RandomPlayer(5), seed=0, max_turns=25)
    b = run_episode(Twenty48(), RandomPlayer(5), seed=0, max_turns=25)
    assert [m.move for m in a.moves] == [m.move for m in b.moves]


@pytest.mark.parametrize("factory,name", GAMES)
def test_heuristic_beats_random_on_the_same_seeds(factory, name):
    seeds = range(4)
    random_total = sum(
        run_episode(factory(), RandomPlayer(s), seed=s, max_turns=150).final_score for s in seeds
    )
    heuristic_total = sum(
        run_episode(factory(), HeuristicPlayer(name), seed=s, max_turns=150).final_score
        for s in seeds
    )
    assert heuristic_total > random_total, f"{name}: {heuristic_total} vs {random_total}"


def test_heuristic_rejects_an_unknown_game():
    with pytest.raises(ValueError):
        HeuristicPlayer("pong")


def test_mock_player_falls_through_to_a_legal_move_when_the_script_runs_out():
    game = Tetris()
    game.reset(0)
    player = MockPlayer(["r9c9"])  # not legal, must be skipped
    decision = player.choose(game.to_state(), game.legal_moves(), game.move_descriptions())
    assert decision.move in game.legal_moves()
