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
size_categories:
  - n<1K
---

# small-ow-agent-bench (catalog)

Public **metadata catalog** for [small-ow-agent-bench](https://github.com/caojiajun777/small-ow-agent-bench) tag **`benchmark-v1.0.1`**. Hugging Face dataset: [`junjun77/small-ow-agent-bench`](https://huggingface.co/datasets/junjun77/small-ow-agent-bench).

This dataset is **not** the Harbor task dump. Each row is one of the 62 scored items:

- `id`, `skill`, `difficulty`, `bank`
- `trap_id` / `trap` (failure-mode label from `TRAPS.md`)
- agent-visible `instruction` / `instruction_summary`
- license, GitHub tag, compact-shell version

It does **not** include hidden verifiers: `tests/`, `solution/`, `foils/`, gold file lists, mutants, or `environment/repo`. Those stay in the Harbor `tasks/` tree on GitHub and are required to score a run.

Do not train on this 62-item bank and then report the same items as evaluation. The published table measures compact-shell **system** reliability, not coding IQ detached from the harness.

Headline numbers and the 12×62×3 matrix live on GitHub (`results/canonical-coverage.json`, `results/v1.0.1_trials.jsonl`), not in this catalog.

Regenerate:

```text
python scripts/export_hf_catalog.py --write
```
