# Timeout contract

Diagnostic layer only. **`atomic_correct` is the hidden verifier**, not this classifier. Official run protocol: [`STANDARD.md`](STANDARD.md).

Do not treat every `AgentTimeoutError` as “cannot do this item.” Harbor’s 180s wall clock wraps the whole `agent.run()` (LLM wait, LiteLLM retries, Novita commands). The same exception name covers infra stalls, empty-spin TLE, and “artifact already correct but Terminus-2 did not halt.”

Analogues: contest TLE ≠ WA ≠ System Error; LiveCodeBench `-3` vs `-2` vs runner error; Inspect SWE-bench `ERRORED` (retry) vs failed patch; Harbor still runs the verifier after timeout.

Public tables report **two numbers**, not one blended lie:

1. **Atom score** — verifier artifact (`reward`).
2. **Timeout / halt rate** — tagged separately.

## Clock (locked)

- Agent timeout stays **180s** except the few tasks that already set 240/300.
- Build is a separate 600s clock.
- `BuildException`: Harbor `--max-retries 1 --retry-include BuildException`.
- `AgentTimeoutError` is **not** retried by Harbor. This repo retries only after a **stall** classification.
- Qwen3 runs with thinking **off**. A long think looks like a stall and would be retried wrongly.

## Outcomes

| Class | Detect | Atom score | Tag |
|---|---|---|---|
| Pass | reward 1.0, no timeout | 1 | — |
| Pass, did not halt | reward 1.0 **and** `AgentTimeoutError` | **1** | `timeout_after_pass` |
| Task miss | reward 0, no timeout | 0 | `task_miss` |
| Loop timeout | timeout, reward 0, spinning | **0** | `timeout_loop` |
| Stall timeout | timeout, reward 0, infra hang | discard, rerun **once** | discarded: `timeout_stall` |
| Stall exhausted | replacement also stall | 0 | `timeout_stall_exhausted` |
| Infra | `BuildException` / setup | Harbor retry / discard | `infra` |

**Artifact wins.** `timeout_after_pass` is an atom pass. Terminus-2 only exits after `task_complete: true` twice; a model can write a correct file and then loop on invalid JSON. That is a halt/protocol failure, not “cannot edit.”

## Stall vs loop (high precision)

Operate on each timed-out trial `result.json`. Ambiguous → **loop**. Do not retry loops.

**If reward is 1.0:** `timeout_after_pass`. Keep. Do not rerun.

**Stall** (reward 0) if any of:

- no completed LLM call (`n_episodes` ≤ 1 and no `api_request_times_msec`), or
- `n_episodes ≤ 8` and `max(api_request_times_msec) ≥ 30000`, or
- `n_episodes ≤ 3` and agent execution ≥ 150s, or
- timeout in `_execute_commands` and `n_episodes ≤ 8` and sum(API times) < 60% of agent wall time.

`python scripts/run_locked.py` retries a stall **once** (60s wait), then keeps the replacement. Loops and after-pass are not retried.

**Otherwise:** `timeout_loop`. Keep as atom 0. Do not rerun.

If the stall replacement times out: classify again. Second stall → `timeout_stall_exhausted` (not a `task_miss`). Second loop → `timeout_loop`.

## Difficulty / Hard

- Do **not** mint Hard from `timeout_loop`, `timeout_after_pass`, or `timeout_stall_exhausted`.
- Hard still needs a stable **task_miss** (wrong artifact) on the target band, plus 27B pass.
- `k=1` `timeout_loop` is not “cannot finish this item.” Same noise rule as a single 9B zero. Prefer `k=3` before locking a time-to-finish claim.

Classifier: `python scripts/classify_timeouts.py jobs/<job>`.

## Classified jobs (no new LLM calls)

| Job | Atom mean | after_pass | loop | stall | task_miss |
|---|---|---|---|---|---|
| 9B rest `2026-08-22__23-55-17` | 0.974 | 0 | 0 | 0 | 1 |
| 8B rest `2026-08-23__00-05-01` | 0.718 | 5 | 6 | 0 | 4 (+1 RuntimeError) |
| Granite unique-trap `2026-08-23__01-29-00` | 0.404 | 2 | 10 | 0 | 18 |

No stalls on these jobs, so no replacement runs. Granite is a draft leaderboard row, not a locked calibration band.
