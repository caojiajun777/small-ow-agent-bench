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

- `id`, `skill`, `difficulty`, `bank`
- `trap_id` / `trap` (failure-mode label from `TRAPS.md`)
- `instruction` / `instruction_summary`
- license, GitHub tag, compact-shell version

It does **not** include hidden verifiers: `tests/`, `solution/`, `foils/`, gold file lists, mutants, or `environment/repo`. Those stay in Harbor `tasks/` on GitHub.

Do not train on this 62-item bank and then report the same items as evaluation.

## Leaderboard (v1.0.1)

Headline = five-skill **macro** mean. Micro = successes / 186. Artifact does not require `finish`; Clean does. Halt (Artifact=1, not clean) = **105**. 12×62×3 = **2232** scored trials. All 12 configs enter one rank. Qwen3.6-35B-A3B is a MoE with ~3B active parameters.

![12 configs Artifact vs Clean](v1.0.1-compact10.svg)

| # | Model | Artifact macro | Clean macro | Gap | Artifact micro | Clean micro |
|---:|---|---:|---:|---:|---:|---:|
| 1 | Qwen3.8-27B | 0.863 | 0.845 | 0.018 | 162/186 | 159/186 |
| 2 | Qwen3.5-9B | 0.786 | 0.757 | 0.029 | 148/186 | 142/186 |
| 3 | Qwen3.6-35B-A3B | 0.632 | 0.560 | 0.072 | 118/186 | 104/186 |
| 4 | Ministral-14B | 0.497 | 0.488 | 0.009 | 93/186 | 91/186 |
| 5 | Ministral-8B | 0.456 | 0.411 | 0.045 | 87/186 | 78/186 |
| 6 | Qwen3-14B | 0.404 | 0.333 | 0.072 | 76/186 | 65/186 |
| 7 | Gemma-3-12B | 0.313 | 0.114 | **0.199** | 60/186 | 18/186 |
| 8 | Granite-4.1-8B | 0.162 | 0.140 | 0.022 | 31/186 | 26/186 |
| 9 | Gemma-3-4B | 0.067 | 0.067 | 0.000 | 11/186 | 11/186 |
| 10 | Ministral-3B | 0.049 | 0.019 | 0.030 | 10/186 | 4/186 |
| 11 | Qwen3-8B | 0.034 | 0.018 | 0.015 | 6/186 | 3/186 |
| 12 | Llama-3.2-3B | 0.027 | 0.000 | 0.027 | 4/186 | 0/186 |

Full five-skill tables: [results/leaderboard.md](https://github.com/caojiajun777/small-ow-agent-bench/blob/main/results/leaderboard.md).

Regenerate:

```text
python scripts/export_hf_catalog.py --write
```
