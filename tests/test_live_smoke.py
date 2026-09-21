"""One live call against the real API.

Skipped unless TYPESAFE_API_KEY is set, so the default test run stays offline
and free. This is the only test in the suite that can fail because of somebody
else's infrastructure.
"""

import os

import pytest

from jev_arcade.games.twenty48 import Twenty48
from jev_arcade.players.heuristic_player import HeuristicPlayer
from jev_arcade.players.jev_client import JevClient
from jev_arcade.players.jev_player import JevPlayer

live = pytest.mark.skipif(
    not os.environ.get("TYPESAFE_API_KEY"),
    reason="TYPESAFE_API_KEY is not set, skipping the live call",
)


@live
def test_jev_answers_a_real_board():
    game = Twenty48()
    game.reset(42)
    player = JevPlayer("2048", JevClient.from_env(), HeuristicPlayer("2048"))
    decision = player.choose(game.to_state(), game.legal_moves(), game.move_descriptions())

    assert decision.move in game.legal_moves()
    if decision.source == "jev":
        assert 0.0 <= decision.confidence <= 1.0
        assert decision.raw["model"].startswith("jev")
        # Probabilities are returned per option and should cover the move set.
        assert set(decision.raw["probabilities"]) <= set(game.legal_moves())
        assert 0.0 <= decision.raw["danger"] <= 1.0


@live
def test_a_bad_key_is_rejected_without_retrying():
    from jev_arcade.players.jev_client import JevAuthError

    client = JevClient(api_key="apikey_definitely_not_valid", max_retries=3)
    with pytest.raises(JevAuthError):
        client.ask("hello", {"q": {"type": "noul", "instructions": "Is this a greeting?"}})
