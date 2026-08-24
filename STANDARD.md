# Standard Track protocol

Thesis: this bench does **not** chase a 50% mean. It asks what 3B–9B coding agents can and cannot do, and where that band ends against a larger ruler.

- **Core** (published 3B–9B table): unique-trap Medium items that discriminate *inside* 3B–9B.
- **Frontier / Hard**: items where 9B *stably* fails and 27B or 34B *stably* passes. Separate table. Do not invent Hard by weakening atomicity, hiding tests, or adding harness intelligence.
- Large models are rulers only. They do not enter the small-model Core table.

This bench measures **model performance under a fixed minimal shell harness**, not intrinsic coding ability. The candidate Standard agent is `compact-shell` (`agents/compact_shell.py`). Terminus-2 is a **comparison harness**, not the published measurement object.

Say: “Qwen 9B Localization success rate under CompactShell is 75%.” Do not say: “Qwen 9B Localization ability is 75%.” Do not treat Terminus-2 calibration jobs as the official table.

Old 8B / 9B / 27B / Granite jobs are **pilot / calibration only**. They do **not** enter the official leaderboard. Formal tables are rerun from a frozen protocol.

Internship / public writeup: [`EVAL-NOTE.md`](EVAL-NOTE.md). Release checklist: [`GATE-A.md`](GATE-A.md).

Public **Core set** = **47** unique-trap Medium tasks in [`README.md`](README.md). L9 and isomorphs stay diagnostic / stock; they are not in the five-skill means. Do not blur 47 with 51. Frontier is empty until an item clears the Hard ladder in [`DIFFICULTY.md`](DIFFICULTY.md).

## Tracks (do not mix)

| Track | What it is | Runtime | Enters published 3B–9B table? |
|---|---|---|---|
| **Calibration / Pilot** | Existing OpenRouter / DashScope / Novita `-n 4|5` jobs | Provider APIs | **No** |
| **API Standard** | Protocol frozen; GPU not ready | OpenRouter + fixed model ids, thinking policy below, **k=3 n=1** | Internal only; label **API** |
| **Local Reference** | Publish / cite this | Self-hosted **vLLM** + pinned HF revision + pinned **compact-shell** | **Yes** (models advertised ≤9B) |
| **Ruler** | 27B / 34B ceiling for Core / Frontier / Unscored | DashScope or vLLM; thinking off | **No** (not laptop-small) |
| **Frontier** | Hard items: 9B stable fail, 27B or 34B stable pass | Same harness as the Core run | **No** (boundary table only) |
| **Reasoning** | Cannot disable thinking | Separate table | **No** (not Standard) |
| **Upper-small** | 12B–14B | Same harness as the track they were run on | Appendix only |

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

Skill mean:

\[
S_{\mathrm{atom}} = \frac{1}{N_{\mathrm{atom}}} \sum p_i
\]

**Primary table (Core):** Localization, Editing, Testgen, Repro, Review on the 47. No forced overall rank. A high 9B Core score is expected if Medium items are in-band; that is not a defect.

**Frontier table:** same five atoms on locked Hard items only. Empty until calibration finds a stable 9B-fail / 27B-or-34B-pass boundary. Do not merge Frontier into the Core mean to pull 9B toward 50%.

**Secondary table:** clean halt rate, TLE rate, timeout-after-pass, protocol error rate, public-green / hidden-red (edit), loc overprediction (canonical set ⊃ gold).

**Order:** freeze the 11-model roster in [`models.lock.yaml`](models.lock.yaml) (10 main + Qwen3.8-27B ruler). Pin OpenRouter `provider.order` with `allow_fallbacks=false`. Ten-model full run: `python scripts/run_locked.py --run --full --group main` (protocol 20, then MAIN_47 470). Restart skips completed cells. `--group all` adds the ruler. Batch 1/2 is execution order only; do not swap models after seeing scores. Existing 9B/8B `run_core_k1.py` jobs are draft. A published Standard table is still **k=3 on Core**, not this k=1 matrix.

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

Deterministic extract of a unique `0`/`1` (see `scripts/std_normalize.py`):

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

**Gate A — freeze protocol / optional API Standard**

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
- [ ] `k=3`, `n=1`, 180s after the Core screen (published table, not the screen)
- [x] Retry whitelist only (infra via Harbor `--retry-include`; stall retried once in `run_locked.py`; never swap provider)
- [x] `atomic_correct` / `termination` recorded — `scripts/score_standard.py`
- [x] Old pilot / Terminus-2 jobs **excluded** from the published table
- [x] Benchmark git tag `benchmark-v1.0-rc1` (local; compact-shell is the official agent)

**Gate B — published Local Reference**

- [ ] Gate A
- [ ] Per-model HF revision + vLLM / Transformers pins
- [ ] Thinking off when a toggle exists
- [ ] Untoggleable reasoners excluded from Standard

After the tag: do not silently edit instruction or verifier. Scoring semantics change → `v1.0` → `v1.1` or rerun the whole table.

## Difficulty labels

[`DIFFICULTY.md`](DIFFICULTY.md) still assigns Medium / Hard / Unscored from the calibration ladder. Those labels used pilot jobs. Do not mint Hard from TLE. A later Local Reference may **reconfirm** bands; it does not rewrite history of the pilot.

## What this repo must not do yet

- The 10-model k=1 matrix and the 27B ruler are done. Do not start a second Novita job while one is running. Command remains `python scripts/run_locked.py --run --full --group main` (resume skips completed cells).
- Do not choose models from scores. Do not mint Frontier / Hard from k=1 all-0 Loc or from the four 27B-only loc passes.
- Do not mix Calibration jobs or the k=1 screen into a published Standard mean.
- Do not keep polishing the stall classifier as if it were the scorer.
