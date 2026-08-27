# Difficulty policy (empirical)

Thesis: do **not** aim for everyone to score 50%. Measure what 3B–9B agents can and cannot do, then find the boundary against a larger ruler.

- **Core** (Medium): discriminate *inside* 3B–9B. 9B may sit near the ceiling. That is in-band.
- **Frontier** (Hard): v1.0 observed 9B 0/3, and 27B or 34B Atomic 3/3. Separate table.
- Labels come from the calibration ladder, not from “this trap looks hard,” a single 9B zero, or a desire to suppress scores.
- Do not break atomicity (exact loc set, hidden edit tests, testgen mutants, repro dual-state, unique review bit) to manufacture a lower mean.

This is not Terminal-Bench 3 / SWE-bench: those may keep items that no current LLM solves, because difficulty is anchored on humans. We do not.

## Calibration ladder

| Role | Model | Harbor id | On the 3B–9B leaderboard? |
|---|---|---|---|
| Floor | Ministral 3B | `openrouter/mistralai/ministral-3b-2512` | appendix only |
| Target | Qwen3.5-9B | `openrouter/qwen/qwen3.5-9b` | yes |
| Target peer | Ministral 8B | `openrouter/mistralai/ministral-8b-2512` | yes |
| Ceiling (label only) | Qwen3.5-27B | `dashscope/qwen3.5-27b` (also `openrouter/qwen/qwen3.5-27b`) | **no** |
| Ceiling (optional) | 34B-class ruler | not pinned yet | **no** |

27B / 34B are rulers, not laptop-small results. Current Hard labels use 27B. A 34B pin can confirm Frontier; it does not enter the 3B–9B Core table. The old Groq 27B 4/4 was appendix terminal tasks only; it does not calibrate atomic Hard.

Always: oracle = 1, nop = 0. That is solvability, not a difficulty band.

## Label rules (per trap; mean of surfaces)

| Label | Rule | If it fails the rule |
|---|---|---|
| **Medium** (Core) | Target band (8B or 9B) can pass | Stays Medium; do not move it to Hard to lower 9B |
| **Hard** (Frontier) | v1.0 9B 0/3 **and** 27B or 34B Atomic 3/3 | Do not call it Hard |
| **Out-of-range** | 9B 0/3 in v1.0 and 27B is not 3/3 | Not an ordered band above Hard; still scored |
| **Easy** | Floor (3B/4B) already Atomic≥1 once, and 9B 3/3 | Floor-reachable; still scored |

Published 62 under compact-shell k=3 (canonical coverage, 2026-08-27): **Easy 12, Medium 38, Hard 7, Out-of-range 5**. 57 items have empirical labels; 5 stay out of the ladder and still enter the mean. k=3 is an observation (0/3 or 3/3), not a proof of p=0 or p=1. Regenerated from `results/v1.0.1_difficulty.json`; v1.0 freeze was Easy 10 / Medium 40 / Hard 6 / Out-of-range 6.

### v1.0.1 task lists

**Easy (12):** `loc-unused-fix`; Edit `covered-length`, `deep-merge`, `prefix-sums`, `timeout-zero`, `retry-discount`; Testgen `timeout-zero`, `cents`; Review `slug-almost`, `slug-complete`, `rotate-right`, `bare-except`. Two Easy items come from Hard-15 floor hits: `edit-retry-discount` (Ministral-3B), `review-bare-except` (Gemma-4B).

**Hard (7):** `loc-member-discount`, `loc-vip-two-files` (27B Clean 0/3), `testgen-anagram`, `repro-first-index`, `repro-whitespace`, `loc-hook-plugin`, `repro-nested-alias` (27B Artifact 3/3 after infra a3; previously 2/3).

**Uncalibrated / Out-of-range (5):** 27B 0/3: `loc-bind-host`, `loc-reexport`, `loc-env-wrapper`. 27B 1/3 or 2/3: `loc-vendor-shadow`, `edit-config-beside`.

**Medium:** the remaining 38. `loc-traceback-helper` is 9B 3/3, 27B 0/3, still Medium (3B/4B never hit). `loc-failing-test-impl` is 9B 3/3 after infra replacement.

Do not mint Hard by relaxing Loc from exact-set to subset. Public ranking tables live in [`结果报表.md`](结果报表.md); this file keeps the item names.

An item that everyone in 3B–27B passes stays in the set as smoke, not as Hard.

`k=1` is noisy. A single 9B zero does not mint Hard. Prefer `k=3` on loc before locking a label.

Pilot jobs below **do not enter the Standard Track table**. Official protocol: [`STANDARD.md`](STANDARD.md). Timeouts are **not** task misses ([`TIMEOUT.md`](TIMEOUT.md)); do not mint Hard from TLE or halt failures.

## What this changes from the old policy

Old: Hard = loc exact-set decoys and review example-satisficing, because 9B dropped.  
New: those are **constructs** (how the trap is written). They are **candidate** items until the ladder assigns Easy / Medium / Hard / Out-of-range.

- Do not add Hard edit / testgen / repro unless 9B fails that construct and 27B passes.
- Do not relax loc from exact set to subset in order to manufacture a passer. If 27B fails exact-set, the item is **Out-of-range**, not “fixed” by a weaker metric.
- Author `difficulty = "hard"` in `task.toml` is a construct tag only. Public tables use this file.

## Calibration results (2026-08-22)

Ruler: Terminus-2, `dashscope/qwen3.5-27b`, thinking off, `k=1 n=1`. Failures below are task errors (answer written), not timeouts.

### Planned shots

| Task | 9B (prior) | 14B (prior) | 27B | Band |
|---|---|---|---|---|
| `loc-hardcoded-digital-vat` (L9) | 0 (decoy / extra file) | 0 (gold + extra tax modules) | 0: gold `resolve.py` **plus** decoy `tax/digital.py` | **Out-of-range** (not in published 62) |
| `review-dollar-cents` (V9) | 1 (ran `0.29`) | — | 0: wrote `1` (example-satisficing) | **not Hard**; 9B already passed once, 27B k=1 miss |

L9 stays in the task bank as a diagnostic: even the ceiling over-reports the dead RATE file. Do not name it Hard. Do not weaken exact-set to create a passer.

### Extra loc map (ceiling only, k=1)

| Task | 27B | Note |
|---|---|---|
| `loc-member-discount` (L1) | 1 | 9B also 1 on the v0 slice |
| `loc-bind-host` (L2) | 1 | 9B `k=3` = 2/3 → Medium, not Hard |
| `loc-vip-two-files` (L3) | 1 | |
| `loc-similar-filenames` (L4) | 1 | |
| `loc-traceback-helper` (L5) | **0/3** (Novita serial, thinking off; no exceptions) | listed `data/records.txt`, missed `codec.py`. Ceiling also fails |
| `loc-failing-test-impl` (L6) | 1 | |
| `loc-reexport` (L7) | **2/3** (k=1 extra `pkg/net.py` was noise) | |
| `loc-unused-fix` (L8) | 1 | |

### compact-shell k=3 lock (2026-08-25)

Official agent. Source: `jobs/locked-core-k3.json` (477 cells, `n_valid=3`). Hard = Qwen3.5-9B **0/3** and Qwen3.8-27B Atomic **3/3**. Not “all 10 main fail.” Do not use Terminus-2 rows below to override this.

| Task | 9B | 27B Atomic | 27B E2E | Band |
|---|---|---|---|---|
| `loc-member-discount` | 0/3 | 3/3 | 3/3 | **Hard** |
| `loc-vip-two-files` | 0/3 | 3/3 | 0/3 | **Hard (Atomic)**; E2E not locked |
| `loc-similar-filenames` | 1/3 | 3/3 | 3/3 | not Hard (9B not 0/3) |
| `loc-failing-test-impl` | **3/3** | 3/3 | 3/3 | Medium (a1 was frozen 429; infra replacement Atomic 1) |
| `loc-traceback-helper` | **3/3** | 0/3 | 0/3 | **Medium**; 9B can pass (a1 was frozen 429) |
| `loc-bind-host` | 0/3 | 0/3 | 0/3 | **Out-of-range** |
| `loc-reexport` | 0/3 | 0/3 | 0/3 | **Out-of-range** |
| `loc-unused-fix` | 3/3 | 3/3 | 3/3 | Easy (floor hit; k=3 from `jobs/locked-upper-base-k3.json`) |

Keep exact-set. The two Loc Hard items stay in the frozen 47 for scoring; they are also on the Frontier table. 9B still 0/3 on `testgen-anagram`, `repro-first-index`, `repro-whitespace`. 27B Base-47 k=3 (2026-08-26, `jobs/locked-upper-base-k3.json`) is Atomic 3/3 on all three → they **lock Hard (Atomic)**. Canonical coverage 2026-08-27 additionally locks Hard-15 `repro-nested-alias` (27B Atomic 3/3 after infra a3; previously Out-of-range at 2/3). Two Hard-15 items are Easy under the floor rule: `edit-retry-discount`, `review-bare-except`.

### Next

Terminus-2 L5/L7 27B `k=3` does not replace the compact-shell screen. Under compact-shell, `loc-bind-host` and `loc-reexport` are **Out-of-range**; `loc-traceback-helper` is Medium (9B 3/3 after infra replacement).

### Target loc profile (2026-08-22)

Terminus-2 calibration **only** (not compact-shell). OpenRouter, `n=1`. 9B = `qwen/qwen3.5-9b`. 8B = `mistralai/ministral-8b-2512`. L2/L5/L7 (and 9B L3) used `k=3`; other loc `k=1`. Published Hard labels are in the compact-shell k=3 table above.

| Task | 9B | 8B | 27B | Band |
|---|---|---|---|---|
| L1 `loc-member-discount` | 1 (k=1) | 0 timeout | 1 | Medium for 9B; 8B loc floor |
| L2 `loc-bind-host` | **2/3** (fail = extra `netutil.py`) | **0/3** (2× extra `netutil.py`, 1 timeout) | 1 | **Medium**, not Hard. v0 9B k=1 zero was noise |
| L3 `loc-vip-two-files` | k=1 missed `checkout.py`; **k=3 = 3/3** | 0 (listed 5 files) | 1 | Medium for 9B |
| L4 `loc-similar-filenames` | 1 | 0 (`app/repo/` prefixes + extras) | 1 | Medium for 9B |
| L5 `loc-traceback-helper` | **1/3** (2× `data/records.txt`) | **0/3** (gold plus wrapper/data/prefixes) | **0/3** | Not Hard (ceiling `k=3` also 0). 9B unstable |
| L6 `loc-failing-test-impl` | 1 | 0 (listed `invoice.py` not `tax.py`) | 1 | Medium for 9B |
| L7 `loc-reexport` | **2/3** (fail = extra `pkg/net.py`) | **0/3** (2 timeouts) | **2/3** | Not Hard. 9B can pass; 27B `k=1` zero was noise |
| L8 `loc-unused-fix` | 1 | 0 timeout | 1 | Medium for 9B |
| L9 `loc-hardcoded-digital-vat` | 0 (prior) | — | 0 | Out-of-range (not in published 62) |

**Loc cutoff (Terminus-2, 2026-08-22):** Ministral 8B does not close exact-set loc (0/8 this run). Qwen3.5-9B closes most loc traps under that harness. **That is not the published table.** compact-shell k=3 locks two Hard loc items (`loc-member-discount`, `loc-vip-two-files`); see the lock table above.

### Target rest profile (2026-08-22)

Terminus-2, OpenRouter, Novita `-e novita -n 5`, `k=1`. 39 unique-trap tasks (edit 12, testgen 10, repro 10, review 7). Jobs: `jobs/2026-08-22__23-55-17` (9B, 9m 42s) and `jobs/2026-08-23__00-05-01` (8B, 18m 35s).

| Atom | 9B | 8B |
|---|---|---|
| Edit | **12/12** | **11/12** (`edit-hhmmss` `timeout_loop`) |
| Testgen | **9/10** (`testgen-gregorian` 0) | **7/10** (`cents`/`parse` `task_miss`; `gregorian` RuntimeError) |
| Repro | **10/10** | **6/10** (3 `timeout_loop`; `float-cents` `task_miss`; 3 `timeout_after_pass` already in the 6) |
| Review | **7/7** | **4/7** (2 `timeout_loop`; `configured-timeout` `task_miss`; `slug-complete` `timeout_after_pass` already in the 4) |
| **Total** | **38/39** (mean 0.974) | **28/39** (Harbor mean 0.718) |

Timeout classification (`python scripts/classify_timeouts.py`, rules in [`TIMEOUT.md`](TIMEOUT.md)):

| Job | Atom mean | `timeout_after_pass` | `timeout_loop` | `timeout_stall` | `task_miss` |
|---|---|---|---|---|---|
| 9B rest `jobs/2026-08-22__23-55-17` | 0.974 | 0 | 0 | 0 | 1 (`testgen-gregorian`) |
| 8B rest `jobs/2026-08-23__00-05-01` | 0.718 | **5** (already reward 1.0) | **6** | **0** | 4 + 1 `RuntimeError` |
| Granite 8B unique-trap `jobs/2026-08-23__01-29-00` (draft, 47 tasks) | 0.404 | 2 (`edit-pad-left`, `repro-whitespace`) | 10 | **0** | 18 |

8B rest: Harbor listed 11 `AgentTimeoutError`. Five of those are `timeout_after_pass` (artifact already correct; halt failed). Six are `timeout_loop` (empty-spin TLE). Zero stalls, so no rerun. Genuine `task_miss`: `repro-float-cents`, `review-configured-timeout`, `testgen-cents`, `testgen-parse`. `testgen-gregorian` is `other_error` (tmux/RuntimeError), not a timeout.

**Rest cutoff (Terminus-2):** 9B saturates edit / repro / review and, after `k=3` on gregorian, testgen too. That zero was noise. **Not Hard.** Do not mint Hard from `timeout_loop`. compact-shell k=3 still has three 9B 0/3 rest items (`testgen-anagram`, `repro-first-index`, `repro-whitespace`) without a 27B k=3 fill — leave them unlocked.


