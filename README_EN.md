# SmallOWBench 2.0

**Complete RC2 results: eight configurations, 496 validated task observations.** Each configuration covers all 62 tasks once. Seven complete original configurations contribute 434 observations; the separately frozen Qwen3.5-9B configuration on PrimeIntellect BF16 contributes 62. Its 29 older Parasail observations are excluded. The new roster is accepted; the original p2 experiment remains accepted=false. [Results and skill breakdown](analysis/v2/release-20261028/RESULTS-COMPLETE-20261029.md) · [Safe task-level data](analysis/v2/release-20261028/SCORES-COMPLETE-20261029.json)

| Configuration | Artifact macro /100 | Clean macro /100 |
|---|---:|---:|
| Qwen3.5-9B · PrimeIntellect BF16 | 37.26 | 19.36 |
| Qwen3.6-35B-A3B | 30.48 | 13.95 |
| Qwen3.8-27B | 18.91 | 17.58 |
| Ministral-14B | 14.99 | 14.99 |
| Ministral-8B | 7.77 | 0.00 |
| Ministral-3B | 2.67 | 1.33 |
| Gemma-3-12B | 0.00 | 0.00 |
| Llama-3.2-3B | 0.00 | 0.00 |

[简体中文](README.md) | **English**

**2026-10-29 final status:** the complete replacement roster passed validation. The earlier shared-pool 429 failures and partial results remain historical records. The original US$40 monetary admission cap was removed by user authorization; fees and unknown reserves remain recorded. See the [fixed-provider protocol](analysis/v2/provider-recovery-20261029/PROVIDER-REASSESSMENT.md).

**Cancellation audit amendment:** one existing `testgen-anagram` execution was restored as a time-limit failure with score zero. It was not rerun; only the twelve never-started tasks continued. Original sources, ledger, visits and initial reports remain unchanged. [Audit and execution amendment](analysis/v2/provider-recovery-20261029/CANCELLATION-AUDIT-AMENDMENT.md).

SmallOWBench 2.0 is an execution-based diagnostic benchmark for compact open-weight coding agents. Its 62 authored small Python workflows cover localization, editing, test generation, bug reproduction and patch validation, with deterministic verification of deliverables. The tasks have been inspected, repaired and used during development; they do not represent an unseen holdout set, real large-repository issues or long-horizon autonomous maintenance.

**Release components: task/grader `2.0.0-rc.2`; harness `2.0.0-rc.1`. A separately validated eight-configuration roster has 496 complete task observations; the original p2 acceptance flag remains false.** The new entry point explicitly selects `task-banks/rc2/tasks`. The root `VERSION`, original `tasks` and original manifest retain their protected RC1 provenance for integrity checks and historical reproduction. Changing the root version or using an old runner does not activate the new bank.

| Skill | Tasks | Verified deliverable |
|---|---:|---|
| Localization / Loc | 11 | The complete target-file set without extra files |
| Editing / Edit | 15 | A code change that passes behavior and regression checks |
| Test Generation / Testgen | 13 | Tests that accept correct implementations and detect faulty ones |
| Reproduction / Repro | 13 | A reproducer that exposes the bug and passes after the reference fix |
| Patch Validation / Review | 10 | Verdicts and required evidence for the candidates within each task |

**Artifact** measures correct deliverables; **Clean** additionally requires a normal protocol finish. Clean is not a real-world software-development E2E success rate. Tasks are equally weighted within each skill, and the five skills are equally weighted for macro; task-micro covers all 62 tasks. Legacy empirical difficulty weights and IRT findings do not transfer. Review's 40 candidates remain nested within ten tasks.

The 2026-10-27 RC2 evidence covers **ten oracle/no-op slots across five selected tasks meeting their expected outcomes**: five reference passes and five no-op failures, plus **232 passed and one skipped** offline test. This verifies the selected paths. Full-bank RC2 container acceptance remains incomplete, and RC1's `full124` does not transfer. Image initialization builds/freezes both image roles for 62 tasks and records dependency versions; it does not add oracle/no-op evaluations or calibration. See the [public evidence summary](analysis/v2/release-20261028/PUBLIC-EVIDENCE.md).

The historical initial plan was **8 original configurations × 62 tasks × 1 repetition: at most 496 task attempts**, with an initial US$40 cap, four workers and zero whole-trial infrastructure retries. The monetary cap was later removed; the complete published roster uses seven complete original profiles plus one independent 62-task PrimeIntellect BF16 reassessment, with its separately frozen transient-infrastructure retry policy. This is not a cap of 496 HTTP requests. Budget admission or provider failures may leave missing slots; missing/infrastructure results are not model zeros. Scores must be recomputed from this run's original evidence, and incomplete data cannot produce a complete formal ranking. The [eight-route catalog check](analysis/v2/release-20261028/ROUTES.md) verifies public endpoint metadata, not sustained capacity or actual parameter enforcement. Excluded legacy models are not silently replaced with other models or precisions.

## Version 2.0 entry points and release materials

[Protocol](STANDARD-v2.md) · [Release notes](analysis/v2/release-20261028/RELEASE-NOTES.md) · [Publication checklist](analysis/v2/release-20261028/PUBLICATION-CHECKLIST.md) · [Public evidence summary](analysis/v2/release-20261028/PUBLIC-EVIDENCE.md)

The public evidence file is a redacted summary with original-file hashes and scope limits. It is not a raw report, a complete trace archive or a replacement validator input.

First follow the [pinned Harbor setup](vendor/harbor-patches/README.md): adjacent checkouts, the specified upstream commit, the supplied runtime patch and `uv sync --locked`. Use that environment's Python from this repository root with local Linux Docker. Keep model credentials in the required host environment, outside task containers and published files.

**Fresh external clone only:** if your machine has no original five-task receipts, create its local profile, ten oracle/no-op slots and transfer records in a new `r2smk` directory first. This makes no model calls; builds explicitly use networking and execution stays offline. It is an initialization option for external reproduction. **The current formal run already has these receipts and does not repeat this step.**

Cross-host portability has a known limitation: the legacy `validate_upgraded_tasks.task_digest` uses `sorted(Path.rglob(...))`, and Windows and Linux `Path` objects apply different case-ordering rules. Frozen file bytes and per-file SHA-256 lists can be checked, but cross-platform equality of the legacy aggregate directory digest has not been confirmed. A fresh Linux-host clone is therefore not guaranteed to pass the original aggregate-digest check. This run continues on Windows without changing frozen functions or values or adding a test stage.

```powershell
python scripts/validate_rc2_containers.py --directory experiments/smallowbench-v2/r2smk --execute --allow-build-network
```

Then prepare the images and freeze the formal run. The following commands document the historical initial configuration, including its original monetary cap; they do not launch the later replacement-provider protocol. New runs need fresh short directory names; existing directories must not be overwritten. Do not feed another machine's absolute-path receipts or public redacted summaries directly to the validator.

```powershell
# Image preparation and version receipts only; no task evaluations or model calls.
python scripts/build_release_v2_images.py --output experiments/smallowbench-v2/im2 --execute --workers 4 --allow-build-network

# --write persists prepare/lock/plan; prepare creates an initial STOP.
python scripts/run_release_v2.py prepare --directory experiments/smallowbench-v2/rel2 --models-file analysis/v2/models.route-ready.json --preflight experiments/smallowbench-v2/r2smk/preflight-rc2.json --runtime experiments/smallowbench-v2/im2/runtime.json --budget-usd 40 --workers 4 --max-infra-retries 0 --visit-reserve-usd 3.5 --repetitions 1 --isolate-model-infra --write
python scripts/run_release_v2.py lock --directory experiments/smallowbench-v2/rel2 --write
python scripts/run_release_v2.py plan --directory experiments/smallowbench-v2/rel2 --write
python scripts/run_release_v2.py status --directory experiments/smallowbench-v2/rel2
python scripts/run_release_v2.py analyze --directory experiments/smallowbench-v2/rel2
```

These paths require your machine's original five-task acceptance materials and new image receipts. Public redacted summaries cannot substitute for complete local evidence, and a new setup does not prove byte identity with the published run. Execution also requires a separate `authorization.json` bound to the manifest, execution lock and approved budget, and an authorized operator must handle the **new run's** initial STOP. `execute --execute --worker 0 --workers 4` starts only worker 0; a four-worker run starts workers 0–3 as separate processes. Preparation and locking do not execute models or remove historical STOP files. See the [protocol commands](STANDARD-v2.md#入口) for execution syntax.

## Legacy introduction and results — not 2.0 scores

**The entire introduction, scoring weights, figures, model results and run examples below are historical.** Legacy tasks are archived; matching IDs do not make old and new scores comparable. Version 2.0 uses a separate experiment namespace and never resumes the old matrix. The `run_locked.py`/Novita examples below are not Version 2.0 release entry points.

[![Leaderboard](https://img.shields.io/badge/leaderboard-v1.0.1-0f4c81)](results/leaderboard.md)
[![License](https://img.shields.io/badge/license-Apache%202.0-2f6f4e)](LICENSE)
[![Hugging Face](https://img.shields.io/badge/Hugging%20Face-catalog-ffcc00)](https://huggingface.co/datasets/junjun77/small-ow-agent-bench)
[![GitHub](https://img.shields.io/badge/GitHub-caojiajun777-181717)](https://github.com/caojiajun777/small-ow-agent-bench)

> How much Coding Agent work can small models handle on a home machine?

The cost of a Coding Agent is not limited to its final answer. To change three lines of code, it may first scan directories, read files, run tests, edit code, and run the tests again. Every step in that trajectory consumes tokens. The hardest problems deserve the strongest models, but engineering tasks do not all have the same level of difficulty. Finding a file, fixing a small piece of logic, adding a few tests, or reproducing a bug all have clear scopes and directly verifiable outcomes. If a small model can do the job, calling the most capable API every time may not be cost-effective.

Open-weight models can also stay on a local machine or inside a company network. Code does not need to be sent to an external service, model versions can be pinned, and quantization and customization are easier. Teams no longer pay per API call and are not subject to third-party rate limits. The 16 configurations on the leaderboard range from 3B to 35B total parameters. With suitable low-bit quantization, all of them can run on a high-performance home machine or personal workstation with enough RAM or VRAM, without multi-server infrastructure, a dedicated cluster, or custom accelerators. Models from 3B to 14B have a lower deployment barrier, while those from 20B to 35B require more memory.

Local deployment still carries hardware and operational costs. Saving on API fees means little if the model cannot complete the task. Small-OW-Agent-Bench starts with a more basic question: which Coding Agent tasks can models deployable on personal hardware actually complete, and where do they get stuck when they fail?

The benchmark contains 62 automatically graded coding tasks that preserve common software-engineering traps. We evaluated 16 open-weight model configurations, running each model independently three times on every task for a total of 2,976 sandbox experiments. The suite can compare today's models and accommodate future releases, revealing both strengths and weaknesses and providing evidence for post-training and improvements in coding ability.

This repository contains the complete evaluation pipeline, from task suite to leaderboard: tasks and hidden verifiers, Docker sandboxes, a terminal Agent, pinned model and API configurations, batch execution, replacement runs for infrastructure failures, difficulty metadata, scoring scripts, and result charts. Every number on the leaderboard can be traced back to a specific model, task, and repeated run; none are manually entered aggregates.

## Why benchmark with code

Code can be executed, so a program can verify whether an answer is correct. A model must enter a terminal, inspect a repository, edit files, run tests, adjust its approach based on feedback, and stop when the task is complete. Together, these actions form the basic working loop of a Coding Agent. Scoring considers only the final artifact, not how polished the response sounds, and does not require another LLM as a judge.

This is only a narrow window into general intelligence. It measures whether models can complete a set of executable, feedback-rich, verifiable software-engineering tasks; it is not an AGI test.

## How we break down tasks

A run can fail for many reasons: the Agent may find the wrong file, make an incorrect edit, write a bad test, or complete the task but fail to stop. A single pass/fail result does not show where the problem occurred, so we divide the workflow into five independently verifiable stages:

| Task | What the model must do | Success criterion |
|---|---|---|
| Localization | Identify the files that need to change from an issue description | Return every required file and no extras |
| Editing | Apply a requested change after the target file is provided | Pass all hidden tests |
| Test Generation | Write tests for a given function | Accept the correct implementation and catch faulty ones |
| Reproduction | Write a program that reliably reproduces a bug | Fail before the fix and pass after it |
| Patch Validation | Decide whether a given patch actually resolves the issue | Match the reference verdict |

The five columns correspond to localization, implementation, testing, reproduction, and patch validation. Two models with similar overall scores may have entirely different weaknesses.

## Two scores

Correct code does not necessarily mean the Agent completed the full workflow. We record the result and the process separately.

| Plain-language name | Technical name | Meaning |
|---|---|---|
| **Result score** | Artifact Score | Whether the Agent left behind the correct result, weighted by the task's authored difficulty |
| **Completion score** | Clean Score | Whether the result was correct and the Agent explicitly completed and stopped, using the same weighting |

For example, an Agent may edit the file correctly but continue rerunning tests until it exhausts its 20-turn budget. That run counts as an Artifact success but not a Clean completion. Below, we call this `correct but did not stop`.

The three runs for each task are averaged first. Authored difficulty weights are 1 for Easy, 1.5 for Medium, and 2 for Hard. The leaderboard applies these weights within each capability category, then gives all five categories equal weight to produce a score out of 100. It also retains the unweighted raw number of successful runs for auditability.

## Why these tasks reveal meaningful differences

Task difficulty is only one requirement. More importantly, score differences should map to specific behaviors, and the grading should withstand repeated inspection.

Each of the five task types has explicit inputs and artifacts. Localization submits only a file set; Editing provides the target file directly; Test Generation may not modify the implementation; Reproduction may not fix the repository; and Patch Validation submits only a verdict. The acceptance rules are equally concrete: file sets must match exactly, and including one extra similar-looking file is a failure; code edits must pass hidden tests; generated tests must accept the correct implementation and reject intentionally faulty versions; bug reproductions must fail before the fix and pass after the reference patch is applied; and patch verdicts are checked against fixed labels. Every grader is validated with both a reference solution and a no-op baseline: the reference solution must pass, and doing nothing must fail.

The 62 tasks are designed around common failure traps across the five capability categories, with each trap represented by one or two short tasks. The authored difficulties frozen at task creation are 17 Easy, 21 Medium, and 24 Hard; these determine scoring weights. After running the benchmark, we calibrated empirical difficulty using the same model pool and obtained 12 Easy, 38 Medium, 7 Hard, and 5 Out-of-range tasks. Empirical labels are used only for calibration and never rewrite authored difficulty. All five Out-of-range tasks were authored as Hard and retain the Hard scoring weight.

Every `model configuration × task` combination runs three times in an independent sandbox. The Agent interface, 20-turn budget, hidden verifier, and scoring rules remain fixed. API or platform outages do not count as model failures; selecting the wrong file, producing an incorrect artifact or format, exhausting the budget, or failing to end normally are still scored as failures under the protocol.

To check whether the intended difficulty tiers were reflected in the data, we also performed a 1PL Rasch analysis. Authored difficulty has a Spearman correlation of 0.58 with empirically estimated difficulty, while average pass rates for Easy, Medium, and Hard are 50.2%, 37.8%, and 26.5%, respectively. The three tiers preserve the expected ordering overall. IRT is used only to inspect the task set and does not affect leaderboard scoring; see [`DIFFICULTY.md`](DIFFICULTY.md) for the complete results.

Artifact measures what the model left behind; Clean additionally checks whether it stopped normally. The leaderboard compares complete system configurations under the frozen compact-shell protocol. Scores should not be interpreted as properties of model weights in isolation from the API provider, inference parameters, and Agent interface.

## Leaderboard (v1.0.1)

The table ranks all 16 configurations by Artifact Score. Dark bars show the result score and light bars show the completion score. The gap between them represents runs in which the model produced the correct artifact but did not stop normally.

![Artifact Score and Clean Score for 16 configurations](results/figures/v1.0.1-compact10-en.svg)

| Model | Artifact Score | Clean Score |
|---|---:|---:|
| <img src="results/figures/vendors/qwen.svg" width="16" height="16" alt="Qwen"> Qwen3.8-27B | 83.8 | 81.8 |
| <img src="results/figures/vendors/qwen.svg" width="16" height="16" alt="Qwen"> Qwen3.5-9B | 77.3 | 74.3 |
| <img src="results/figures/vendors/qwen.svg" width="16" height="16" alt="Qwen"> Qwen3.6-35B-A3B | 59.5 | 51.7 |
| <img src="results/figures/vendors/zai.svg" width="16" height="16" alt="Z.ai"> GLM-4.7-Flash | 51.3 | 39.1 |
| <img src="results/figures/vendors/openai.svg" width="16" height="16" alt="OpenAI"> GPT-OSS-20B | 47.9 | 40.2 |
| <img src="results/figures/vendors/mistralai.svg" width="16" height="16" alt="Mistral"> Ministral-14B | 46.9 | 46.2 |
| <img src="results/figures/vendors/mistralai.svg" width="16" height="16" alt="Mistral"> Ministral-8B | 43.2 | 38.7 |
| <img src="results/figures/vendors/qwen.svg" width="16" height="16" alt="Qwen"> Qwen3-14B | 39.0 | 31.8 |
| <img src="results/figures/vendors/nvidia.svg" width="16" height="16" alt="NVIDIA"> Nemotron-3.5-Lightning | 34.7 | 9.2 |
| <img src="results/figures/vendors/google.svg" width="16" height="16" alt="Google"> Gemma-3-12B | 30.2 | 11.0 |
| <img src="results/figures/vendors/ibm.svg" width="16" height="16" alt="IBM"> Granite-4.1-8B | 15.2 | 13.4 |
| <img src="results/figures/vendors/google.svg" width="16" height="16" alt="Google"> Gemma-4-26B-A4B | 13.1 | 13.1 |
| <img src="results/figures/vendors/google.svg" width="16" height="16" alt="Google"> Gemma-3-4B | 6.8 | 6.8 |
| <img src="results/figures/vendors/mistralai.svg" width="16" height="16" alt="Mistral"> Ministral-3B | 4.7 | 1.7 |
| <img src="results/figures/vendors/qwen.svg" width="16" height="16" alt="Qwen"> Qwen3-8B | 2.5 | 1.5 |
| <img src="results/figures/vendors/meta.svg" width="16" height="16" alt="Meta"> Llama-3.2-3B | 2.1 | 0.0 |

Qwen3.6-35B-A3B is a Mixture-of-Experts model with about 3B active parameters; it should not be treated as the next size tier above a 27B dense model. The table is sorted only by measured score, not by parameter count.

The five skill scores are 0–100 after Easy 1 / Medium 1.5 / Hard 2 weighting inside each category; the weighted total is the equal-weight mean of the five skills. The full tables, raw success counts, and Clean skill columns are in [`results/leaderboard.md`](results/leaderboard.md).

### Artifact Score (five skills)

| Model | Loc | Edit | Testgen | Repro | Review | Weighted total |
|---|---:|---:|---:|---:|---:|---:|
| <img src="results/figures/vendors/qwen.svg" width="16" height="16" alt="Qwen"> Qwen3.8-27B | 52.1 | 96.4 | 90.7 | 84.1 | 95.8 | **83.8** |
| <img src="results/figures/vendors/qwen.svg" width="16" height="16" alt="Qwen"> Qwen3.5-9B | 28.2 | 89.2 | 93.0 | 76.2 | 100.0 | 77.3 |
| <img src="results/figures/vendors/qwen.svg" width="16" height="16" alt="Qwen"> Qwen3.6-35B-A3B | 33.3 | 53.2 | 90.7 | 45.2 | 75.0 | 59.5 |
| <img src="results/figures/vendors/zai.svg" width="16" height="16" alt="Z.ai"> GLM-4.7-Flash | 2.6 | 71.2 | 36.4 | 64.3 | 82.3 | 51.3 |
| <img src="results/figures/vendors/openai.svg" width="16" height="16" alt="OpenAI"> GPT-OSS-20B | 17.9 | 36.0 | 35.7 | 73.0 | 77.1 | 47.9 |
| <img src="results/figures/vendors/mistralai.svg" width="16" height="16" alt="Mistral"> Ministral-14B | 7.7 | 61.3 | 2.3 | 81.0 | 82.3 | 46.9 |
| <img src="results/figures/vendors/mistralai.svg" width="16" height="16" alt="Mistral"> Ministral-8B | 13.7 | 61.3 | 30.2 | 55.6 | 55.2 | 43.2 |
| <img src="results/figures/vendors/qwen.svg" width="16" height="16" alt="Qwen"> Qwen3-14B | 7.7 | 40.5 | 44.2 | 42.1 | 60.4 | 39.0 |
| <img src="results/figures/vendors/nvidia.svg" width="16" height="16" alt="NVIDIA"> Nemotron-3.5-Lightning | 5.1 | 66.7 | 64.3 | 11.1 | 26.0 | 34.7 |
| <img src="results/figures/vendors/google.svg" width="16" height="16" alt="Google"> Gemma-3-12B | 0.0 | 48.6 | 16.3 | 40.5 | 45.8 | 30.2 |
| <img src="results/figures/vendors/ibm.svg" width="16" height="16" alt="IBM"> Granite-4.1-8B | 0.0 | 34.2 | 7.0 | 4.8 | 30.2 | 15.2 |
| <img src="results/figures/vendors/google.svg" width="16" height="16" alt="Google"> Gemma-4-26B-A4B | 4.3 | 18.9 | 15.5 | 27.0 | 0.0 | 13.1 |
| <img src="results/figures/vendors/google.svg" width="16" height="16" alt="Google"> Gemma-3-4B | 0.0 | 8.1 | 0.0 | 0.0 | 26.0 | 6.8 |
| <img src="results/figures/vendors/mistralai.svg" width="16" height="16" alt="Mistral"> Ministral-3B | 2.6 | 11.7 | 9.3 | 0.0 | 0.0 | 4.7 |
| <img src="results/figures/vendors/qwen.svg" width="16" height="16" alt="Qwen"> Qwen3-8B | 7.7 | 0.0 | 0.0 | 4.8 | 0.0 | 2.5 |
| <img src="results/figures/vendors/meta.svg" width="16" height="16" alt="Meta"> Llama-3.2-3B | 0.0 | 0.0 | 0.0 | 0.0 | 10.4 | 2.1 |

### Clean Score (five skills)

Clean Score requires a correct artifact and a normal stop. Row order matches the Artifact table.

| Model | Loc | Edit | Testgen | Repro | Review | Weighted total |
|---|---:|---:|---:|---:|---:|---:|
| <img src="results/figures/vendors/qwen.svg" width="16" height="16" alt="Qwen"> Qwen3.8-27B | 41.9 | 96.4 | 90.7 | 84.1 | 95.8 | 81.8 |
| <img src="results/figures/vendors/qwen.svg" width="16" height="16" alt="Qwen"> Qwen3.5-9B | 28.2 | 83.8 | 93.0 | 66.7 | 100.0 | 74.3 |
| <img src="results/figures/vendors/qwen.svg" width="16" height="16" alt="Qwen"> Qwen3.6-35B-A3B | 33.3 | 53.2 | 90.7 | 6.3 | 75.0 | 51.7 |
| <img src="results/figures/vendors/zai.svg" width="16" height="16" alt="Z.ai"> GLM-4.7-Flash | 2.6 | 71.2 | 36.4 | 3.2 | 82.3 | 39.1 |
| <img src="results/figures/vendors/openai.svg" width="16" height="16" alt="OpenAI"> GPT-OSS-20B | 17.9 | 16.2 | 25.6 | 64.3 | 77.1 | 40.2 |
| <img src="results/figures/vendors/mistralai.svg" width="16" height="16" alt="Mistral"> Ministral-14B | 7.7 | 57.7 | 2.3 | 81.0 | 82.3 | 46.2 |
| <img src="results/figures/vendors/mistralai.svg" width="16" height="16" alt="Mistral"> Ministral-8B | 8.5 | 50.5 | 27.1 | 52.4 | 55.2 | 38.7 |
| <img src="results/figures/vendors/qwen.svg" width="16" height="16" alt="Qwen"> Qwen3-14B | 7.7 | 40.5 | 44.2 | 40.5 | 26.0 | 31.8 |
| <img src="results/figures/vendors/nvidia.svg" width="16" height="16" alt="NVIDIA"> Nemotron-3.5-Lightning | 2.6 | 9.0 | 21.7 | 3.2 | 9.4 | 9.2 |
| <img src="results/figures/vendors/google.svg" width="16" height="16" alt="Google"> Gemma-3-12B | 0.0 | 0.0 | 7.0 | 2.4 | 45.8 | 11.0 |
| <img src="results/figures/vendors/ibm.svg" width="16" height="16" alt="IBM"> Granite-4.1-8B | 0.0 | 25.2 | 7.0 | 4.8 | 30.2 | 13.4 |
| <img src="results/figures/vendors/google.svg" width="16" height="16" alt="Google"> Gemma-4-26B-A4B | 4.3 | 18.9 | 15.5 | 27.0 | 0.0 | 13.1 |
| <img src="results/figures/vendors/google.svg" width="16" height="16" alt="Google"> Gemma-3-4B | 0.0 | 8.1 | 0.0 | 0.0 | 26.0 | 6.8 |
| <img src="results/figures/vendors/mistralai.svg" width="16" height="16" alt="Mistral"> Ministral-3B | 0.0 | 3.6 | 4.7 | 0.0 | 0.0 | 1.7 |
| <img src="results/figures/vendors/qwen.svg" width="16" height="16" alt="Qwen"> Qwen3-8B | 7.7 | 0.0 | 0.0 | 0.0 | 0.0 | 1.5 |
| <img src="results/figures/vendors/meta.svg" width="16" height="16" alt="Meta"> Llama-3.2-3B | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## How to use this leaderboard

This leaderboard is more useful for model routing than for simply choosing the model with the highest overall score. Start with scores across the five task categories, then select candidates based on the work you actually need to do. Small-scope, frequent, automatically verifiable tasks can be routed to a small model first and checked with tests or deterministic rules. Tasks that fail validation or carry higher risk can then be escalated to a stronger model or a human. The leaderboard cannot define a team's risk boundaries, but it can help the team decide which model to try first.

## Protocol and limitations

All experiments run in independent Linux Docker sandboxes. Models cannot see the hidden tests and receive at most 20 terminal-interaction turns. To ensure that every model faces the same environment, we pin the API route, inference parameters, Agent interface, tool permissions, and turn budget. From the Agent's perspective, this closely resembles connecting the model to a local inference service: it sees the same repository, uses the same terminal tools, receives the same execution feedback, and submits the same type of artifact. The API provides inference only; it does not participate in task execution or scoring. The leaderboard therefore reflects end-to-end Agent capability under a fixed protocol and can serve as evidence when screening models for local deployment. See [`STANDARD.md`](STANDARD.md) for the full protocol, all 16 model configurations, and reproduction instructions.

The main difference between API and local execution lies in the inference backend. Quantization method, inference engine, context implementation, and hardware configuration can all affect output, speed, and cost. Version 1.0.1 does not control these variables or include the strongest closed models under the same protocol. This is therefore a capability and reliability leaderboard, not a price-performance ranking, and it does not claim that small models have reached the capabilities of frontier closed models. A complete comparison of local cost-effectiveness must also account for GPU cost, throughput, latency, utilization, and cost per successful task.

<details>
<summary>Run one task</summary>

The sandbox uses Novita and the Agent uses compact-shell. First copy `.env.example` to `.env`; do not commit `.env`. If another evaluation job is already running, wait for it to finish before starting the next one.

```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = (Get-Location).Path

harbor run --env-file .env -o jobs -p ./tasks/loc-member-discount `
  -a agents.compact_shell:CompactShellAgent `
  -m openrouter/qwen/qwen3.5-9b -k 1 -n 1 -e novita `
  --ak 'llm_call_kwargs={"extra_body":{"enable_thinking":false}}'

python scripts/score_standard.py jobs/<job>
```

Batch entry point: `python scripts/run_locked.py` (see [`STANDARD.md`](STANDARD.md)). Do not overwrite `jobs/locked-core.json`, `jobs/locked-core-k3.json`, or `jobs/locked-hard-release-k3.json`.

</details>
