# jev-arcade

**Can a System One model play arcade games?**

[TypeSafe's Jev](https://docs.typesafe.ai/introduction) is a *System One* model. It does
not generate text. You hand it application state plus typed questions, and it returns
typed answers with calibrated probabilities. This repo points that at Tetris, Snake and
2048, and lets it play by itself.

```
turn 17  move left  by jev  confidence 0.52  509 ms
```

## Why this is interesting

Every published "AI plays games" harness targets *System Two* models, meaning LLMs that
reason in text. [lmgame-Bench](https://arxiv.org/abs/2505.15146) (ICLR 2026) ran LLMs on
Tetris, Sokoban, 2048 and Super Mario and found that on Tetris their scores sit close to
random play.

Nobody has measured a System One model on the same task, even though picking a move from
a board is about as System One as a task gets.

Two properties make Jev structurally different from an LLM here.

**Illegal moves are impossible.** The move set *is* the `criteria` map of a `Choice`
question. There is no prompt to misparse and no free text to hallucinate, so Jev can only
return a key the game supplied. That removes the largest failure source in LLM game
harnesses.

**It is fast enough to actually play.** Measured round trip from Istanbul is about 500 ms,
of which TypeSafe documents 10 to 15 ms as compute and the rest is network. An LLM harness
fights 1 to 3 seconds per move.

## What is measured

Two numbers, not one.

1. **Does it play well?** Jev against a uniform random baseline and against a strong
   heuristic, over seeded episodes.
2. **Is its confidence calibrated?** Jev returns `confidence` separately from
   `probabilities`. Bucket its moves by confidence and check whether quality rises with
   it. That is the real claim.

## Results

Three seeded episodes per cell, 60 turns per episode, run 2026-09-21 against
`jev-1.13.0`.

### Raw play, with every answer acted on

Confidence threshold 0, so nothing fell back to the heuristic.

| game | random | heuristic | jev | jev as share of heuristic |
| --- | --- | --- | --- | --- |
| snake | 0 | 80 | 70 | 88% |
| 2048 | 447 | 497 | 484 | 97% |
| tetris | 0 | 2333 | 167 | 7% |

**The pattern is not about game difficulty. It is about action space size and how far
ahead you have to look.** Snake and 2048 offer at most four moves and reward local
reasoning, and there Jev lands close to a tuned heuristic. Tetris offers around 34
placements per piece and rewards planning several pieces ahead, and there Jev falls a
long way short. That is what a System One model should look like: fast intuitive
judgement, not deliberate search.

Jev still clearly beats random on Tetris, scoring 167 against 0 and surviving a mean of
36 pieces against 25. That is worth stating plainly, because lmgame-Bench found LLM
scores on Tetris sitting close to random.

### Calibration: confidence carries real signal

Every Jev move re-simulated from its replay, then compared with what the heuristic would
have chosen from the identical board. Chance agreement is one over the number of legal
options. Turns with one legal move are excluded, because those never reached the API.

| game | confidence | moves | agrees with heuristic | chance |
| --- | --- | --- | --- | --- |
| snake | 0.0 to 0.3 | 18 | 33% | 33% |
| snake | 0.3 to 0.5 | 56 | 54% | 33% |
| snake | 0.5 to 0.8 | 73 | 63% | 33% |
| snake | 0.8 to 1.0 | 157 | **93%** | 33% |
| 2048 | 0.0 to 0.3 | 61 | 16% | 28% |
| 2048 | 0.3 to 0.5 | 99 | 19% | 26% |
| 2048 | 0.5 to 0.8 | 42 | **57%** | 30% |
| tetris | 0.0 to 0.3 | 101 | 19% | 8% |
| tetris | 0.3 to 0.5 | 3 | 33% | 6% |

Snake is the clean case. Agreement rises monotonically from exactly chance at low
confidence to 93% at high confidence. The confidence number is doing real work.

**Look at what is missing from the Tetris rows.** Out of 104 real decisions, 101 came
back below 0.3 confidence, and not one cleared 0.5. Jev never gets confident about a
Tetris move. It is not overconfident and wrong. It is correctly reporting that it does
not know how to play this game.

### Self-routing: one threshold sends each game to the right player

The same benchmark at `--threshold 0.5`, so Jev defers to the heuristic whenever it is
unsure.

| game | jev at threshold 0 | jev at threshold 0.5 | heuristic | fallback rate |
| --- | --- | --- | --- | --- |
| snake | 70 | 73 | 80 | **25%** |
| 2048 | 484 | 499 | 497 | **88%** |
| tetris | 167 | 2333 | 2333 | **100%** |

**The fallback rate tracks competence almost exactly, and nobody configured it.** One
number, 0.5, applied to all three games. On Snake, where Jev genuinely plays well, it
kept control of three quarters of its moves. On Tetris, where it cannot play, it handed
over every single decision.

That is [confidence-gated routing](https://docs.typesafe.ai/patterns/confidence-routing)
behaving as documented: the answer tells you what, the confidence tells you whether to
act. The engineering value is a system that degrades gracefully into a known good
fallback on the tasks the model cannot do, without anyone having to know in advance which
tasks those are.

Be clear about what the Tetris 2333 is, though. At 100% fallback that is the heuristic's
score, not Jev's. Jev contributed the decision to stay out of the way.

### What these numbers do not show

Stated plainly, because a benchmark that oversells itself is worth less than no benchmark.

* **Three seeds per cell is a small sample.** Enough to see a 300x gap on Tetris, not
  enough to trust the 13 point gap on 2048.
* **60 turns barely stretches 2048.** Random scores 447 and the heuristic 497, so the
  game only separates players by about 11% at this length.
* **The Tetris heuristic never died.** It hit the 60 turn cap every time, so 2333 is a
  floor on its skill, not a measurement of it.
* **Agreement with the heuristic is a proxy, not truth.** It is the strongest reference
  available and it sees the same state, but on 2048 the heuristic itself is only
  marginally better than random, which makes agreement a weak signal for that game. The
  Tetris consequence measure, holes created per move, needs no reference and is the
  stronger of the two.

Reproduce with:

```bash
PYTHONPATH=src python3 -m jev_arcade bench --game all --player all --episodes 3 --max-turns 60
PYTHONPATH=src python3 -m jev_arcade bench --game all --player jev --episodes 3 --threshold 0.5
PYTHONPATH=src python3 -m jev_arcade analyse
```

The analysis step costs nothing. Replays store the seed and move sequence, and the games
are deterministic, so every episode re-simulates exactly.

## How a move works

One HTTP request per move, batching every question over the same state. This is
TypeSafe's [speculative fan-out](https://docs.typesafe.ai/patterns/fan-out) pattern.

```json
{
  "model": "jev-latest",
  "state": { "board": ["..........", "####...###"], "current_piece": "I", "column_heights": [4, 4] },
  "questions": {
    "move":   { "type": "choice", "criteria": { "r0c6": "rotation 0, column 6" } },
    "danger": { "type": "noul",   "instructions": "The stack has grown close to the top." },
    "health": { "type": "score",  "criteria": ["Low and flat", "Moderate", "High and badly holed"] }
  }
}
```

Questions inside one request cannot see each other's answers, so the companion questions
ask about the board as it stands rather than about the move that was chosen. They are
telemetry, not inputs to the decision.

Then [confidence-gated routing](https://docs.typesafe.ai/patterns/confidence-routing). If
confidence clears the threshold, play Jev's move. Otherwise fall back to the heuristic,
and record which one played, so fallbacks never silently inflate Jev's score.

## Fairness rules

A benchmark that leaks the answer into the question measures nothing. Two rules are
enforced by tests rather than by good intentions.

**No hints in state.** No serialized field may be named `note`, `hint`, `suggestion`,
`best`, `advice` or `answer`. Perception aids such as `column_heights` are allowed because
they are directly readable off the board. Evaluations of the position are not.

**No evaluative move labels.** A label may say `rotation 0, columns 3 to 5`. It may not
say which placement is good.

These exist because the first exploratory call during design *did* include a hint, and Jev
answered it at confidence 0.99. That proved the transport worked and measured nothing.

## Architecture

Dependencies point one way. Games know nothing about Jev. Players know nothing about
rendering.

```
src/jev_arcade/
  types.py      frozen value types: Decision, MoveRecord, Episode
  games/        tetris.py  snake.py  twenty48.py
  players/      random_player  heuristic_player  jev_player  jev_client  mock_player
  harness/      runner  recorder (JSONL replays)  render (ANSI terminal)
  analysis.py   calibration report over replays, no API calls
  web/          stdlib SSE server and the race viewer page
  bench.py      watch, bench, analyse and serve commands
```

Games are pure and deterministic given a seed, so the whole suite runs without touching a
network. The Jev tests inject a fake opener.

## Games

| Game | Engine | Notes |
| --- | --- | --- |
| Tetris | own, pure Python | Placement level moves such as `r1c4`, not keypresses, so a player decides once per piece. Rotations are generated by rotating the base shape, not from a hand written table. |
| Snake | own, pure Python | The cleanest possible `Choice`, at most four options. Reversing into the neck is excluded from the legal set. |
| 2048 | own, pure Python | Also in lmgame-Bench, which gives one directly comparable number. A move is legal only if it changes the board. |

The design originally called for [`tetris-gymnasium`](https://github.com/Max-We/Tetris-Gymnasium)
under a reuse before building rule. It was dropped after checking its dependency tree: it
pulls jax, chex and opencv-python, roughly 200MB, to model a 10x20 integer grid, and it
exposes keypress level actions when this project needs placement level ones. The placement
simulation would have had to be written anyway.

**No ROMs.** Real Game Boy emulation via [PyBoy](https://github.com/Baekalfen/PyBoy) works
and was considered, but commercial ROMs are copyrighted and this repo is public. It is
deferred behind the `Game` protocol, which PyBoy can satisfy later without changing
anything else.

## Setup

**Runtime dependencies: none.** Python 3.11 or newer and the standard library. The HTTP
client is `urllib`. Clone and run.

```bash
git clone https://github.com/CankatSarac/jev-arcade
cd jev-arcade
cp .env.example .env     # then paste your key into .env
```

Get a key at [console.typesafe.ai/keys](https://console.typesafe.ai/keys). The key is read
from `TYPESAFE_API_KEY` and nowhere else. Never a file in the repo, never a CLI argument.
`.env` is gitignored.

## Watch it in the browser

```bash
PYTHONPATH=src python3 -m jev_arcade serve
```

Then open http://127.0.0.1:8765. Two boards run the same seed side by side, so both
players get an identical starting position and an identical piece sequence. Pick the
game, the two players, the seed, the turn cap and the confidence threshold, then press
start.

Under the Jev board you get its confidence bar and the probability it assigned to each
of its top options, updating every move. It is the clearest view of the finding: on Snake
the two boards track each other, and on Tetris you watch one stack fill with holes while
the other stays flat.

A real Tetris race, seed 0, reading off the stream:

```
t 0  JEV  r0c0 conf 0.40  holes  0  |  HEUR  r0c7  holes  0
t 3  JEV  r0c0 conf 0.10  holes  8  |  HEUR  r0c2  holes  0
t 5  JEV  r0c0 conf 0.06  holes 12  |  HEUR  r2c2  holes  0
t11  JEV  r0c4 conf 0.07  holes 19  |  HEUR  r0c1  holes  2
```

Two things are visible there that the summary tables cannot show. Jev has a pronounced
left column bias, playing `r0c0` seven times in twelve turns. And its confidence falls
from 0.40 to under 0.07 as the board degrades, which is the calibration result happening
live: it registers that the position is lost even though it cannot repair it.

The server is the standard library, `http.server` streaming Server Sent Events. No web
framework, because the zero dependency property is worth more than the convenience.

**Security.** The server binds to `127.0.0.1` only, so nothing off this machine can reach
it. The API key stays server side: the browser receives game state and model answers, and
never talks to TypeSafe itself. Every query parameter is checked against a fixed whitelist
and the numbers are clamped, so a crafted URL cannot start an unbounded run that spends
API calls. Passing a different `--host` prints a warning, because this process holds your
key.

## Usage


Watch a game being played, one frame per move:

```bash
PYTHONPATH=src python3 -m jev_arcade watch --game tetris --player heuristic
PYTHONPATH=src python3 -m jev_arcade watch --game 2048 --player jev --max-turns 40
```

Run the benchmark:

```bash
PYTHONPATH=src python3 -m jev_arcade bench --game all --player all --episodes 3 --max-turns 60
```

Make Jev defer to the heuristic whenever it is unsure:

```bash
PYTHONPATH=src python3 -m jev_arcade bench --game tetris --player jev --threshold 0.5
```

Report on whether Jev's confidence carried signal:

```bash
PYTHONPATH=src python3 -m jev_arcade analyse
```

Results land in `results/` and full replays in `replays/`, as JSONL. The analysis reads
those replays and re-simulates each episode from its seed, so it costs no API calls at
all.

**Cost note.** Jev spends one API call per turn. The `--max-turns` flag is a budget as much
as a rule, which is why scores are reported as score within N turns rather than final
score. Random and heuristic players are free and instant.

## Tests

```bash
python3 -m pytest tests/ -q
```

No network access is required. Every test either uses a pure game engine or an injected
fake HTTP opener. One live smoke test is skipped unless `TYPESAFE_API_KEY` is set.

## References

* [TypeSafe API reference](https://docs.typesafe.ai/api), [Confidence](https://docs.typesafe.ai/confidence), [Patterns](https://docs.typesafe.ai/patterns)
* [lmgame-Bench: How Good are LLMs at Playing Games?](https://arxiv.org/abs/2505.15146), arXiv:2505.15146
* [GamingAgent](https://github.com/lmgame-org/GamingAgent), the LLM side equivalent

## License

MIT. See [LICENSE](LICENSE).
