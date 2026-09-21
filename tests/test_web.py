"""Web viewer tests. No API key and no outbound network.

Every race here uses heuristic and random players, so the suite stays offline.
"""

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from jev_arcade.games.registry import CORE_GAMES
from jev_arcade.web.race import race_frames
from jev_arcade.web.server import MAX_TURNS_LIMIT, RaceHandler


@pytest.fixture
def server():
    """A viewer bound to an ephemeral loopback port, torn down after the test."""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), RaceHandler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def get(base, path):
    with urllib.request.urlopen(base + path, timeout=10) as r:
        return r.status, r.read().decode("utf-8")


def status_of(base, path):
    try:
        with urllib.request.urlopen(base + path, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as exc:
        return exc.code


# ---- race generator ---------------------------------------------------------


def test_both_sides_start_from_an_identical_board():
    """The comparison is only fair if the seed gives both players the same game."""
    frames = list(race_frames("tetris", "heuristic", "random", seed=7, max_turns=1))
    start = frames[0]
    assert start["type"] == "start"
    assert start["left"]["state"] == start["right"]["state"]


def test_frames_run_start_then_turns_then_done():
    frames = list(race_frames("snake", "heuristic", "random", seed=1, max_turns=5))
    assert frames[0]["type"] == "start"
    assert frames[-1]["type"] == "done"
    turns = [f for f in frames if f["type"] == "frame"]
    assert 1 <= len(turns) <= 5
    assert [f["turn"] for f in turns] == list(range(len(turns)))


def test_each_frame_reports_the_move_that_was_played():
    for frame in race_frames("2048", "heuristic", "random", seed=3, max_turns=4):
        if frame["type"] == "frame":
            for side in ("left", "right"):
                last = frame[side]["last"]
                assert last.get("over") or last.get("move")


def test_a_side_that_dies_stops_while_the_other_plays_on():
    frames = list(race_frames("tetris", "random", "heuristic", seed=2, max_turns=60))
    done = frames[-1]
    assert done["type"] == "done"
    # Random reliably tops out well before the heuristic does.
    assert done["left_over"] or done["right_score"] >= done["left_score"]


def test_unknown_game_is_rejected():
    with pytest.raises(ValueError, match="unknown game"):
        list(race_frames("pong", "heuristic", "random"))


def test_unknown_player_is_rejected():
    with pytest.raises(ValueError, match="unknown player"):
        list(race_frames("snake", "heuristic", "cheater"))


# ---- HTTP layer -------------------------------------------------------------


def test_page_is_served(server):
    status, body = get(server, "/")
    assert status == 200
    assert "jev-arcade" in body
    assert "EventSource" in body


def test_config_lists_games_and_players(server):
    _, body = get(server, "/api/config")
    config = json.loads(body)
    # Core games are always present. Gym backed ones appear only when
    # gymnasium is installed, so the check is a superset rather than equality.
    assert set(config["games"]) >= set(CORE_GAMES)
    assert set(config["players"]) == {"jev", "heuristic", "random"}
    assert config["max_turns_limit"] == MAX_TURNS_LIMIT


def test_config_reports_key_presence_without_revealing_it(server, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "apikey_secret_value_here")
    _, body = get(server, "/api/config")
    assert "apikey_secret_value_here" not in body
    assert json.loads(body)["jev_available"] is True


def test_page_never_contains_a_key(server, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "apikey_secret_value_here")
    _, body = get(server, "/")
    assert "apikey" not in body.lower()


@pytest.mark.parametrize(
    "path",
    [
        "/api/race?game=../../etc/passwd",
        "/api/race?game=tetris&left=evil",
        "/api/race?game=tetris&right=evil",
    ],
)
def test_bad_parameters_are_rejected(server, path):
    assert status_of(server, path) == 400


def test_unknown_route_is_404(server):
    assert status_of(server, "/nope") == 404


def test_race_streams_server_sent_events(server):
    url = f"{server}/api/race?game=snake&left=heuristic&right=random&seed=0&max_turns=3"
    with urllib.request.urlopen(url, timeout=30) as response:
        assert response.headers["Content-Type"] == "text/event-stream"
        payloads = [
            json.loads(line.decode()[6:])
            for line in response
            if line.startswith(b"data: ")
        ]
    assert payloads[0]["type"] == "start"
    assert payloads[-1]["type"] == "done"


def test_max_turns_is_clamped_to_the_limit(server):
    """A crafted URL must not be able to start an unbounded, API spending run."""
    url = f"{server}/api/race?game=snake&left=random&right=random&seed=0&max_turns=999999"
    with urllib.request.urlopen(url, timeout=60) as response:
        first = json.loads(next(line for line in response if line.startswith(b"data: "))[6:])
    assert first["max_turns"] == MAX_TURNS_LIMIT


def test_threshold_is_clamped_to_zero_and_one(server):
    url = f"{server}/api/race?game=snake&left=random&right=random&max_turns=1&threshold=99"
    with urllib.request.urlopen(url, timeout=30) as response:
        first = json.loads(next(line for line in response if line.startswith(b"data: "))[6:])
    assert first["threshold"] == 1.0


def test_page_does_not_hardcode_the_game_list(server):
    """The dropdown must come from /api/config.

    It was hardcoded to the three core games at first, so the gym backed ones
    could never appear in the browser no matter what the server registered.
    """
    _, body = get(server, "/")
    assert '<select id="game"></select>' in body
    assert "/api/config" in body
    for name in ("tetris", "snake", "2048"):
        assert f'<option value="{name}">' not in body


def test_page_can_render_every_registered_game(server):
    """Each game needs either a glyph map, a tile view or a fact view.

    A game the page cannot draw would show an empty box with no error.
    """
    _, body = get(server, "/")
    _, config = get(server, "/api/config")
    drawable = {"tetris", "snake", "2048"}  # bespoke renderers
    for name in json.loads(config)["games"]:
        assert (
            name in drawable
            or f"  {name}: {{" in body  # entry in GLYPHS
            or f"  {name}: s =>" in body  # entry in FACTS
        ), f"the page has no way to draw {name}"
