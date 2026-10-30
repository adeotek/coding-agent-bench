# Determinism — measured, not assumed

The bench spent a week explaining sampling noise and no time measuring how much of it is removable.
`scripts/determinism_probe.py` (`make determinism`) answers that directly, with cents: the same prompt
sent N times to the same model, in three arms, counting distinct answers.

Measured **2026-10-30**, `deepseek-v4.1-flash` via `https://opencode.ai/zen/go/v1`, 6 requests per arm
(18 total, ≈$0.01):

| arm | sampling parameters | session | answers | distinct |
|---|---|---|---|---|
| `pinned` | `temperature: 0`, `seed: 42`, `top_p: 1` | one, reused | 5 | **5** |
| `default` | none (what every agent sends) | one, reused | 5 | **5** |
| `new-session` | `temperature: 0`, `seed: 42`, `top_p: 1` | fresh per call | 6 | **4** |

**The endpoint ignores `temperature: 0` and `seed`.** Five pinned requests produced five different
programs; the unpinned arm did exactly the same. So the sampling variance this bench measures is **not
removable from the client** — plumbing temperature/seed through the adapters would buy nothing on this
provider. (One request in each of the first two arms came back with empty content at `max_tokens: 1500`:
a reasoning model spends the budget thinking first. The probe counts those separately rather than scoring
the empty string as a reproducible answer — the first version of the probe did exactly that and reported
"6 identical answers", which was a bug, not a finding.)

The `new-session` arm is the interesting one for a different reason: same pinned request, only the routing
session differs, and it produced **4 distinct answers in 6 calls** — i.e. the provider's session-affine
routing is visible at this granularity but not separable from sampling with six calls. Treat it as a
second variance source worth naming, not a measured effect.

## What this settles

- **No agent-side knob can make a trial repeatable here.** Any claim of the form "we fixed the benchmark's
  variance by pinning temperature" is false on this endpoint, before it is tested.
- **Replication is the only lever**, so the tooling now enforces it: `N_ATTEMPTS` defaults to 3 for
  `subset`/`full`, `bench_report.py matrix` refuses a single-draw job, rates print with Wilson intervals,
  and `docs/cell-stability.json` records which cells have been measured enough to say anything.
- **The measured floor stands as measured**: 10 of 24 (cell, agent) pairs still split at k=3, and the
  4–6 cell sweep-to-sweep swing on unchanged binaries is what those rates must produce. That is not a
  defect to be engineered away; it is the cost of asking a sampling process a question.

## Reproducing

```bash
set -a && . ./.env && set +a
make determinism            # 6 requests per arm
python3 scripts/determinism_probe.py -n 12 --json
```

Two provider quirks the probe had to learn, both worth knowing before writing another client:

- **Cloudflare fronts the endpoint** and answers urllib's default User-Agent with `error code: 1010`
  before the request reaches the API. Send a real UA.
- **The go endpoint requires `x-opencode-session`** and returns `MissingSessionID` (HTTP 400) without it —
  routing is session-affine, which is why the third arm exists.
