---
license: apache-2.0
pretty_name: small-ow-agent-bench
task_categories:
  - text-generation
language:
  - en
tags:
  - agents
  - code
  - evaluation
  - harbor
  - benchmark
size_categories:
  - n<1K
configs:
  - config_name: catalog
    data_files: catalog.jsonl
    default: true
---

# small-ow-agent-bench (catalog)

Frozen compact-shell **system** reliability for compact open-weight coding agents — not coding IQ.

- GitHub: [caojiajun777/small-ow-agent-bench](https://github.com/caojiajun777/small-ow-agent-bench)
- Tag: [`benchmark-v1.0.1`](https://github.com/caojiajun777/small-ow-agent-bench/releases/tag/benchmark-v1.0.1)
- This dataset: [`junjun77/small-ow-agent-bench`](https://huggingface.co/datasets/junjun77/small-ow-agent-bench)

This dataset is **not** the Harbor task dump. Each of the 62 rows is catalog metadata plus the agent-visible instruction:

- `id`, `skill`, `difficulty`, `construct_difficulty`, `bank`
- `empirical_band`, `calibration_status`, `difficulty_weight`
- `trap_id` / `trap` (failure-mode label from `TRAPS.md`)
- `instruction` / `instruction_summary`
- license, GitHub tag, compact-shell version

It does **not** include hidden verifiers: `tests/`, `solution/`, `foils/`, gold file lists, mutants, or `environment/repo`. Those stay in Harbor `tasks/` on GitHub.

Do not train on this 62-item bank and then report the same items as evaluation.

The v1.0.1 canonical table covers 16 fully evaluated model configurations. Each `(configuration, task, attempt)` key is unique, and frozen source rows are not overwritten.

## Leaderboard (v1.0.1)

Headline = a 0–100 difficulty-weighted score: Easy 1, Medium 1.5, Hard 2 inside each skill, followed by a five-skill macro. Raw successes / 186 remain visible. Artifact does not require `finish`; Clean does. Halt (Artifact=1, not clean) = **197**. 16×62×3 = **2976** scored trials. All 16 configs enter one rank. Qwen3.6-35B-A3B is a MoE with ~3B active parameters.

![Artifact Score 与 Clean Score](v1.0.1-compact10.svg)

| # | Model | Artifact Score | Clean Score | Gap | Artifact raw | Clean raw |
|---:|---|---:|---:|---:|---:|---:|
| 1 | Qwen3.8-27B | 83.8 | 81.8 | 2.1 | 162/186 | 159/186 |
| 2 | Qwen3.5-9B | 77.3 | 74.3 | 3.0 | 148/186 | 142/186 |
| 3 | Qwen3.6-35B-A3B | 59.5 | 51.7 | 7.8 | 118/186 | 104/186 |
| 4 | GLM-4.7-Flash | 51.3 | 39.1 | 12.2 | 105/186 | 80/186 |
| 5 | GPT-OSS-20B | 47.9 | 40.2 | 7.7 | 89/186 | 74/186 |
| 6 | Ministral-14B | 46.9 | 46.2 | 0.7 | 93/186 | 91/186 |
| 7 | Ministral-8B | 43.2 | 38.7 | 4.4 | 87/186 | 78/186 |
| 8 | Qwen3-14B | 39.0 | 31.8 | 7.2 | 76/186 | 65/186 |
| 9 | Nemotron-3.5-Lightning | 34.7 | 9.2 | 25.5 | 70/186 | 18/186 |
| 10 | Gemma-3-12B | 30.2 | 11.0 | 19.2 | 60/186 | 18/186 |
| 11 | Granite-4.1-8B | 15.2 | 13.4 | 1.8 | 31/186 | 26/186 |
| 12 | Gemma-4-26B-A4B | 13.1 | 13.1 | 0.0 | 26/186 | 26/186 |
| 13 | Gemma-3-4B | 6.8 | 6.8 | 0.0 | 11/186 | 11/186 |
| 14 | Ministral-3B | 4.7 | 1.7 | 3.1 | 10/186 | 4/186 |
| 15 | Qwen3-8B | 2.5 | 1.5 | 1.0 | 6/186 | 3/186 |
| 16 | Llama-3.2-3B | 2.1 | 0.0 | 2.1 | 4/186 | 0/186 |

Full five-skill tables: [results/leaderboard.md](https://github.com/caojiajun777/small-ow-agent-bench/blob/main/results/leaderboard.md).

Regenerate:

```text
python scripts/export_hf_catalog.py --write
```
