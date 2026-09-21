# jev-arcade Implementation Plan

> **For agentic workers:** use superpowers:executing-plans to work through this task by task. Steps use checkbox syntax for tracking.

**Goal:** A runnable harness where TypeSafe's Jev plays Tetris, Snake and 2048 by itself, benchmarked against random and heuristic baselines.

**Architecture:** Three layers with one way dependencies. Games are pure, seeded state machines that expose a JSON serializable view and a list of legal moves. Players map that view to a move. The harness drives the loop, records replays and renders.

**Tech Stack:** Python 3.11+, standard library only at runtime. Dev extras: pytest, ruff, mypy. Package manager: uv.

**Spec:** `docs/superpowers/specs/2026-09-21-jev-arcade-design.md`

## Global Constraints

* Runtime dependencies: none. Standard library only, including the HTTP client (`urllib.request`).
* No dash punctuation in any repo text. No em dash, no ` - ` inside a sentence. Use commas, colons or separate sentences. Empty table cells read `n/a`. Markdown bullet syntax and hyphenated compound words are fine.
* API key comes from the `TYPESAFE_API_KEY` environment variable only. Never a default argument, never a file in the repo, never a CLI argument.
* Serialized game state contains observable facts only. No key may be named `note`, `hint`, `suggestion`, `best`, `advice` or `answer`. Enforced by a test.
* Every game is deterministic given a seed. Same seed plus same moves yields the same episode.
* Endpoint `https://api.typesafe.ai/v1/systemone`, model `jev-latest`, auth header `Authorization: Bearer <key>`.
* Commits use Conventional Commits and carry no attribution trailers.

## Spec revision recorded during planning

The spec named `tetris-gymnasium` as the Tetris engine under a reuse first rule. Planning found it depends on jax, chex and opencv-python, roughly 200MB, to model a 10x20 integer grid. It also exposes keypress level actions while this project needs placement level actions, so the placement simulation would have to be written regardless. Decision: write all three engines in pure Python. The repo becomes zero dependency and clone to run. Spec section 6 is updated to match.

## File structure

```
src/jev_arcade/
  types.py              Move, Decision, Episode, MoveRecord. Frozen dataclasses.
  games/
    base.py             Game protocol
    tetris.py           10x20 Tetris, 7 piece bag, placement level moves
    snake.py            Grid snake, 4 direction moves
    twenty48.py         4x4 2048, 4 direction moves
  players/
    base.py             Player protocol
    random_player.py    Uniform over legal moves. Seeded.
    heuristic_player.py Per game heuristics. Deterministic.
    mock_player.py      Scripted queue of moves. Test only.
    jev_player.py       Builds questions, calls client, gates on confidence
    jev_client.py       HTTP transport, retries, error mapping
  harness/
    runner.py           run_episode
    recorder.py         JSONL write and read
    render.py           ANSI terminal view
  bench.py              CLI entry point
tests/
  test_tetris.py  test_snake.py  test_twenty48.py
  test_players.py  test_jev_player.py  test_runner.py  test_state_hygiene.py
```

## Tasks

### Task 1: Core types and protocols

**Files:** Create `src/jev_arcade/types.py`, `src/jev_arcade/games/base.py`, `src/jev_arcade/players/base.py`

**Produces:**
* `Move = str` (an opaque key, always a member of `legal_moves()`)
* `@dataclass(frozen=True) Decision(move: Move, source: str, confidence: float | None, raw: dict | None)`
* `@dataclass(frozen=True) MoveRecord(turn: int, move: Move, source: str, confidence: float | None, score_after: int, latency_ms: float | None)`
* `@dataclass(frozen=True) Episode(game: str, player: str, seed: int, final_score: int, turns: int, moves: list[MoveRecord], meta: dict)`
* `Game` protocol: `reset(seed)`, `legal_moves() -> list[Move]`, `move_descriptions() -> dict[Move, str]`, `step(move)`, `to_state() -> dict`, `score: int`, `game_over: bool`, `name: str`
* `Player` protocol: `choose(state, legal_moves, descriptions) -> Decision`, `name: str`

Steps: write the dataclasses, assert frozen, commit.

### Task 2: Tetris engine

**Files:** Create `src/jev_arcade/games/tetris.py`, `tests/test_tetris.py`

Board 10 wide by 20 tall, list of lists of int. Seven piece bag randomiser seeded from `random.Random(seed)`. A move key is `r{rot}c{col}`. `legal_moves()` enumerates rotations by columns where the piece fits. `step` drops the piece to rest, locks it, clears full rows, scores 0/100/300/500/800 for 0..4 lines, then spawns the next piece. `game_over` when the spawned piece cannot be placed.

`to_state()` returns `board` as a list of strings using `.` and `#`, `column_heights`, `holes`, `current_piece`, `next_piece`, `lines_cleared`, `score`.

Tests: seeded determinism, single line clear, tetris clear scores 800, holes counted under an overhang, game over on a full board, every returned move is legal.

### Task 3: Snake engine

**Files:** Create `src/jev_arcade/games/snake.py`, `tests/test_snake.py`

12x12 grid. Moves `up`, `down`, `left`, `right`. Reversing into the neck is excluded from `legal_moves()`. Eating food grows the snake and scores 10. Collision with wall or body ends the game. Food placement uses the seeded RNG. A step budget of 400 without eating ends the episode so a looping player cannot run forever.

`to_state()` returns `grid` as strings, `head`, `body_length`, `food`, `direction`, `steps_since_food`.

Tests: determinism, growth on eating, wall collision, self collision, reverse move excluded, starvation cutoff.

### Task 4: 2048 engine

**Files:** Create `src/jev_arcade/games/twenty48.py`, `tests/test_twenty48.py`

4x4 grid of ints. Moves `up`, `down`, `left`, `right`. A move is legal only if it changes the board. Merge rule: each tile merges at most once per move, score increases by the merged value. After a move spawn a 2 with probability 0.9 else a 4, in a uniformly chosen empty cell from the seeded RNG. Game over when no move changes the board.

`to_state()` returns `grid` as rows of ints, `max_tile`, `empty_cells`, `score`.

Tests: determinism, left merge of `[2,2,4,4]` gives `[4,8,0,0]` and scores 12, no double merge of `[4,4,4,4]` giving `[8,8,0,0]`, illegal move excluded, game over detection.

### Task 5: Random and Mock players

**Files:** Create `src/jev_arcade/players/random_player.py`, `src/jev_arcade/players/mock_player.py`, `tests/test_players.py`

`RandomPlayer(seed)` picks uniformly from legal moves and returns `source="random"`, `confidence=None`. `MockPlayer(moves)` pops a scripted queue and falls back to the first legal move when exhausted. Tests cover determinism and that both only ever return legal moves.

### Task 6: Heuristic players

**Files:** Create `src/jev_arcade/players/heuristic_player.py`, extend `tests/test_players.py`

One class with a per game strategy chosen by `game_name`.

* Tetris: simulate each placement, score with Dellacherie style weights on aggregate height, lines cleared, holes and bumpiness. Weights are module constants.
* Snake: greedy Manhattan step toward food, rejecting moves that hit a wall or body, preferring the move that keeps the most free space.
* 2048: one ply lookahead scoring empty cells, monotonicity and max tile in a corner.

Returns `source="heuristic"`, `confidence=None`. Tests assert it beats RandomPlayer on the same seeds for all three games.

### Task 7: Jev client and player

**Files:** Create `src/jev_arcade/players/jev_client.py`, `src/jev_arcade/players/jev_player.py`, `tests/test_jev_player.py`

`JevClient(api_key, model, base_url, timeout, max_retries)` posts `{state, model, questions}` with `urllib.request` and returns the parsed body plus latency. Retries 429 and 529 with exponential backoff and jitter. Raises immediately on 401. Key read from env in a `from_env()` constructor.

`JevPlayer(client, confidence_threshold, fallback)` sends one request per move containing a `move` Choice over the full legal set, a `danger` Noul and a `quality` Score. On an answer above the threshold it returns `source="jev"`. Below threshold, on a transport failure, or on an answer outside the legal set, it delegates to the fallback and returns `source="heuristic"` with the reason in `raw`.

Tests use a fake transport, no network. Cover: request shape, criteria covers every legal move, low confidence falls back, 401 raises, 429 retries then succeeds, illegal answer falls back. One live smoke test skipped unless `TYPESAFE_API_KEY` is set.

### Task 8: Harness

**Files:** Create `src/jev_arcade/harness/runner.py`, `recorder.py`, `render.py`, `tests/test_runner.py`, `tests/test_state_hygiene.py`

`run_episode(game, player, seed, max_turns, on_step)` loops until game over or the turn cap, records a `MoveRecord` per turn and returns an `Episode`. `recorder.write_jsonl` and `read_jsonl` round trip an Episode. `render.render(state, game_name)` returns an ANSI string, and `on_step` can print it for live viewing.

`test_state_hygiene` walks every key of `to_state()` for all three games and asserts none is in the banned set.

### Task 9: Benchmark CLI

**Files:** Create `src/jev_arcade/bench.py`, `src/jev_arcade/__main__.py`

`python3 -m jev_arcade` runs a game with a player and optional live rendering. `bench` runs N seeded episodes for each selected player and prints a markdown results table with mean and best score plus the Jev fallback rate. Writes replays under `replays/` and results under `results/`.

### Task 10: Docs pass

**Files:** Modify `README.md`, `docs/superpowers/specs/2026-09-21-jev-arcade-design.md`, `pyproject.toml`

Remove all dash punctuation. Update spec section 6 with the engine decision above. Drop the runtime dependency list from pyproject. Fill the README results table from a real run. Change the status notice to reflect working code.
