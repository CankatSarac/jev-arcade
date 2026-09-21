"""Tetris engine tests. No network, no randomness beyond the seed."""

import pytest

from jev_arcade.games.tetris import ROTATIONS, Tetris


def test_rotation_counts_are_geometrically_correct():
    # O is symmetric, I S and Z repeat after 180 degrees, the rest have four.
    assert len(ROTATIONS["O"]) == 1
    assert len(ROTATIONS["I"]) == len(ROTATIONS["S"]) == len(ROTATIONS["Z"]) == 2
    assert len(ROTATIONS["T"]) == len(ROTATIONS["J"]) == len(ROTATIONS["L"]) == 4


def test_every_rotation_has_four_cells():
    for name, rots in ROTATIONS.items():
        for cells in rots:
            assert len(set(cells)) == 4, name


def test_same_seed_yields_same_episode():
    def run(seed):
        g = Tetris()
        g.reset(seed)
        out = []
        for _ in range(30):
            if g.game_over:
                break
            move = g.legal_moves()[0]
            g.step(move)
            out.append((move, g.score))
        return out

    assert run(7) == run(7)
    assert run(7) != run(8)


def test_different_seeds_diverge():
    a, b = Tetris(), Tetris()
    a.reset(1)
    b.reset(2)
    # The seven piece bag makes the opening sequence differ across seeds.
    seq_a = [a.current_piece]
    seq_b = [b.current_piece]
    for _ in range(10):
        a.step(a.legal_moves()[0])
        b.step(b.legal_moves()[0])
        seq_a.append(a.current_piece)
        seq_b.append(b.current_piece)
    assert seq_a != seq_b


def test_step_rejects_illegal_move():
    g = Tetris()
    g.reset(0)
    with pytest.raises(ValueError):
        g.step("r9c9")


def test_all_legal_moves_are_actually_playable():
    g = Tetris()
    g.reset(3)
    for move in g.legal_moves():
        clone = Tetris()
        clone.reset(3)
        clone.step(move)  # must not raise


def test_single_line_clear_scores_100():
    g = Tetris()
    g.reset(0)
    # Fill the bottom row except one cell, then drop a single cell into it.
    g._board[19] = [1] * 10
    g._board[19][4] = 0
    g._current = "I"
    g._board[18] = [1] * 10
    g._board[18][4] = 0
    before = g.score
    # A vertical I in column 4 fills both gaps and clears two rows.
    g.step("r1c4")
    assert g.score - before == 300  # two lines


def test_tetris_four_lines_scores_800():
    g = Tetris()
    g.reset(0)
    for r in range(16, 20):
        g._board[r] = [1] * 10
        g._board[r][0] = 0
    g._current = "I"
    g.step("r1c0")
    assert g.score == 800
    assert g.to_state()["lines_cleared"] == 4


def test_holes_counted_under_an_overhang():
    g = Tetris()
    g.reset(0)
    assert g._holes() == 0
    g._board[10][3] = 1  # a block with empty space beneath it
    assert g._holes() == 9


def test_column_heights_measure_from_the_floor():
    g = Tetris()
    g.reset(0)
    g._board[19][0] = 1  # bottom row, height 1
    g._board[15][1] = 1  # five rows up, height 5
    heights = g._column_heights()
    assert heights[0] == 1
    assert heights[1] == 5
    assert heights[2] == 0


def test_game_over_when_board_is_full():
    g = Tetris()
    g.reset(0)
    g._board = [[1] * 10 for _ in range(20)]
    assert g.game_over
    assert g.legal_moves() == []


def test_board_property_is_a_copy():
    g = Tetris()
    g.reset(0)
    snapshot = g.board
    snapshot[0][0] = 9
    assert g.board[0][0] == 0
