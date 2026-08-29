# Standard Track protocol

Thesis: this bench does **not** chase a 50% mean. It asks what 3B–9B coding agents can and cannot do, and where that band ends against a larger ruler.

- **Core** (published item bank): **62** = construct Easy 17 / Medium 21 / Hard 24; empirical bands Easy 12 / Medium 38 / Hard 7 / Out-of-range 5. The headline is a 0–100 difficulty-weighted score within each skill, followed by a five-skill macro. Hard-Release-15 was run on 6 examinees (including 9B). The other 6 compact models did not sit those 15 items; the **published v1.0 mean imputes them as 0** (marked). Lock files still omit those cells. The 47-item table is the same-item panel without imputation.
- **Frontier / Hard** (ladder label): items where v1.0 observed 9B 0/3 and 27B or 34B Atomic 3/3. They **stay inside Core 62** and enter the mean. Do not invent Hard by weakening atomicity, hiding tests, or adding harness intelligence.
- Large models are rulers. They appear on the published Core-62 table as contrast. They do **not** enter the compact-10 rank.

This bench measures **end-to-end agent reliability under a frozen text-only compact-shell protocol**, not coding intelligence detached from a harness. A score is a **system** number: model + pinned OpenRouter provider/quant + Novita sandbox + compact-shell. It is procedurally fair (same grammar, budget, verifier, k=3). It is **not** a matched-weights table (providers, BF16/FP8, chat templates, and serving stacks differ).

**v1.0 published track = API Standard.** Cite it as an API system table. Local Reference (pinned HF revision + vLLM) is a later **weight-control** experiment; it is not a prerequisite for this tag and does not overwrite the frozen API mean.

Say: “Qwen 9B Localization success rate under CompactShell is 75%.” Do not say: “Qwen 9B Localization ability is 75%.” Do not say the API table proves one checkpoint’s inherent code skill is below another. Do not drop `protocol_error` / halt from the Atomic mean to “correct” a model. Do not treat Terminus-2 calibration jobs as the official table.

Legal protocol limits (declare; do not change for v1.0 because a larger model scored low): one `bash` fence per turn; no XML/native tool calls; `max_turns=20`; 180s wall clock **includes** LLM wait; Loc must write `/app/answer.txt`; Repro must exit non-zero on the buggy repo. **`finish` is required for E2E / `termination=clean`, not for Atomic.** Unfinished episodes with a correct artifact stay `atomic_correct=1`. Published E2E is **halt compliance** (Atomic ∧ clean `finish`), not “atomic skill end-to-end.” Do **not** add a finish sentence to every `instruction.md` to pretty up E2E; that is a v1.1 / sensitivity experiment. `finish` is taught only in `SYSTEM_PROMPT`; task text never mentions it; the parser requires an empty ` ```finish ` fence (body inside the fence does not count). Trace audit of 99 Atomic=1 unfinished trials: 0 missed empty-finish parses; most keep acting, pytest-loop, or rewrite to the turn cap. Gemma-12B pays the halt tax (13/47 Atomic successes also clean-finish). 9B does not (140/146). See [`EVAL-NOTE.md`](EVAL-NOTE.md) §14.

A protocol **bug** would be: instruction vs verifier contradiction; correct artifact scored 0; per-model budgets; parser not matching the documented grammar; silent provider fallback; infra counted as a task 0; crossed attempts. None of those are in evidence. Changing turns, parser, finish, Repro contract, or Atomic rules after seeing Hard-15 would start a new experiment. Sensitivity (looser protocol, Local vLLM) is a later track; it does not overwrite the frozen mean.

Old 8B / 9B / 27B / Granite jobs are **pilot / calibration only**. They do **not** enter the official leaderboard. Formal tables are rerun from a frozen protocol.

Internship / public writeup: [`结果报表.md`](结果报表.md). Process notes: [`EVAL-NOTE.md`](EVAL-NOTE.md). Release checklist: [`GATE-A.md`](GATE-A.md).

Public item bank = **62** (construct Easy 17 / Medium 21 / Hard 24; empirical Easy 12 / Medium 38 / Hard 7 / Out-of-range 5). Weighted skill scores cover every item in the atom (Loc 11, Edit 15, Testgen 13, Repro 13, Review 10). Published Core-62 (tag `benchmark-v1.0`) imputes Hard-15 as 0 for the 6 compact models that were not official Hard examinees (**marked**; the official Hard lock still omits those cells). Completeness for those 6 is `jobs/locked-hard-floor-k3.json` (does not overwrite the official Hard lock). 9B *did* sit Hard-15 (Atomic 30/45). The **current reading table** is the 16-model v1.0.1 canonical matrix in [`results/leaderboard.md`](results/leaderboard.md) / `results/canonical-coverage.json` (Hard filled + Gemma-4B 429 overlay + 13 infra replacements + four-model supplement; `remaining_dirty` 0). The 47-item table is the actually-sat compact panel.

## Tracks (do not mix)

Empirical **run** tracks (what was actually executed):

| Track | Models | Items | Product | Enters published Core-62? |
|---|---|---|---|---|
| **Compact Main** | 10 `compact_dense` | Base-47 | `jobs/locked-core-k3.json` | Base stratum; Hard missing for floor models |
| **Upper Reference** | 27B + 35B-A3B | Base-47 | `jobs/locked-upper-base-k3.json` | Base stratum for rulers |
| **Hard Evaluation** | 6 pre-selected | Hard-15 | `jobs/locked-hard-release-k3.json` | **Yes** — pooled with Base-47 for those 6 |
| **Hard-floor** | 6 skipped compact | Hard-15 | `jobs/locked-hard-floor-k3.json` | Completeness only; not the v1.0 headline |
| **v1.0.1 supplement** | GPT-OSS-20B / Nemotron-3.5-Lightning / GLM-4.7-Flash / Gemma-4-26B-A4B | Full 62 | `jobs/supplement-2026-08-k3.json` | **Yes** — append-only canonical layer |

Published Core-62 Atomic/E2E is Base-47 + Hard-15. Six examinees (including 9B) have measured Hard-15 in the official Hard lock. The other six compact models are **imputed 0 on those 15** in the v1.0 published 62 mean (marked). Completeness later sat those 15 and wrote `locked-hard-floor-k3.json`. Do not write that all 12 models are official Hard examinees. Do not copy floor rows into `locked-hard-release-k3.json`.

Evidence **grade** tracks:

| Track | What it is | Runtime | Cite as |
|---|---|---|---|
| **Calibration / Pilot** | Existing OpenRouter / DashScope / Novita `-n 4|5` jobs | Provider APIs | Not official |
| **API Standard (v1.0)** | Protocol frozen; OpenRouter ids + thinking policy + **k=3 n=1** | OpenRouter + Novita | **Published system table**; label **API** |
| **Local Reference** | Pinned HF revision + vLLM + compact-shell | Self-hosted | Future weight-control; not required for v1.0 |
| **Ruler** | 27B / 35B-A3B ceiling for Core / Frontier / Out-of-range | Same API harness | **No** (not in compact-10 mean) |
| **Frontier** | Hard items: v1.0 9B 0/3, 27B Atomic 3/3 | Same harness | **No** (boundary table only) |
| **Reasoning** | Cannot disable thinking | Separate table | **No** |
| **Upper-small** | 12B–14B | Same harness as the track they were run on | Appendix / Compact Main if they are in the 10 |

Chat templates still differ by family. Local Reference pins **per-model** `{revision, dtype, chat template, max_len, sampling}` and a **runtime family** (vLLM + Transformers versions). It does not pretend one template fits all.

## Standard / Non-reasoning inference

```
temperature    0
top_p          1
timeout        180 s (task 240/300 exceptions stay)
k              3
n_concurrent   1
agent          compact-shell (agents/compact_shell.py, pinned version)
tools / prompt frozen ```bash``` / ```finish``` grammar; no JSON tools
```

Runtime is Novita + compact-shell (`python scripts/run_compact.py`). Terminus-2 is not the Standard agent. Optional wall-clock cap is `max_turns=20`. Hidden verifier still grades the frozen sandbox. Do **not** auto-stop because the repo looked idle.

Thinking:

- Qwen3 / Qwen3.5 / Qwen3.8 → **off** (`reasoning.enabled: false` and `enable_thinking: false`).
- Model is instruct-only → default instruct.
- Reasoning checkpoint that **cannot** be turned off → **out of Standard**; Reasoning Track only.

OpenRouter provider is pinned in `models.lock.yaml` (`allow_fallbacks: false`). Do not let the router swap BF16/FP8/INT4.

Do not put thinking-off Qwen, default Ministral, and thinking-on Gemma on one Standard table.

Do not add planner / memory / reflection / JSON repair / hidden-test hints. Mechanism, not intelligence.

## Per-run record (orthogonal)

```
atomic_correct:          0 | 1     # hidden verifier artifact
termination:             clean | tle | protocol_error
format_compliance:       pass | fail
path_format_compliance:  pass | fail | n/a   # loc only; does not change atomic
```

Timeout → freeze sandbox → hidden verifier.

- Verifier 1 and TLE → `atomic_correct=1`, `termination=tle` (includes messy success / second `def` winning). Do not deduct style points.
- Verifier 0 and TLE → `atomic_correct=0`, `termination=tle`.
- Never `finish` and the run ended without TLE, or the episode produced only unparsed actions → `protocol_error` (halt label only; not “harness incompatible”). Parse-fail turns are observations, not a score penalty.

`hello-world` + `collect-todos` both atomic=1 and clean is **`preflight_both_pass`**, not protocol compatibility. Legacy JSON still says `protocol_pass`. Recompute real harness rates from `compact-shell.json` (`n_shell`, `n_parse_fail`, `finished`).

From the same frozen k=1 jobs, write three matrices (`python scripts/relabel_locked.py`; does not overwrite `jobs/locked-core.json`):

| Matrix | Cell | Use |
|---|---|---|
| **A** `atomic_correct` | hidden verifier 0/1 | exploratory Atomic-IRT |
| **T** `termination==clean` | clean halt 0/1 | strategy / protocol diagnosis |
| **E** A ∧ T | did it and stopped | k=1 E2E table |

Unfinished is scored 0/1, never dropped (selection bias). Infra only is missing. Fail kinds: `task_pass_clean`, `task_pass_unfinished`, `task_fail_clean`, `task_fail_unfinished`, `format_fail`, `no_attempt`, `infra_fail`. A−E is “can do, did not halt.”

Taxonomy (`timeout_loop`, `timeout_after_pass`, conservative stall) is **diagnostic only**. See [`TIMEOUT.md`](TIMEOUT.md). It must not change `atomic_correct`.

## Scoring (published)

Each main-set task, Standard run:

\[
p_i = \frac{\text{count of atomic\_correct}=1 \text{ in 3 trials}}{3}
\]

Construct difficulty is frozen independently of leaderboard outcomes:

\[
w_i = 1.0\ (Easy),\quad 1.5\ (Medium),\quad 2.0\ (Hard)
\]

Weighted skill score:

\[
S_{\mathrm{atom}} = \frac{\sum_i w_i p_i}{\sum_i w_i}
\]

Core-62 item counts (Loc 11, Edit 15, Testgen 13, Repro 13, Review 10). Skipped Hard-15 items enter as \(p=0\). Two averages are both correct; **do not mix the labels**:

| Name | Formula | Role |
|---|---|---|
| **Artifact Score (0–100)** | \(100\times(S_{\mathrm{Loc}}+S_{\mathrm{Edit}}+S_{\mathrm{Testgen}}+S_{\mathrm{Repro}}+S_{\mathrm{Review}})/5\) | Primary ranking score |
| **Task-micro** | \(\sum p_i / 62\) = successes / \((62\times 3)\) | Overall attempt rate; secondary |

**Primary table (Core):** the five \(S_{\mathrm{atom}}\) columns on all 62 items. No forced overall rank. A high 9B Core score is expected if Medium items are in-band; that is not a defect. 9B sat Hard-15 (Atomic 30/45). Floor compact models that were not official Hard examinees get \(p=0\) on those 15 in the v1.0 published table (marked). Completeness: `jobs/locked-hard-floor-k3.json`.

**Frontier table:** same five atoms; Frontier items stay inside Core 62 and still enter the mean. Do not drop them to lift 9B.

**Secondary table:** clean halt rate, TLE rate, timeout-after-pass, protocol error rate, public-green / hidden-red (edit), loc overprediction (canonical set ⊃ gold).

**Order:** freeze the 12-model roster in [`models.lock.yaml`](models.lock.yaml) (10 compact_dense + Qwen3.8-27B + Qwen3.6-35B-A3B). Pin OpenRouter `provider.order` with `allow_fallbacks=false`. Ten-model full run: `python scripts/run_locked.py --run --full --group main` (protocol 20, then MAIN_47 470). Restart skips completed cells. `--group ruler` / `--group moe` are Upper Reference, not Compact Main. Batch 1/2 is execution order only; do not swap models after seeing scores. Existing 9B/8B `run_core_k1.py` jobs are draft. A published Compact Main table is **k=3 on Core**, not this k=1 matrix.

The later four-model v1.0.1 extension is frozen separately in [`models.supplement-2026-08.yaml`](models.supplement-2026-08.yaml). It preserves the task bank, `k=3`, one independent sandbox per attempt, 20 turns, strict bash/finish parser, and disabled provider fallback. Declared API adaptations are part of those system configurations: GPT-OSS uses mandatory low reasoning with a separate retained reasoning field, and Gemma uses post-first-action stop markers. The original 12-model lock and source result files are not rewritten.

k=1 item roles (screen only): `irt_candidate` (mix of 0 and 1 — not automatically a good discriminator), `all_pass`, `uncalibrated_above_range` (all 0 — keep in the raw matrix; **do not** Rasch-MLE a finite \(b\)). Use **corrected** item-total \(r\) (total excludes the item). Do not mint Hard from all-0 Loc.

## Localization

Atomic score = **exact file set** after canonicalize:

- `\ ` → `/`
- collapse `//`
- strip `./`
- strip `/app/repo/` and `app/repo/`
- `PurePosixPath` normalize

Not subset. Extra decoy still 0 if the instruction asks for the **minimal file set that must change**. That construct is intact (`serve.py` + decoy `netutil.py` is a miss). Also record Loc precision / recall from verifier stdout (`relabel_locked.py`) so over-prediction is visible. Raw-vs-canonical mismatch is `path_format_compliance=fail` only.

## Review

This atom is **patch validation**, not full code review (style, security, maintainability). Deterministic extract of a unique `0`/`1` (see `scripts/std_normalize.py`):

Accepted if unique: `0`, `0\n`, `0 because …`, `The answer is 0`, `Answer: 0`.

`The answer could be 0 or 1` → format fail (`extract_judgment` is `None`).

```
review atomic = extracted token == label
raw_format_compliant = first token was already exactly 0 or 1
```

No LLM judge.

## Edit public vs hidden

Visible `/app/repo/tests` are debugging aids, not the spec. Reward is hidden `/tests`. Do not expose hidden cases to the agent.

## Retry whitelist (only these)

Rerun (once), log `attempt_id`, `rerun_reason`, original error:

- `BuildException` / container build failure
- Docker / Novita daemon or 5xx / connection reset
- provider rate limit
- Harbor internal exception
- verifier infrastructure crash
- host OOM unrelated to the model

**Never rerun:** wrong artifact, empty-spin TLE (`timeout_loop`), agent loop, bad JSON, missing answer, bad tool call, model-raised exception, format failure. Infra stall (`timeout_stall`) is retried **once** by `run_locked.py`.

## Gates

Do not start the 10-model k=1 matrix before Gate A oracle/nop is green.

**Gate A — freeze protocol / API Standard (v1.0 system table)**

- [x] Loc canonicalize + review extract in verifiers
- [x] Testgen isolation + repro dual-state — `scripts/test_verifier_chain.py`
- [x] `compact-shell` agent + frozen grammar (`agents/`)
- [x] 10-task compact-shell on Novita — `python scripts/run_compact.py --run <model>` (9/10; `repro-whitespace` over-edited)
- [x] Draft k=1 9B/8B screen (`jobs/core-k1-screen.json`). Not the frozen matrix.
- [x] Frozen 10-model preflight (`protocol-check.json`; rename: `preflight_both_pass`)
- [x] Frozen 10 × MAIN_47 — `jobs/locked-core.json` (470; do not overwrite). Relabel: `python scripts/relabel_locked.py`
- [x] Frozen Qwen3.8-27B ruler k=1 (49 cells merged into the same JSON; not in \(\theta\)). See EVAL-NOTE §10
- [x] Main 47 + diagnostic: Oracle = 1, NOP = 0 (harness-independent)
- [x] Thinking off for Qwen3 / 3.5 / 3.8 in `models.lock.yaml` (`reasoning.enabled=false`)
- [x] `k=3`, `n=1`, 180s: fill attempts 2–3 (`python scripts/run_locked.py --k3-fill --group main` then `--group ruler`). Pooled with attempt=1. Did not overwrite `jobs/locked-core.json`. All 477 published cells have `n_valid=3`. Table: [`EVAL-NOTE.md`](EVAL-NOTE.md) §6.2.
- [x] Retry whitelist only (infra via Harbor `--retry-include`; stall retried once in `run_locked.py`; never swap provider)
- [x] `atomic_correct` / `termination` recorded — `scripts/score_standard.py`
- [x] Old pilot / Terminus-2 jobs **excluded** from the published table
- [x] Benchmark git tag `benchmark-v1.0-rc1` (local; compact-shell is the official agent)

**Gate B — Local Reference (weight-control; not required for v1.0)**

- [ ] Per-model HF revision + vLLM / Transformers pins
- [ ] Thinking off when a toggle exists
- [ ] Untoggleable reasoners excluded from Standard
- Does **not** overwrite the frozen API mean. Changelog if the citeable track changes.

After the tag: do not silently edit instruction or verifier. Scoring semantics change → `v1.0` → `v1.1` or rerun the whole table. Changing API Standard vs Local Reference **evidence grade** is a release-note item, not a silent edit.

## Difficulty labels

[`DIFFICULTY.md`](DIFFICULTY.md) separates author-designed `construct_difficulty` from the observed `empirical_band`. Construct Easy / Medium / Hard determines weights 1 / 1.5 / 2. Empirical Hard = 9B 0/3 and 27B Atomic 3/3; Out-of-range = 9B 0/3 and 27B is not 3/3. Do not mint empirical Hard from TLE. A later Local Reference may **reconfirm** empirical bands; it does not rewrite the author tier or the API table.

## What this repo must not do yet

- Do not start a second Novita job while one is running.
- Do not choose models from scores. Do not mint Frontier / Hard from k=1 all-0 Loc.
- Do not mix Calibration jobs or the k=1 screen into a published Standard mean.
- Do not keep polishing the stall classifier as if it were the scorer.
- Do not treat the weighted five-skill score and the raw task-micro rate as the same number.
- Do not write that all 12 models are official Hard examinees. v1.0 published 62 imputes skipped Hard as 0 and marks it; do not forge those cells in `locked-hard-release-k3.json`. Completeness is `locked-hard-floor-k3.json`.
- Do not cite the API table as a matched-weights Local Reference.
