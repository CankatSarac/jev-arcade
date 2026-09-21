"""Harness tests, driven entirely by MockPlayer."""

import pytest

from jev_arcade.games.snake import Snake
from jev_arcade.games.tetris import Tetris
from jev_arcade.games.twenty48 import Twenty48
from jev_arcade.harness.recorder import read_jsonl, write_jsonl
from jev_arcade.harness.render import render
from jev_arcade.harness.runner import run_episode
from jev_arcade.players.mock_player import MockPlayer
from jev_arcade.players.random_player import RandomPlayer
from jev_arcade.types import Decision

GAMES = [(Tetris, "tetris"), (Snake, "snake"), (Twenty48, "2048")]


@pytest.mark.parametrize("factory,name", GAMES)
def test_episode_terminates_and_records_every_turn(factory, name):
    episode = run_episode(factory(), RandomPlayer(0), seed=1, max_turns=50)
    assert episode.game == name
    assert episode.turns == len(episode.moves)
    assert episode.turns <= 50
    assert all(m.turn == i for i, m in enumerate(episode.moves))


def test_turn_cap_is_respected():
    episode = run_episode(Tetris(), RandomPlayer(0), seed=1, max_turns=7)
    assert episode.turns == 7


def test_same_seed_and_player_reproduce_the_episode():
    a = run_episode(Tetris(), RandomPlayer(3), seed=9, max_turns=40)
    b = run_episode(Tetris(), RandomPlayer(3), seed=9, max_turns=40)
    assert a.final_score == b.final_score
    assert [m.move for m in a.moves] == [m.move for m in b.moves]


def test_an_illegal_move_from_a_player_is_an_error():
    class Cheater:
        name = "cheater"

        def choose(self, state, legal_moves, descriptions):
            return Decision(move="r9c9", source="mock")

    with pytest.raises(ValueError, match="illegal move"):
        run_episode(Tetris(), Cheater(), seed=0)


def test_mock_player_follows_its_script():
    game = Tetris()
    game.reset(0)
    scripted = game.legal_moves()[:3]
    episode = run_episode(Tetris(), MockPlayer(scripted), seed=0, max_turns=3)
    assert [m.move for m in episode.moves] == scripted


def test_replays_round_trip_through_jsonl(tmp_path):
    episodes = [run_episode(Twenty48(), RandomPlayer(i), seed=i, max_turns=20) for i in range(3)]
    path = write_jsonl(tmp_path / "r.jsonl", episodes)
    loaded = read_jsonl(path)
    assert [e.final_score for e in loaded] == [e.final_score for e in episodes]
    assert [m.move for m in loaded[0].moves] == [m.move for m in episodes[0].moves]


@pytest.mark.parametrize("factory,name", GAMES)
def test_render_produces_output_for_every_game(factory, name):
    game = factory()
    game.reset(0)
    assert len(render(game.to_state(), name)) > 0


def test_fallback_rate_counts_non_primary_sources():
    from jev_arcade.types import Episode, MoveRecord

    moves = [
        MoveRecord(0, "a", "jev", 0.9, 1),
        MoveRecord(1, "b", "heuristic", None, 2),
        MoveRecord(2, "c", "jev", 0.8, 3),
        MoveRecord(3, "d", "heuristic", None, 4),
    ]
    episode = Episode("tetris", "jev", 0, 4, 4, moves)
    assert episode.fallback_rate == 0.5
