# jev-arcade — Design

**Date:** 2026-09-21
**Status:** Approved (scope + naming), pending spec review
**Author:** Cankat Sarac

## 1. Problem

TypeSafe's **Jev** is a *System One* model: it does not generate text. It accepts
application state plus typed questions and returns typed answers with calibrated
probabilities — `Choice` (one of up to 255 options), `Score` (position on 2–10
ordered levels), `Noul` (probability that a statement is true).

Game playing is the canonical System One task: perceive a board, pick a move,
repeat, under time pressure. Yet every published "AI plays games" harness targets
*System Two* models — LLMs that reason in text. lmgame-Bench (ICLR 2026) evaluated
LLMs on Tetris, Sokoban, 2048 and Super Mario and found that **on Tetris and Candy
Crush their scores sit close to random play**.

No one has measured a System One model on the same task.

**Research question:** *Can a System One model play arcade games competently, and
is its reported confidence calibrated against whether its move was actually good?*

## 2. Goals and non-goals

### Goals
- A small, readable harness where Jev plays Tetris, Snake and 2048 autonomously.
- Baselines that make the result interpretable: random, and a strong heuristic.
- Reproducible, seeded episodes with recorded replays.
- A public repository that contains no API keys and no copyrighted ROMs.

### Non-goals (explicitly cut)
- **Real Game Boy emulation via PyBoy.** It works and is tempting, but commercial
  ROMs are copyrighted and this repo is public. Deferred behind the `Game`
  protocol, which PyBoy can satisfy later without changing anything else.
- Training or fine-tuning any model. Jev is used as-is.
- A GUI. Terminal rendering only.

## 3. Why this shape

Three findings from the spike drove the design.

**Latency permits real play.** A live call from Istanbul returned in **515 ms**
wall-clock (TypeSafe documents 10–15 ms compute; the remainder is network). An LLM
harness must fight 1–3 s per move; Jev does not. Games still step turn-by-turn, but
an episode completes in minutes rather than hours.

**Illegal moves are structurally impossible.** The move set *is* the `criteria` map
of a `Choice` question. There is no prompt to misparse and no free text to
hallucinate — Jev can only return a key we supplied. This removes the single
largest source of failure in LLM game harnesses.

**Confidence is a separate, usable axis.** `Choice` and `Score` return `confidence`
(distribution concentration) independently of `probabilities`. TypeSafe's
confidence-gated routing pattern applies directly and gives the project its second
measurable.

### Spike result

A hand-built Tetris state with a 4-deep well at column 6 was sent to
`jev-latest`. It returned `c6` at probability 1.0, confidence 0.99, and
`danger: 0.12`.

> **Caveat, recorded deliberately:** that state included a `note` field that named
> column 6 as correct. It validates the transport, not the model's play. The
> harness must never place hints, evaluations or suggestions in state — only
> observable board facts. This is a correctness requirement, not a style note, and
> is enforced by a test.

## 4. Architecture

Dependencies point one way. Games know nothing about Jev; players know nothing
about rendering.

```
src/jev_arcade/
  games/        Game protocol: reset(seed) step(move) legal_moves() to_state() score  game_over
    tetris.py   snake.py   twenty48.py
  players/      Player protocol: choose(state, legal_moves) -> Decision
    random_player.py      null baseline
    heuristic_player.py   strong baseline and low-confidence fallback
    jev_player.py         the System One player
    mock_player.py        scripted; tests run with zero network
  harness/
    runner.py    run_episode(game, player, seed) -> Episode
    recorder.py  JSONL replays: re-watch without spending API calls
    render.py    terminal view
  bench.py       N seeded episodes x M players -> results table
```

### Game protocol

```python
class Game(Protocol):
    def reset(self, seed: int) -> None: ...
    def legal_moves(self) -> list[Move]: ...
    def step(self, move: Move) -> None: ...
    def to_state(self) -> dict:   # JSON-serializable, observable facts only
    @property
    def score(self) -> int: ...
    @property
    def game_over(self) -> bool: ...
```

Games are pure and deterministic given a seed, so they test without a network.

### Player protocol

```python
@dataclass(frozen=True)
class Decision:
    move: Move
    confidence: float | None
    source: Literal["jev", "heuristic", "random"]
    raw: dict | None          # full API answer, for post-hoc analysis

class Player(Protocol):
    def choose(self, state: dict, legal_moves: list[Move]) -> Decision: ...
```

`source` is recorded per move so fallbacks are visible in results rather than
silently inflating Jev's score.

## 5. How Jev plays a move

One HTTP request per move, batching every question over the same state
(TypeSafe's speculative fan-out pattern — parallel questions are documented as
substantially cheaper and faster than sequential ones):

```json
{
  "model": "jev-latest",
  "state": { "board": ["..........", "####...###"], "piece": "I", "heights": [4,4] },
  "questions": {
    "move":    { "type": "choice", "instructions": "...", "criteria": { "r0c6": "rotation 0, column 6" } },
    "danger":  { "type": "noul",   "instructions": "The stack is about to top out." },
    "quality": { "type": "score",  "instructions": "...", "criteria": ["Creates holes", "Neutral", "Clears lines"] }
  }
}
```

`criteria` allows up to 255 options. Tetris has at most 4 rotations x 10 columns =
40 placements, Snake 4, 2048 4 — all comfortably inside the limit, so the full
legal move set is always offered and no pruning heuristic is needed.

### Confidence-gated fallback

```
if decision.confidence >= threshold:   play Jev's move        (source="jev")
else:                                  play heuristic's move  (source="heuristic")
```

The threshold is a config value, not a constant, and is evaluated against recorded
episodes rather than guessed. Per TypeSafe's guidance, confidence measures
distribution concentration and not correctness, so a low value where several moves
are equally fine is not a failure — the analysis must separate "uncertain because
ambiguous" from "uncertain because confused".

## 6. Games

| Game | Engine | Reason |
| --- | --- | --- |
| Tetris | `tetris-gymnasium` (PyPI), wrapped in a placement-level adapter | Reuse before building. Gymnasium-native, board exposed as an array, citable in a write-up. The adapter converts `(rotation, column)` into the keypress sequence the env expects, so Jev decides at placement level rather than per-keypress. |
| Snake | Own implementation, ~120 lines | No package justifies a dependency here. Cleanest possible `Choice`: exactly four options. |
| 2048 | Own implementation, ~150 lines | Trivial to implement, and it appears in lmgame-Bench — giving one directly comparable LLM-vs-System-One number. |

## 7. Error handling

| Condition | Response |
| --- | --- |
| `429` / `529` | Exponential backoff with jitter, bounded retries. |
| `401` | Fail immediately with a clear message. Never retry a bad key. |
| Timeout / connection error | Retry within budget, then fall back to the heuristic and record `source="heuristic"` with the reason. |
| Answer key not in `legal_moves` | Should be impossible. Assert, log the full payload, fall back. A test asserts this path is unreachable under normal operation. |

An episode never dies from a transient API failure; it degrades to the heuristic
and says so in the record.

## 8. Testing

TDD. Coverage target 80%.

- **Games** — pure and seeded; identical seed yields an identical episode. Line
  clears, collisions, merges, game-over conditions tested directly.
- **Harness** — driven by `MockPlayer`; no network involved.
- **Jev adapter** — request construction and response parsing tested against a
  recorded fixture captured from the live API.
- **State hygiene** — a test asserts no serialized state contains hint-like keys
  (`note`, `hint`, `suggestion`, `best`, `answer`), guarding the spike's mistake.
- **Live smoke test** — one, skipped unless `TYPESAFE_API_KEY` is set.

## 9. Reproducibility

Each episode record stores seed, game config, player config, resolved model
version (the API returns `jev-1.13.0` for `jev-latest`), threshold, timestamp and
library versions. Replays are JSONL so a run can be re-rendered and re-analyzed
without spending API calls.

## 10. Security

- Key read from the `TYPESAFE_API_KEY` environment variable only. Never a
  constructor default, never a file in the repo, never a CLI argument.
- `.gitignore` covers `.env`, `*apikey*`, `*api_key*`, `*.key`, `*.pem`.
- `.env.example` ships with an empty value.
- No ROMs of any kind; `*.gb`, `*.gbc`, `*.gba` and `roms/` are gitignored so the
  deferred PyBoy work cannot accidentally commit one later.
- Error messages and recorded replays must not echo the key.

## 11. Deliverable

A results table over N seeded episodes per game:

| Game | Random | Heuristic | Jev | Jev fallback rate |
| --- | --- | --- | --- | --- |

Plus a calibration view: Jev's accuracy against the heuristic's chosen move,
bucketed by reported confidence. If confidence is calibrated, accuracy rises
monotonically across buckets. That plot is the actual scientific claim.

## 12. Open questions

Recorded now, resolved with data rather than argument:

1. What confidence threshold balances autonomy against score? Swept over recorded
   episodes.
2. Does board orientation in the serialized state (row 0 = top vs. bottom) change
   play quality? Testable with one config flag.
3. Does adding a `Score` question on placement quality improve the `Choice`, given
   that batched questions cannot see one another's answers? Ablation.

## 13. References

- TypeSafe API reference — https://docs.typesafe.ai/api
- Speculative fan-out — https://docs.typesafe.ai/patterns/fan-out
- Confidence-gated routing — https://docs.typesafe.ai/patterns/confidence-routing
- Confidence — https://docs.typesafe.ai/confidence
- lmgame-Bench, arXiv:2505.15146 — https://arxiv.org/abs/2505.15146
- Tetris-Gymnasium — https://github.com/Max-We/Tetris-Gymnasium
- PyBoy (deferred) — https://github.com/Baekalfen/PyBoy
