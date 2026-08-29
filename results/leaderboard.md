# v1.0.1 leaderboard

Source: [`canonical-coverage.json`](canonical-coverage.json). Regenerate: `python scripts/write_leaderboard.py --write`.

Headline = 0–100 difficulty-weighted score: Easy 1, Medium 1.5, Hard 2 inside each skill, followed by a five-skill macro. Raw successes remain visible. All 16 configs enter one rank, sorted by Artifact Score. Qwen3.6-35B-A3B is a MoE with ~3B active parameters, not a dense 35B step. Artifact does not require `finish`; Clean does.

n = 16 configs × 62 tasks × 3 = **2976** scored trials. `remaining_dirty` 0. Halt (Artifact=1, not clean) = **197**.

## Ranked (16 configs)

| # | 模型 | Artifact Score | Clean Score | Gap | Artifact 原始通过 | Clean 原始通过 |
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

## Artifact Score (five weighted skills)

| 模型 | Loc | Edit | Testgen | Repro | Review | **加权总分** |
|---|---:|---:|---:|---:|---:|---:|
| Qwen3.8-27B | 52.1 | 96.4 | 90.7 | 84.1 | 95.8 | **83.8** |
| Qwen3.5-9B | 28.2 | 89.2 | 93.0 | 76.2 | 100.0 | 77.3 |
| Qwen3.6-35B-A3B | 33.3 | 53.2 | 90.7 | 45.2 | 75.0 | 59.5 |
| GLM-4.7-Flash | 2.6 | 71.2 | 36.4 | 64.3 | 82.3 | 51.3 |
| GPT-OSS-20B | 17.9 | 36.0 | 35.7 | 73.0 | 77.1 | 47.9 |
| Ministral-14B | 7.7 | 61.3 | 2.3 | 81.0 | 82.3 | 46.9 |
| Ministral-8B | 13.7 | 61.3 | 30.2 | 55.6 | 55.2 | 43.2 |
| Qwen3-14B | 7.7 | 40.5 | 44.2 | 42.1 | 60.4 | 39.0 |
| Nemotron-3.5-Lightning | 5.1 | 66.7 | 64.3 | 11.1 | 26.0 | 34.7 |
| Gemma-3-12B | 0.0 | 48.6 | 16.3 | 40.5 | 45.8 | 30.2 |
| Granite-4.1-8B | 0.0 | 34.2 | 7.0 | 4.8 | 30.2 | 15.2 |
| Gemma-4-26B-A4B | 4.3 | 18.9 | 15.5 | 27.0 | 0.0 | 13.1 |
| Gemma-3-4B | 0.0 | 8.1 | 0.0 | 0.0 | 26.0 | 6.8 |
| Ministral-3B | 2.6 | 11.7 | 9.3 | 0.0 | 0.0 | 4.7 |
| Qwen3-8B | 7.7 | 0.0 | 0.0 | 4.8 | 0.0 | 2.5 |
| Llama-3.2-3B | 0.0 | 0.0 | 0.0 | 0.0 | 10.4 | 2.1 |

## Clean Score (five weighted skills)

Row order matches the Artifact table. Granite Clean Score > Gemma-12B because of Gemma-12B's halt tax, not because Granite solves more items.

| 模型 | Loc | Edit | Testgen | Repro | Review | **加权总分** |
|---|---:|---:|---:|---:|---:|---:|
| Qwen3.8-27B | 41.9 | 96.4 | 90.7 | 84.1 | 95.8 | 81.8 |
| Qwen3.5-9B | 28.2 | 83.8 | 93.0 | 66.7 | 100.0 | 74.3 |
| Qwen3.6-35B-A3B | 33.3 | 53.2 | 90.7 | 6.3 | 75.0 | 51.7 |
| GLM-4.7-Flash | 2.6 | 71.2 | 36.4 | 3.2 | 82.3 | 39.1 |
| GPT-OSS-20B | 17.9 | 16.2 | 25.6 | 64.3 | 77.1 | 40.2 |
| Ministral-14B | 7.7 | 57.7 | 2.3 | 81.0 | 82.3 | 46.2 |
| Ministral-8B | 8.5 | 50.5 | 27.1 | 52.4 | 55.2 | 38.7 |
| Qwen3-14B | 7.7 | 40.5 | 44.2 | 40.5 | 26.0 | 31.8 |
| Nemotron-3.5-Lightning | 2.6 | 9.0 | 21.7 | 3.2 | 9.4 | 9.2 |
| Gemma-3-12B | 0.0 | 0.0 | 7.0 | 2.4 | 45.8 | 11.0 |
| Granite-4.1-8B | 0.0 | 25.2 | 7.0 | 4.8 | 30.2 | 13.4 |
| Gemma-4-26B-A4B | 4.3 | 18.9 | 15.5 | 27.0 | 0.0 | 13.1 |
| Gemma-3-4B | 0.0 | 8.1 | 0.0 | 0.0 | 26.0 | 6.8 |
| Ministral-3B | 0.0 | 3.6 | 4.7 | 0.0 | 0.0 | 1.7 |
| Qwen3-8B | 7.7 | 0.0 | 0.0 | 0.0 | 0.0 | 1.5 |
| Llama-3.2-3B | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
