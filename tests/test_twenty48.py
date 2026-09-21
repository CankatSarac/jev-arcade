"""2048 engine tests, focused on the merge rule that is easy to get wrong."""

import pytest

from jev_arcade.games.twenty48 import Twenty48, _compress


def test_compress_merges_each_pair_once():
    assert _compress([2, 2, 4, 4]) == ([4, 8, 0, 0], 12)


def test_compress_does_not_chain_merge():
    # [4,4,4,4] must give [8,8], never [16]. A tile merges at most once a move.
    assert _compress([4, 4, 4, 4]) == ([8, 8, 0, 0], 16)


def test_compress_slides_without_merging_unequal_tiles():
    assert _compress([0, 2, 0, 4]) == ([2, 4, 0, 0], 0)


def test_compress_leaves_a_settled_row_alone():
    assert _compress([8, 4, 2, 0]) == ([8, 4, 2, 0], 0)


def test_same_seed_yields_same_board():
    a, b = Twenty48(), Twenty48()
    a.reset(5)
    b.reset(5)
    assert a.grid == b.grid
    for _ in range(10):
        if a.game_over:
            break
        move = a.legal_moves()[0]
        a.step(move)
        b.step(move)
    assert a.grid == b.grid
    assert a.score == b.score


def test_a_move_that_changes_nothing_is_illegal():
    g = Twenty48()
    g.reset(0)
    g._grid = [
        [2, 4, 8, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ]
    # Already packed left against the top with no equal neighbours, so left and
    # up both do nothing. Right and down still slide the tiles.
    assert "left" not in g.legal_moves()
    assert "up" not in g.legal_moves()
    assert "right" in g.legal_moves()
    assert "down" in g.legal_moves()


def test_score_increases_by_the_merged_value():
    g = Twenty48()
    g.reset(0)
    g._grid = [
        [2, 2, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ]
    g._score = 0
    g.step("left")
    assert g.score == 4


def test_game_over_on_a_gridlocked_board():
    g = Twenty48()
    g.reset(0)
    g._grid = [
        [2, 4, 8, 16],
        [4, 8, 16, 32],
        [8, 16, 32, 64],
        [16, 32, 64, 128],
    ]
    assert g.game_over
    assert g.legal_moves() == []


def test_step_rejects_illegal_move():
    g = Twenty48()
    g.reset(0)
    g._grid = [[2, 4, 8, 16], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
    with pytest.raises(ValueError):
        g.step("left")


def test_grid_property_is_a_copy():
    g = Twenty48()
    g.reset(0)
    snapshot = g.grid
    snapshot[0][0] = 999
    assert g.grid[0][0] != 999
