"""Snake engine tests."""

import pytest

from jev_arcade.games.snake import Snake


def test_same_seed_yields_same_food_sequence():
    a, b = Snake(), Snake()
    a.reset(11)
    b.reset(11)
    assert a.food == b.food
    for _ in range(5):
        a.step("up")
        b.step("up")
    assert a.food == b.food
    assert a.body == b.body


def test_cannot_reverse_into_its_own_neck():
    g = Snake()
    g.reset(0)
    # Starts facing right with the body trailing to the left.
    assert "left" not in g.legal_moves()
    assert set(g.legal_moves()) == {"up", "down", "right"}


def test_eating_food_grows_and_scores():
    g = Snake()
    g.reset(0)
    head_r, head_c = g.body[0]
    g._food = (head_r, head_c + 1)  # directly ahead
    length_before = len(g.body)
    g.step("right")
    assert g.score == 10
    assert len(g.body) == length_before + 1


def test_hitting_a_wall_ends_the_game():
    g = Snake()
    g.reset(0)
    for _ in range(g.size + 2):
        if g.game_over:
            break
        g.step("up")
    assert g.game_over


def test_running_into_its_own_body_ends_the_game():
    g = Snake()
    g.reset(0)
    # Grow long enough to be able to hit itself, then turn in a tight square.
    g._body = [(5, 5), (5, 4), (4, 4), (4, 5), (4, 6)]
    g.step("up")  # moves to (4, 5), which is occupied
    assert g.game_over


def test_starvation_cutoff_ends_a_looping_episode():
    g = Snake()
    g.reset(0)
    g._steps_since_food = g.__class__.__mro__ and 399
    g._food = (0, 0)  # far away, will not be eaten by one step
    g.step("up")
    assert g.game_over


def test_no_legal_moves_once_dead():
    g = Snake()
    g.reset(0)
    g._dead = True
    assert g.legal_moves() == []


def test_step_rejects_illegal_move():
    g = Snake()
    g.reset(0)
    with pytest.raises(ValueError):
        g.step("left")  # reversing into the neck
