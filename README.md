# small-ow-agent-bench

在冻结的极薄 shell（**compact-shell** v0.1.1）下，测开放权重小型 coding agent 的**端到端系统可靠性**。分数是模型 + 钉死的 OpenRouter 线路 + Novita 沙箱 + compact-shell 的系统分，不是脱离 harness 的 coding IQ。

公开仓库：[github.com/caojiajun777/small-ow-agent-bench](https://github.com/caojiajun777/small-ow-agent-bench)。当前阅读表是 **v1.0.1 canonical matrix**，对应 git tag **`benchmark-v1.0.1`**。方法与读法见 [`项目说明.md`](项目说明.md)。

## 两个指标

不要混成一个「总分」。Headline = 五个任务族的**宏平均**。括号里的微平均 = 成功 / 186（62 题 × 3）。宏平均 ≠ 微平均。

| 指标 | 定义 | `finish` |
|---|---|---|
| **Artifact**（规定产物正确率） | 隐藏评分器看规定产物过没过 | 不要求。写对了但没停，仍记 1。Headline。 |
| **Clean**（干净完成率） | Artifact=1 且交互干净终止 | 要求空的 finish 围栏 |

五个任务族是操作性切片，不是五种基础智力：Loc / Edit / Testgen / Repro / Review（本集里 Review = **Patch Validation**）。

## Leaderboard（v1.0.1）

12 配置 × 62 题 × 3 = **2,232** 次 scored trial。`remaining_dirty` 0。Halt（Artifact=1、非 clean）= **105**。Compact-10 按 Artifact 宏平均排序。27B / 35B-A3B 是 upper-reference，不进该排序。35B-A3B 是约 3B 激活的 MoE。

数字从 [`results/canonical-coverage.json`](results/canonical-coverage.json) 生成。完整五列技能表：[`results/leaderboard.md`](results/leaderboard.md)。再生：`python scripts/write_leaderboard.py --write`。

### Compact-10

| # | 模型 | Artifact 宏平均 | Clean 宏平均 | Gap | Artifact 微平均 | Clean 微平均 |
|---:|---|---:|---:|---:|---:|---:|
| 1 | Qwen3.5-9B | 0.786 | 0.757 | 0.029 | 148/186 | 142/186 |
| 2 | Ministral-14B | 0.497 | 0.488 | 0.009 | 93/186 | 91/186 |
| 3 | Ministral-8B | 0.456 | 0.411 | 0.045 | 87/186 | 78/186 |
| 4 | Qwen3-14B | 0.404 | 0.333 | 0.072 | 76/186 | 65/186 |
| 5 | Gemma-3-12B | 0.313 | 0.114 | **0.199** | 60/186 | 18/186 |
| 6 | Granite-4.1-8B | 0.162 | 0.140 | 0.022 | 31/186 | 26/186 |
| 7 | Gemma-3-4B | 0.067 | 0.067 | 0.000 | 11/186 | 11/186 |
| 8 | Ministral-3B | 0.049 | 0.019 | 0.030 | 10/186 | 4/186 |
| 9 | Qwen3-8B | 0.034 | 0.018 | 0.015 | 6/186 | 3/186 |
| 10 | Llama-3.2-3B | 0.027 | 0.000 | 0.027 | 4/186 | 0/186 |

### Upper-reference（不与 Compact-10 混排）

| 模型 | Artifact 宏平均 | Clean 宏平均 | Gap | Artifact 微平均 | Clean 微平均 |
|---|---:|---:|---:|---:|---:|
| Qwen3.8-27B | 0.863 | 0.845 | 0.018 | 162/186 | 159/186 |
| Qwen3.6-35B-A3B | 0.632 | 0.560 | 0.072 | 118/186 | 104/186 |

### Artifact Correctness

| 模型 | Loc | Edit | Testgen | Repro | Review | **宏平均** | 微平均 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen3.5-9B | 0.303 | 0.933 | 0.923 | 0.769 | 1.000 | **0.786** | 0.796（148/186） |
| Ministral-14B | 0.091 | 0.689 | 0.026 | 0.846 | 0.833 | 0.497 | 0.500（93/186） |
| Ministral-8B | 0.152 | 0.689 | 0.308 | 0.564 | 0.567 | 0.456 | 0.468（87/186） |
| Qwen3-14B | 0.091 | 0.467 | 0.462 | 0.436 | 0.567 | 0.404 | 0.409（76/186） |
| Gemma-3-12B | 0.000 | 0.533 | 0.179 | 0.385 | 0.467 | 0.313 | 0.323（60/186） |
| Granite-4.1-8B | 0.000 | 0.356 | 0.077 | 0.077 | 0.300 | 0.162 | 0.167（31/186） |
| Gemma-3-4B | 0.000 | 0.067 | 0.000 | 0.000 | 0.267 | 0.067 | 0.059（11/186） |
| Ministral-3B | 0.030 | 0.111 | 0.103 | 0.000 | 0.000 | 0.049 | 0.054（10/186） |
| Qwen3-8B | 0.091 | 0.000 | 0.000 | 0.077 | 0.000 | 0.034 | 0.032（6/186） |
| Llama-3.2-3B | 0.000 | 0.000 | 0.000 | 0.000 | 0.133 | 0.027 | 0.022（4/186） |
| Qwen3.8-27B | 0.576 | 0.978 | 0.923 | 0.872 | 0.967 | 0.863 | 0.871（162/186） |
| Qwen3.6-35B-A3B | 0.364 | 0.644 | 0.923 | 0.462 | 0.767 | 0.632 | 0.634（118/186） |

### Clean Completion

行序与上表相同。Granite 的 Clean 宏平均高于 Gemma-12B，是停机税，不是 Granite 更会做题。

| 模型 | Loc | Edit | Testgen | Repro | Review | **宏平均** | 微平均 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen3.5-9B | 0.303 | 0.867 | 0.923 | 0.692 | 1.000 | 0.757 | 0.763（142/186） |
| Ministral-14B | 0.091 | 0.644 | 0.026 | 0.846 | 0.833 | 0.488 | 0.489（91/186） |
| Ministral-8B | 0.091 | 0.578 | 0.282 | 0.538 | 0.567 | 0.411 | 0.419（78/186） |
| Qwen3-14B | 0.091 | 0.467 | 0.462 | 0.410 | 0.233 | 0.333 | 0.349（65/186） |
| Gemma-3-12B | 0.000 | 0.000 | 0.077 | 0.026 | 0.467 | 0.114 | 0.097（18/186） |
| Granite-4.1-8B | 0.000 | 0.244 | 0.077 | 0.077 | 0.300 | 0.140 | 0.140（26/186） |
| Gemma-3-4B | 0.000 | 0.067 | 0.000 | 0.000 | 0.267 | 0.067 | 0.059（11/186） |
| Ministral-3B | 0.000 | 0.044 | 0.051 | 0.000 | 0.000 | 0.019 | 0.022（4/186） |
| Qwen3-8B | 0.091 | 0.000 | 0.000 | 0.000 | 0.000 | 0.018 | 0.016（3/186） |
| Llama-3.2-3B | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000（0/186） |
| Qwen3.8-27B | 0.485 | 0.978 | 0.923 | 0.872 | 0.967 | 0.845 | 0.855（159/186） |
| Qwen3.6-35B-A3B | 0.364 | 0.644 | 0.923 | 0.103 | 0.767 | 0.560 | 0.559（104/186） |

## 两处诊断

**同一 harness 下任务族可以显著分化。** Ministral-14B Artifact 宏平均 0.497：Repro 0.85、Testgen 0.03。Qwen3-8B 与 Qwen3.5-9B 也不是单纯的 8B→9B。

**产物正确不等于干净完成。** 全表 halt **105** 次。Gemma-3-12B Artifact 宏平均 0.313（60/186），Clean 0.114（18/186），Gap **0.199**；Edit Artifact 0.53，Clean Edit 为 0。

明细、停机构成和 infra 勘误见 [`结果报表.md`](结果报表.md)。

## 协议快照

- Agent：自写 compact-shell v0.1.1（Harbor `BaseAgent`）。每轮一条 bash 围栏或一个空 finish 围栏。不是 Terminus-2 fork。
- 预算：最多 20 轮、命令 60 秒、观察 8000 字符。温度 0。Qwen thinking 关。禁止 provider fallback。
- 沙箱：Harbor + Novita，`n=1`。k=3 独立沙箱重复。
- 发表轨道：**API Standard**。Local Reference（钉死 HF 权重 + vLLM）尚未跑，不要把本表说成已控制权重。
- 题库 62：Loc 11、Edit 15、Testgen 13、Repro 13、Review 10。Easy 12 / Medium 38 / Hard 7 / Uncalibrated 5。标签是本系统 + k=3 的经验档，不是绝对难度。
- 有效性：infra 替换在后续时间窗口完成；provider / 顺序 / 采样冻结，API 后端时间漂移无法完全排除。

完整协议：[`STANDARD.md`](STANDARD.md)。冻结结果：tag **`benchmark-v1.0.1`**。tag `benchmark-v1.0` 保留作缺测记 0 的审计快照，不再当阅读主表。

## 文档

| 文件 | 看什么 |
|---|---|
| 本文 | 落地页、v1.0.1 排行榜、怎么跑 |
| [`项目说明.md`](项目说明.md) | 问题、设计、主结果、读法 |
| [`结果报表.md`](结果报表.md) | 五列全表、halt、难度、infra 勘误 |
| [`results/leaderboard.md`](results/leaderboard.md) | 从 canonical JSON 生成的排行榜 |
| [`STANDARD.md`](STANDARD.md) | 冻结协议与指标 |
| [`DIFFICULTY.md`](DIFFICULTY.md) | Easy / Medium / Hard / Uncalibrated |
| [`TRAPS.md`](TRAPS.md) | 失败模式；同族不重复 |
| [`models.lock.yaml`](models.lock.yaml) | 12 个配置 + 钉死的 provider |
| [`EVAL-NOTE.md`](EVAL-NOTE.md) | 过程笔记；§6.2 / §13 是 v1.0 审计 |

Gold、hidden 测试、mutant、foil 留在 Harbor `tasks/`，不会作为公开数据集泄露。

## 怎么跑

沙箱用 **Novita**（`-e novita`，`n=1`）。Agent 用 **compact-shell**，不要默认 Terminus-2。复制 `.env.example` 为 `.env`，不要提交 `.env`。已有一条 Novita job 时不要再开第二条。

```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = (Get-Location).Path

# 单题
harbor run --env-file .env -o jobs -p ./tasks/loc-member-discount `
  -a agents.compact_shell:CompactShellAgent `
  -m openrouter/qwen/qwen3.5-9b -k 1 -n 1 -e novita `
  --ak 'llm_call_kwargs={"extra_body":{"enable_thinking":false}}'

# 打分
python scripts/score_standard.py jobs/<job>
```

oracle 必须 1.0，nop 必须 0.0：

```powershell
harbor run --env-file .env -o jobs -p ./tasks/loc-bind-host -a oracle -k 1 -n 1 -e novita
harbor run --env-file .env -o jobs -p ./tasks/review-clip-incomplete -a nop -k 1 -n 1 -e novita
```

锁定名单与补格子：`python scripts/run_locked.py`（见 [`STANDARD.md`](STANDARD.md)）。不要覆盖 `jobs/locked-core.json`、`jobs/locked-core-k3.json`、`jobs/locked-hard-release-k3.json`。
