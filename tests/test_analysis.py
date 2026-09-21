"""Analysis tests, with attention to the two exclusions that keep it honest."""

from jev_arcade.analysis import BUCKETS, analyse_replays, collect_moves, format_report
from jev_arcade.games.snake import Snake
from jev_arcade.games.tetris import Tetris
from jev_arcade.harness.recorder import write_jsonl
from jev_arcade.harness.runner import run_episode
from jev_arcade.players.heuristic_player import HeuristicPlayer
from jev_arcade.types import Episode, MoveRecord


def scripted_episode(game_name, factory, sources_and_confidence):
    """Build a replay by playing the heuristic and relabelling each move."""
    base = run_episode(factory(), HeuristicPlayer(game_name), seed=0,
                       max_turns=len(sources_and_confidence))
    moves = [
        MoveRecord(i, rec.move, src, conf, rec.score_after)
        for i, (rec, (src, conf)) in enumerate(
            # An episode can end before the script does, so the shorter one wins.
            zip(base.moves, sources_and_confidence, strict=False)
        )
    ]
    return Episode(game_name, "jev", 0, base.final_score, len(moves), moves)


def test_fallback_moves_are_excluded():
    episode = scripted_episode("snake", Snake, [("jev", 0.9), ("heuristic", None), ("jev", 0.9)])
    rows = collect_moves(episode)
    assert len(rows) == 2, "heuristic fallback moves must not be scored against the heuristic"


def test_a_buried_well_is_unreachable():
    """Pieces spawn at the top, so a well with filled cells above it is dead.

    This is why holes are the most punished term in the Tetris heuristic.
    """
    game = Tetris()
    game.reset(0)
    game._board = [[1] * 10 for _ in range(20)]
    for r in range(16, 20):
        game._board[r][0] = 0  # a 4 deep well, but covered by rows 0 to 15
    game._current = "I"
    assert game.legal_moves() == []


def test_a_single_open_column_leaves_exactly_one_placement():
    game = Tetris()
    game.reset(0)
    game._board = [[1] * 10 for _ in range(20)]
    for r in range(20):
        game._board[r][0] = 0  # column 0 open from the very top
    game._current = "I"
    # Only the vertical I fits. The horizontal one needs four free columns.
    assert game.legal_moves() == ["r1c0"]


def test_every_kept_row_had_a_real_choice():
    episode = scripted_episode("tetris", Tetris, [("jev", 0.5)] * 12)
    for row in collect_moves(episode):
        assert row["options"] > 1
        assert 0.0 <= row["confidence"] <= 1.0


def test_agreement_is_true_when_jev_matched_the_heuristic():
    # Every move in this replay came from the heuristic, relabelled as Jev, so
    # agreement must be total.
    episode = scripted_episode("snake", Snake, [("jev", 0.9)] * 10)
    rows = collect_moves(episode)
    assert rows
    assert all(r["agrees"] for r in rows)


def test_tetris_rows_carry_consequence_measures():
    episode = scripted_episode("tetris", Tetris, [("jev", 0.4)] * 10)
    rows = collect_moves(episode)
    assert rows
    assert all(r["holes_created"] is not None for r in rows)
    assert all(r["height_delta"] is not None for r in rows)


def test_non_tetris_rows_have_no_consequence_measures():
    episode = scripted_episode("snake", Snake, [("jev", 0.4)] * 6)
    assert all(r["holes_created"] is None for r in collect_moves(episode))


def test_buckets_cover_the_whole_range_without_gaps():
    lows = [low for _, low, _ in BUCKETS]
    highs = [high for _, _, high in BUCKETS]
    assert lows[0] == 0.0
    assert highs[-1] > 1.0
    for i in range(len(BUCKETS) - 1):
        assert highs[i] == lows[i + 1]


def test_report_reads_replays_from_disk(tmp_path):
    episode = scripted_episode("snake", Snake, [("jev", 0.9)] * 8)
    write_jsonl(tmp_path / "snake_jev.jsonl", [episode])
    rows = analyse_replays(tmp_path)
    assert rows
    report = format_report(rows)
    assert "Agreement with the heuristic" in report
    assert "chance" in report


def test_report_says_so_when_there_is_nothing_to_analyse(tmp_path):
    assert "No Jev moves found" in format_report(analyse_replays(tmp_path))


def test_non_jev_episodes_are_ignored(tmp_path):
    episode = run_episode(Snake(), HeuristicPlayer("snake"), seed=0, max_turns=5)
    write_jsonl(tmp_path / "snake_heuristic.jsonl", [episode])
    assert analyse_replays(tmp_path) == []
