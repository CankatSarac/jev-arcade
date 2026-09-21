"""JevPlayer and JevClient tests. Nothing here opens a socket."""

import pytest
from fakes import always_http_error, http_error, ok

from jev_arcade.games.tetris import Tetris
from jev_arcade.players.heuristic_player import HeuristicPlayer
from jev_arcade.players.jev_client import JevAuthError, JevClient, JevError, JevTransportError
from jev_arcade.players.jev_player import MAX_CHOICE_OPTIONS, JevPlayer


def make(opener, threshold=0.0):
    game = Tetris()
    game.reset(0)
    client = JevClient(api_key="test-key", max_retries=3, opener=opener)
    player = JevPlayer("tetris", client, HeuristicPlayer("tetris"), threshold)
    return game, player


def choice_answer(move, confidence=0.9):
    return {
        "move": {"type": "choice", "choice": move, "confidence": confidence,
                 "probabilities": {move: confidence}},
        "danger": {"type": "noul", "noul": 0.1},
        "health": {"type": "score", "score": 0.4, "confidence": 0.8},
    }


def test_request_carries_state_model_and_three_questions():
    game, player = make(ok(choice_answer("r0c0")))
    legal = game.legal_moves()
    player.choose(game.to_state(), legal, game.move_descriptions())
    sent = player._client._opener.calls[0]
    assert sent["model"] == "jev-latest"
    assert set(sent["questions"]) == {"move", "danger", "health"}
    assert sent["questions"]["move"]["type"] == "choice"
    assert sent["questions"]["danger"]["type"] == "noul"
    assert sent["questions"]["health"]["type"] == "score"
    assert "board" in sent["state"]


def test_choice_criteria_cover_every_legal_move():
    game, player = make(ok(choice_answer("r0c0")))
    legal = game.legal_moves()
    questions = player.build_questions(legal, game.move_descriptions())
    assert set(questions["move"]["criteria"]) == set(legal)
    assert len(legal) <= MAX_CHOICE_OPTIONS


def test_accepts_a_confident_answer():
    game, player = make(ok(choice_answer("r0c3", confidence=0.95)))
    decision = player.choose(game.to_state(), game.legal_moves(), game.move_descriptions())
    assert decision.move == "r0c3"
    assert decision.source == "jev"
    assert decision.confidence == 0.95


def test_low_confidence_falls_back_to_the_heuristic():
    game, player = make(ok(choice_answer("r0c3", confidence=0.10)), threshold=0.5)
    decision = player.choose(game.to_state(), game.legal_moves(), game.move_descriptions())
    assert decision.source == "heuristic"
    assert decision.raw["fallback_reason"] == "low_confidence"
    assert player.fallback_reasons["low_confidence"] == 1


def test_an_answer_outside_the_legal_set_falls_back():
    game, player = make(ok(choice_answer("r9c9")))
    legal = game.legal_moves()
    decision = player.choose(game.to_state(), legal, game.move_descriptions())
    assert decision.source == "heuristic"
    assert decision.raw["fallback_reason"] == "illegal_answer"
    assert decision.move in legal


def test_a_single_legal_move_is_played_without_a_request():
    game, player = make(ok(choice_answer("r0c0")))
    decision = player.choose(game.to_state(), ["r0c0"], {"r0c0": "only option"})
    assert decision.move == "r0c0"
    assert player._client._opener.calls == []


def test_transport_failure_falls_back_rather_than_crashing():
    game, player = make(always_http_error(529))
    player._client.max_retries = 1
    decision = player.choose(game.to_state(), game.legal_moves(), game.move_descriptions())
    assert decision.source == "heuristic"
    assert decision.raw["fallback_reason"] == "transport_error"


def test_a_rejected_key_raises_and_is_never_retried():
    game, player = make(always_http_error(401))
    with pytest.raises(JevAuthError):
        player.choose(game.to_state(), game.legal_moves(), game.move_descriptions())


def test_client_retries_a_429_then_succeeds():
    client = JevClient(
        api_key="k", max_retries=3, opener=http_error(429, then=ok(choice_answer("r0c0")))
    )
    body, latency = client.ask({"x": 1}, {"move": {"type": "noul", "instructions": "q"}})
    assert body["answers"]["move"]["choice"] == "r0c0"
    assert latency >= 0


def test_client_gives_up_after_max_retries():
    client = JevClient(api_key="k", max_retries=2, opener=always_http_error(529))
    with pytest.raises(JevTransportError):
        client.ask({"x": 1}, {})


def test_client_does_not_retry_a_422():
    client = JevClient(api_key="k", max_retries=3, opener=always_http_error(422))
    with pytest.raises(JevError):
        client.ask({"x": 1}, {})


def test_from_env_requires_the_key(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(JevAuthError):
        JevClient.from_env()


def test_from_env_reads_the_key(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "abc")
    client = JevClient.from_env()
    assert client.model == "jev-latest"
    assert client.base_url.endswith("/v1/systemone")
