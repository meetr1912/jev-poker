# Jev Poker

Watch **Jev** (TypeSafe's System One model) play heads-up No-Limit Texas Hold'em against a
local bot — with its decision probabilities rendered live on the side panel.

Jev does not generate text here. Each betting decision is a single TypeSafe `choice` question.
Jev scores every legal action, your code acts on the winner, and the distribution *is* the
"thinking" shown on the right.

> Educational/demo project. It plays a local engine only; it is not connected to any real-money
> poker site (automating those breaks their terms of service).

## What's in here

| File | Job |
| --- | --- |
| `jev_poker/engine.py` | Heads-up NLHE table on [PokerKit](https://github.com/uoftcprg/pokerkit) (state, legal actions, chip accounting) |
| `jev_poker/jev.py` | TypeSafe call: builds the state + a choice question over the legal actions, validates the answer |
| `jev_poker/bots.py` | `HouseBot` (heuristic) and `CallBot` (baseline) opponents |
| `jev_poker/scoreboard.py` | Money/points ledger; writes `results/scoreboard.json` and `results/SCOREBOARD.md` |
| `jev_poker/demo.py` | Match loop + local inspector server |
| `jev_poker/static/` | The felt, cards, and "Jev's thinking" side panel |

## Run it

```bash
cd ~/jev-poker
uv sync
cp .env.example .env          # then add TYPESAFE_API_KEY
uv run jev-poker              # opens http://127.0.0.1:8777
```

The API key is read from `.env` here, or falls back to `~/jev-ultrafast/.env`.

Options:

```bash
uv run jev-poker --hands 12 --stack 200 --blinds 2 --delay 0.6 --port 8777
uv run jev-poker --headless --hands 6     # print a transcript instead of serving the UI
```

## Money and points, captured

Each player starts with a bankroll (chips double as dollars, $1 per chip). The
match ledger records, per hand, the winner, the pot, and both players' net
money. When a match ends it writes:

- `results/scoreboard.json` — machine-readable ledger
- `results/SCOREBOARD.md` — the table below

```bash
uv run jev-poker --headless --hands 100 --stack 1000 --results-dir results
```

Captured example (`results/SCOREBOARD.md`):

| Player | Money | Net | Hands won |
| --- | ---: | ---: | ---: |
| HouseBot-A | $2000 | +1000 | 13 |
| HouseBot-B | $0 | -1000 | 7 |

### Offline mode (no API key)

`--offline` replaces Jev with a local heuristic agent, so a full money/points
scorecard can be produced with **no TypeSafe key and no paid calls**. This is
what CI runs:

```bash
uv run jev-poker --headless --offline --hands 100 --stack 1000 --results-dir results
```

## The decision loop

Every legal action becomes one choice criterion:

```
state  : your hand, position, street, board, pot, chips to call, stacks, recent actions
question: { "action": { type: choice, criteria: {FOLD, CHECK/CALL, RAISE_MIN, ...} } }
answer : { choice, probabilities, confidence }
```

The chosen action is applied to the engine exactly once. In one request, Jev evaluates the
whole action set, so the side panel can show how close the second-best option was.

Example (River, from the screenshot): `CHECK 54% · RAISE_MIN 19% · RAISE_HALF 14% ·
RAISE_POT 9% · RAISE_ALLIN 4%`, confidence 41%, ~210 ms.

## Safety rails

- **Targets never come from the model.** Jev picks among action *names* the engine generated;
  it cannot invent a size or a selector.
- **One request per decision.** An invalid or non-normalized answer is rejected and retried.
- **Fail safe, not open.** If TypeSafe is unavailable, the hand takes the safest legal action
  (check/call, else fold) and the panel labels it a fallback.
- **Bounded.** A per-hand action cap prevents loops.

## Verify

```bash
uv run pytest -q     # chip conservation, legal-action invariants, scoreboard math
uv run ruff check .
```

## CI

`.github/workflows/ci.yml` runs lint, tests, and a package build. `.github/workflows/scoreboard.yml`
plays an offline match and uploads `results/` as an artifact.

Both run **without any secrets**: `.env` is gitignored, `.env.example` has empty
placeholders, and CI uses the `--offline` path, which never reads `TYPESAFE_API_KEY`.
