# 已有 bench 的题目级 IRT（精炼题，不是模型卡总分）

先验来自 **别人已经公开的题目 × agent 0/1 矩阵**，不是 LCB 65.6 那种一个数。

## 数据

[Agent Psychometrics](https://arxiv.org/abs/2604.00594) 已经拟合过 1PL：

| 题集 | 题数 | agent 数 | 矩阵 |
|---|---:|---:|---|
| SWE-bench Verified | 500 | 134 | `cache/swebench_verified/responses.jsonl` |
| Terminal-Bench 2.0 | 89 | 112 | `cache/terminalbench/responses.jsonl` |
| SWE-bench Pro | 730 | 14 | `cache/swebench_pro/responses.jsonl` |

`items.csv` 里的 `b` 是他们的 1PL 难度。`abilities.csv` 的 \(\theta\) 几乎全是前沿 agent（Opus / GPT-5 / OpenHands），**没有 3B–9B 行**。

## 精炼规则

```text
python scripts/distill_bench_irt.py
```

对每道已有题：

- \(p\le 0.02\) 或 \(p\ge 0.98\)：零信息，丢掉
- \(0.2<p<0.8\)：对 **该人群** 有信息（前沿 agent 之间能拉开）
- \(p>0.8\)：该人群的 Easy 尾。只有这里的 \(b\) 才可能靠近小模型 \(\theta\)

产出：`distilled.json`、`informative-items.json`。

## 对出题的含义

这些 \(b\) 是按前沿 agent 标定的。把 SWE / TB 原题原样拿给 3B–9B，几乎全 0，IRT 没有斜率。

精炼 = 留下 Easy / informative 尾的 **考点**（`fix-git`、点名编辑、日志抽取、局部复现），改写成五项原子的 Harbor 短题；丢掉 `make-doom-for-mips` / `install-windows-3.11` 这种复合长程题。
