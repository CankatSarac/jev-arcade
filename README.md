# jev-arcade

**Can a System One model play arcade games?**

[TypeSafe's Jev](https://docs.typesafe.ai/introduction) is a *System One* model. It
doesn't generate text — you hand it application state and typed questions, and it
returns typed answers with calibrated probabilities. This repo points that at
Tetris, Snake and 2048, and lets it play by itself.

> **Status: design complete, implementation in progress.**
> The [design spec](docs/superpowers/specs/2026-09-21-jev-arcade-design.md) is
> written and the API path is verified against the live service. Game and player
> code is not written yet. Nothing below is claimed to run until this notice
> changes.

---

## Why this is interesting

Every published "AI plays games" harness targets *System Two* models — LLMs that
reason in text. [lmgame-Bench](https://arxiv.org/abs/2505.15146) (ICLR 2026) ran
LLMs on Tetris, Sokoban, 2048 and Super Mario and found that **on Tetris their
scores sit close to random play**.

Nobody has measured a System One model on the same task — even though picking a
move from a board is about as System One as a task gets.

Two properties make Jev structurally different from an LLM here:

**Illegal moves are impossible.** The move set *is* the `criteria` map of a
`Choice` question. There's no prompt to misparse and no free text to hallucinate;
Jev can only return a key we supplied. That removes the largest failure source in
LLM game harnesses.

**It's fast enough to actually play.** A live call from Istanbul returned in
**515 ms** wall-clock (TypeSafe documents 10–15 ms compute; the rest is network).
An LLM harness fights 1–3 s per move.

## The question being measured

Two numbers, not one:

1. **Does it play well?** Jev vs. a random baseline vs. a strong heuristic, over
   seeded episodes.
2. **Is its confidence calibrated?** Jev returns `confidence` separately from
   `probabilities`. Bucket its moves by confidence and check whether accuracy
   rises monotonically. That plot is the real claim.

## How a move works

One HTTP request per move, batching every question over the same state — TypeSafe's
[speculative fan-out](https://docs.typesafe.ai/patterns/fan-out) pattern:

```json
{
  "model": "jev-latest",
  "state": { "board": ["..........", "####...###"], "piece": "I", "heights": [4, 4] },
  "questions": {
    "move":    { "type": "choice", "criteria": { "r0c6": "rotation 0, column 6" } },
    "danger":  { "type": "noul",   "instructions": "The stack is about to top out." },
    "quality": { "type": "score",  "criteria": ["Creates holes", "Neutral", "Clears lines"] }
  }
}
```

Then [confidence-gated routing](https://docs.typesafe.ai/patterns/confidence-routing):
if confidence clears the threshold, play Jev's move; otherwise fall back to the
heuristic — and record which one played, so fallbacks never silently inflate Jev's score.

## Architecture

Dependencies point one way. Games know nothing about Jev; players know nothing
about rendering.

```
src/jev_arcade/
  games/      Game protocol: reset · step · legal_moves · to_state · score
  players/    random · heuristic · jev · mock
  harness/    runner · recorder (JSONL replays) · render (terminal)
  bench.py    N seeded episodes × M players → results table
```

Games are pure and deterministic given a seed, so the whole suite tests without
touching the network.

## Games

| Game | Engine | Why |
| --- | --- | --- |
| Tetris | [`tetris-gymnasium`](https://github.com/Max-We/Tetris-Gymnasium) + placement adapter | Reuse before building. Jev decides at placement level, not per-keypress. |
| Snake | Own, ~120 lines | No package justifies a dependency. Cleanest possible `Choice` — 4 options. |
| 2048 | Own, ~150 lines | Trivial, and in lmgame-Bench — one directly comparable number. |

**No ROMs.** Real Game Boy emulation via [PyBoy](https://github.com/Baekalfen/PyBoy)
works and was considered, but commercial ROMs are copyrighted and this repo is
public. It's deferred behind the `Game` protocol, which PyBoy can satisfy later
without changing anything else.

## Setup

```bash
uv sync
cp .env.example .env     # then paste your key into .env
```

Get a key at [console.typesafe.ai/keys](https://console.typesafe.ai/keys).
The key is read from `TYPESAFE_API_KEY` and nowhere else — never a file in the
repo, never a CLI argument. `.env` is gitignored.

```bash
uv run python -m jev_arcade.bench --game tetris --player jev --episodes 10   # planned
```

## Results

Populated once the implementation lands.

| Game | Random | Heuristic | Jev | Jev fallback rate |
| --- | --- | --- | --- | --- |
| Tetris | — | — | — | — |
| Snake | — | — | — | — |
| 2048 | — | — | — | — |

## References

- [TypeSafe API reference](https://docs.typesafe.ai/api) · [Confidence](https://docs.typesafe.ai/confidence) · [Patterns](https://docs.typesafe.ai/patterns)
- [lmgame-Bench: How Good are LLMs at Playing Games?](https://arxiv.org/abs/2505.15146) (arXiv:2505.15146)
- [GamingAgent](https://github.com/lmgame-org/GamingAgent) — the LLM-side equivalent

## License

MIT — see [LICENSE](LICENSE).
