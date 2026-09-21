"""Adapter from Gymnasium's toy_text environments to the Game protocol.

Why these environments. They are discrete action, turn based and small state,
which is exactly the shape a Choice question wants. Taxi even publishes an
`action_mask` per step, so the "an illegal move cannot be expressed" property
carries over for free: only unmasked actions ever reach the criteria map.

Why an optional dependency. The core package stays standard library only.
Install with `pip install jev-arcade[gym]` to get these four games. Gymnasium
itself is light, needing numpy, cloudpickle, typing-extensions and
farama-notifications.

A raw Gymnasium observation is an integer, which tells a model nothing. Every
environment here has a `describe` function that turns that integer back into a
readable board, because the model has to see the game rather than its index.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from jev_arcade.types import Move

__all__ = ["GymGame", "GYM_GAMES", "gymnasium_available"]

INSTALL_HINT = (
    "gymnasium is not installed. These games are an optional extra: "
    "pip install 'jev-arcade[gym]' or uv pip install gymnasium"
)


def gymnasium_available() -> bool:
    try:
        import gymnasium  # noqa: F401

        return True
    except ImportError:
        return False


# ---- per environment descriptions -------------------------------------------


def _frozen_lake(env: Any, obs: Any) -> dict[str, Any]:
    desc = [[c.decode() for c in row] for row in env.unwrapped.desc]
    ncol = len(desc[0])
    row, col = divmod(int(obs), ncol)
    grid = [r[:] for r in desc]
    grid[row][col] = "P"
    return {
        "grid": ["".join(r) for r in grid],
        "grid_legend": (
            "'P' is you, 'S' start, 'F' safe frozen tile, 'H' hole which ends the "
            "episode, 'G' the goal. Row 0 is the top."
        ),
        "position": {"row": row, "col": col},
        "goal": "reach G without stepping on an H",
    }


def _cliff_walking(env: Any, obs: Any) -> dict[str, Any]:
    rows, cols = env.unwrapped.shape
    row, col = divmod(int(obs), cols)
    grid = [["." for _ in range(cols)] for _ in range(rows)]
    for c in range(1, cols - 1):
        grid[rows - 1][c] = "C"
    grid[rows - 1][cols - 1] = "G"
    grid[row][col] = "P"
    return {
        "grid": ["".join(r) for r in grid],
        "grid_legend": (
            "'P' is you, 'C' is cliff which costs 100 and sends you back to the "
            "start, 'G' is the goal, '.' is safe. Row 0 is the top."
        ),
        "position": {"row": row, "col": col},
        "goal": "reach G in as few steps as possible without walking into C",
    }


TAXI_LOCATIONS = {0: "R", 1: "G", 2: "Y", 3: "B"}


def _taxi(env: Any, obs: Any) -> dict[str, Any]:
    taxi_row, taxi_col, passenger, destination = env.unwrapped.decode(int(obs))
    in_taxi = passenger == 4
    return {
        "taxi": {"row": int(taxi_row), "col": int(taxi_col)},
        "passenger_location": "in the taxi" if in_taxi else TAXI_LOCATIONS[int(passenger)],
        "destination": TAXI_LOCATIONS[int(destination)],
        "passenger_on_board": in_taxi,
        "grid_legend": (
            "A 5 by 5 grid with pickup points R, G, Y and B. Row 0 is the top. "
            "R is (0,0), G is (0,4), Y is (4,0), B is (4,3)."
        ),
        "goal": (
            "drive to the passenger, pick them up, drive to the destination and drop "
            "them off. Every step costs 1, a wrong pickup or dropoff costs 10, a "
            "correct dropoff pays 20."
        ),
    }


def _blackjack(env: Any, obs: Any) -> dict[str, Any]:
    player_sum, dealer_card, usable_ace = obs
    return {
        "your_total": int(player_sum),
        "dealer_showing": int(dealer_card),
        "you_hold_a_usable_ace": bool(usable_ace),
        "goal": "get closer to 21 than the dealer without going over 21",
    }


Describe = Callable[[Any, Any], dict[str, Any]]


class _Spec:
    def __init__(self, env_id: str, actions: dict[int, str], describe: Describe) -> None:
        self.env_id = env_id
        self.actions = actions
        self.describe = describe


# Action names come from the Gymnasium documentation for each environment.
GYM_GAMES: dict[str, _Spec] = {
    "frozenlake": _Spec(
        "FrozenLake-v1",
        {0: "left", 1: "down", 2: "right", 3: "up"},
        _frozen_lake,
    ),
    "cliffwalking": _Spec(
        "CliffWalking-v1",
        {0: "up", 1: "right", 2: "down", 3: "left"},
        _cliff_walking,
    ),
    "taxi": _Spec(
        "Taxi-v4",
        {0: "south", 1: "north", 2: "east", 3: "west", 4: "pickup", 5: "dropoff"},
        _taxi,
    ),
    "blackjack": _Spec(
        "Blackjack-v1",
        {0: "stick", 1: "hit"},
        _blackjack,
    ),
}


class GymGame:
    """Wraps one Gymnasium toy_text environment as a jev-arcade Game."""

    def __init__(self, name: str) -> None:
        if name not in GYM_GAMES:
            raise ValueError(f"unknown gym game {name!r}. Choose from {', '.join(GYM_GAMES)}")
        try:
            import gymnasium as gym
        except ImportError as exc:
            raise ImportError(INSTALL_HINT) from exc

        self.name = name
        self._spec = GYM_GAMES[name]
        self._gym = gym
        self._env = gym.make(self._spec.env_id)
        self._by_label = {label: index for index, label in self._spec.actions.items()}
        self._obs: Any = None
        self._info: dict[str, Any] = {}
        self._score = 0.0
        self._done = False
        self.reset(0)

    def reset(self, seed: int) -> None:
        self._obs, self._info = self._env.reset(seed=seed)
        self._env.action_space.seed(seed)
        self._score = 0.0
        self._done = False

    def legal_moves(self) -> list[Move]:
        if self._done:
            return []
        mask = self._info.get("action_mask")
        if mask is not None:
            return [self._spec.actions[i] for i, ok in enumerate(mask) if ok]
        return list(self._spec.actions.values())

    def move_descriptions(self) -> dict[Move, str]:
        # Descriptive, never evaluative, the same rule the hand written games follow.
        labels = {
            "pickup": "pick the passenger up here",
            "dropoff": "drop the passenger off here",
            "stick": "stop drawing and let the dealer play",
            "hit": "draw one more card",
        }
        return {m: labels.get(m, f"move {m}") for m in self.legal_moves()}

    def step(self, move: Move) -> None:
        if move not in self.legal_moves():
            raise ValueError(f"illegal move {move!r}")
        obs, reward, terminated, truncated, info = self._env.step(self._by_label[move])
        self._obs, self._info = obs, info
        self._score += float(reward)
        self._done = bool(terminated or truncated)

    def to_state(self) -> dict[str, Any]:
        state = self._spec.describe(self._env, self._obs)
        state["score"] = round(self._score, 2)
        state["environment"] = self._spec.env_id
        return state

    @property
    def score(self) -> int:
        # The Game protocol reports an int. Gymnasium rewards are floats, and
        # these four environments only ever emit whole numbers.
        return int(round(self._score))

    @property
    def game_over(self) -> bool:
        return self._done

    def close(self) -> None:
        self._env.close()
