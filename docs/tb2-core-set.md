# A core task set for moca regression rounds

Status: **proposal, pre-registered** — nothing here is measured yet. Numbers marked *(audited)*
come from `make audit` jobs, *(measured)* from agent runs in `results/jobs`, *(estimated)* from
registry manifests. Written 2026-10-27, before any run of the candidate cells.

## The question this set must answer

> Did moca's release change its capability on Terminal-Bench-style work, or did the number move
> because cells are noisy?

The 24-cell comparison set cannot answer that. Measured twice with all four agents
(`cab-subset-20261025-174057-3299781`, `cab-subset-20261026-134414-1158148`):

- **13 of 96 cells flipped** between two identical runs — one cell in seven.
- Only **6 of 24 cells discriminate** at all (per-agent pass rate spread ≥ 1 run). Of those,
  two are already excluded task-side (`configure-git-webserver`, `filter-js-from-html`).
- The other 18 are saturated (every agent passes both runs) or dead (every agent fails).
- 24 cells × 1 attempt carries a 95 % CI of ±17 points; a one-cell effect is invisible.

So the instrument is measuring a set where the signal lives in **4 usable cells**, and the noise
is 13.5 %. More repeats of that set buy precision on a number that cannot move.

## Selection rules (fixed now, before the data arrives)

A cell joins the core set only if **all** of these hold:

1. **Hermetic** — the verifier does not fetch code or packages at verification time.
   *(A cell all four agents passed 8/8 went to `oracle 0/3` in a day because its verifier cloned
   upstream and asserted that project's suite — `build-cython-ext`.)*
2. **Healthy** — `oracle` passes and `nop` fails *(audited)*.
3. **Discriminating** — at least one agent's pass rate differs from another's by ≥ 1 run at the
   final k, on evidence from the screening sweep, not from one trial.
4. **Cheap** — image < 1 GB compressed and no > 900 s timeout; the whole set must fit on one
   96 GB host alongside four concurrent agents.
5. **Stable** — passes at the same rate across repeats; a cell that flips for a single agent in
   two identical runs is not a measurement, it is a coin.

Nothing joins because it "looks hard". A cell that every agent fails is a task-side finding until
proven otherwise, and a cell that every agent passes is a floor check, not a discriminator.

## Phases

### Phase 1 — screening sweep (the input this proposal is missing)

21 healthy audited cells have **never been run with an agent**. They are all small:

| | |
|---|---|
| cells | 21 |
| image size, all 21 | **3.8 GB compressed** *(estimated)* |
| agents | moca + pi (the two cheapest legs; pi is the second opinion) |
| attempts | 1 |
| expected spend | ≈ **$0.65** *(estimated, at the measured $0.015/task)* |
| wall clock | 3–5 h at concurrency 2 |

`docs/tb2-screen2.txt` is the list. Result: a pass/fail matrix over 21 fresh cells, which is what
turns "discriminating" from a guess into a rule.

### Phase 2 — lock the core set

Target **12–16 cells** built from:

- the 4 known discriminating, healthy cells *(measured)*:
  `large-scale-text-editing` (moca 0/2, opencode 1/2, pi 1/2, claude 2/2),
  `overfull-hbox` (0/2, 1/2, 2/2, 2/2),
  `sanitize-git-repo` (1/2, 1/2, 0/2, 2/2),
  `dna-insert` (1/2, 2/2, 2/2, 1/2);
- the cells Phase 1 finds discriminating;
- **3 canaries** — cheap, always-pass cells whose only job is to prove the harness, credentials
  and image pulls worked (`kv-store-grpc`, `fix-git`, `log-summary-date-ranges`). A canary that
  fails invalidates the round; it never counts as a moca result.

Explicitly **excluded**, with reasons:

| cell | reason |
|---|---|
| `configure-git-webserver` | verifier passes on a leftover artifact from the agent's own smoke test (`docs/task-side.json`) |
| `filter-js-from-html` | byte-exact assertion no agent has ever passed, 0/5 and 0/6 (`docs/task-side.json`) |
| `build-cython-ext` | verifier clones upstream and asserts *its* suite; `oracle 0/3` (2026-10-27) |
| `mteb-*`, `hf-model-inference`, `pytorch-model-recovery` | 15–21 GB images; cost, not capability, and they measure environment plumbing |
| the 8 audited `broken-task` cells | reference solution fails as shipped |

### Phase 3 — the round

- **k = 3 attempts** per cell per agent. At the measured flip rate, one attempt per cell cannot
  separate a release change from a bad draw; three can, and 12 cells × 3 = 36 trials keeps the
  bill near one current 24-cell sweep.
- **Agents**: all four when the question is cross-agent ranking; **moca + one comparator** when
  the question is "did moca regress" — that is the cheap 2-agent configuration
  (≈ 12 × 3 × 2 = 72 trials, ≈ $1.10 zen *(estimated)*).

## The acceptance rule (pre-registered, not tuned after seeing the result)

Primary metric: **cells solved**, pooled over k attempts per cell and then paired by task.

| verdict | rule |
|---|---|
| **regressed** | paired Δ(moca_new − moca_prev) ≤ −2 cells **and** the task-clustered bootstrap 95 % CI excludes 0 **and** exact McNemar p < 0.10 on discordant cells |
| **improved** | symmetric, Δ ≥ +2 cells |
| **no change detected** | otherwise — reported as "no change detected at this power", never as "unchanged" |
| **invalid round** | any canary fails, or the manifest differs from the previous round's in harness/python/toolchain |

Secondary metric: **test-pass credit** from `verifier/ctrf.json`, reported beside the binary score
but never substituted for it. Measured on the 24-cell set, credit narrowed a 16.6-point binary
spread to 4.9 — binary overstates differences that are one assertion deep.

Both numbers are published with the round: Δ, CI, discordant pair counts, McNemar p, and the
number of cells the design could have detected (±1 cell = ±8 pts at 12 cells).

## Cost and disk

| configuration | trials | zen cash *(measured rates)* | Claude API-eq | image disk |
|---|---|---|---|---|
| Phase 1 screen (21 cells × 2 agents × 1) | 42 | ≈ $0.65 | — | 3.8 GB |
| core round, 2 agents × k=3, 12 cells | 72 | ≈ $1.10 | — | ~2 GB |
| core round, 4 agents × k=3, 16 cells | 192 | ≈ $2.30 | ≈ $18 | ~3 GB |

Either core round costs less than one 24-cell sweep today ($1.6 zen + $10.5 Claude-eq) and leaves a
CI narrow enough to call a two-cell change. That is the trade: **fewer cells, more repeats, on
cells where the answer can differ.**

## What would change this plan

- Phase 1 finds fewer than 8 discriminating cells → the honest conclusion is that Terminal-Bench
  2.0's public set is saturated for these four agents, and the bench should move to a different
  signal (cost/turns per solve on hard cells, or a private task set), not to more repeats.
- A canary fails in the round → investigate the harness before reading any cell.
- A cell's verdict flips between two rounds at k=3 → it does not belong in the core set; demote it
  and record why.
