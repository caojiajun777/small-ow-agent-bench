# Small-OW-Agent-Bench

小型开放权重模型做 Coding Agent 时，究竟是不会找文件、不会改代码，还是已经把任务做对了，却不知道如何提交和停止？

本项目构建了 62 个短小、可自动判分的代码任务，分别测试找文件、修改代码、编写测试、复现 Bug 和判断补丁五类行为。我们在 16 个开放权重模型配置上将每道题独立运行 3 次，共完成 2,976 次有效沙箱实验。

主要发现：

- Qwen3.8-27B 是 16 个配置中整体表现最好的；Qwen3.5-9B 以 78.6% 排第二；
- GLM-4.7-Flash 以 55.3% 排第四，GPT-OSS-20B 以 48.6% 排第六；
- Ministral-14B 擅长复现 Bug，却几乎不会编写能发现错误的测试；
- Gemma-3-12B 经常已经正确修改代码，却因为不能正常停止而丢分。

A diagnostic benchmark for finding where small coding agents fail.

[![Tag](https://img.shields.io/badge/tag-benchmark--v1.0.1-0f4c81)](https://github.com/caojiajun777/small-ow-agent-bench/releases/tag/benchmark-v1.0.1)
[![License](https://img.shields.io/badge/license-Apache%202.0-2f6f4e)](LICENSE)
[![Hugging Face](https://img.shields.io/badge/Hugging%20Face-catalog-ffcc00)](https://huggingface.co/datasets/junjun77/small-ow-agent-bench)
[![GitHub](https://img.shields.io/badge/GitHub-caojiajun777-181717)](https://github.com/caojiajun777/small-ow-agent-bench)

## 我们测什么

| 任务 | 模型要做什么 | 怎样算成功 |
|---|---|---|
| 找文件（Localization） | 根据问题描述找出需要修改的文件 | 文件一个不能少，也不能多报 |
| 修改代码（Editing） | 已经告诉目标文件，完成指定修改 | 隐藏测试全部通过 |
| 编写测试（Test Generation） | 为给定函数编写测试 | 正确实现通过，错误实现被测试发现 |
| 复现 Bug（Reproduction） | 编写能稳定触发问题的复现程序 | 修复前失败，修复后成功 |
| 判断补丁（Patch Validation） | 判断给出的补丁是否真的解决问题 | 输出的判断与标准答案一致 |

所有任务都由程序自动判分，不使用 LLM 进行主观打分。

## 两个分数

不要混成一个「总分」。

| 通俗名称 | 技术名称 | 意思 |
|---|---|---|
| **结果正确率** | Artifact Correctness | Agent 最终是否留下了正确结果 |
| **完整完成率** | Clean Completion | 结果正确，而且 Agent 正常宣布完成并停止 |

例如，Agent 已经正确修改了文件，但仍然不断运行测试，直到 20 轮预算耗尽。这次实验的「结果正确率」记 1，但「完整完成率」记 0。下文把这类情况简称「做对但没停」。

排行榜把五类任务**等权平均**，避免某一类因为题目更多而获得更大权重。全部尝试的直接统计、分子分母和五列明细见 [`结果报表.md`](结果报表.md)。

## 排行榜（v1.0.1）

16 个配置全部进入同一张排名，按结果正确率排序。图里深色条是「结果有没有做对」，浅色条是「做对了并且正常停下来」；两条差一截，就是做对了却没停。

![16 个配置的结果正确率与完整完成率](results/figures/v1.0.1-compact10.svg)

| 模型 | 结果正确率 | 完整完成率 |
|---|---:|---:|
| <img src="results/figures/vendors/qwen.svg" width="16" height="16" alt="Qwen"> Qwen3.8-27B | 86.3% | 84.5% |
| <img src="results/figures/vendors/qwen.svg" width="16" height="16" alt="Qwen"> Qwen3.5-9B | 78.6% | 75.7% |
| <img src="results/figures/vendors/qwen.svg" width="16" height="16" alt="Qwen"> Qwen3.6-35B-A3B | 63.2% | 56.0% |
| <img src="results/figures/vendors/zai.svg" width="16" height="16" alt="Z.ai"> GLM-4.7-Flash | 55.3% | 42.4% |
| <img src="results/figures/vendors/mistralai.svg" width="16" height="16" alt="Mistral"> Ministral-14B | 49.7% | 48.8% |
| <img src="results/figures/vendors/openai.svg" width="16" height="16" alt="OpenAI"> GPT-OSS-20B | 48.6% | 41.5% |
| <img src="results/figures/vendors/mistralai.svg" width="16" height="16" alt="Mistral"> Ministral-8B | 45.6% | 41.1% |
| <img src="results/figures/vendors/qwen.svg" width="16" height="16" alt="Qwen"> Qwen3-14B | 40.4% | 33.3% |
| <img src="results/figures/vendors/nvidia.svg" width="16" height="16" alt="NVIDIA"> Nemotron-3.5-Lightning | 35.2% | 9.5% |
| <img src="results/figures/vendors/google.svg" width="16" height="16" alt="Google"> Gemma-3-12B | 31.3% | 11.4% |
| <img src="results/figures/vendors/ibm.svg" width="16" height="16" alt="IBM"> Granite-4.1-8B | 16.2% | 14.0% |
| <img src="results/figures/vendors/google.svg" width="16" height="16" alt="Google"> Gemma-4-26B-A4B | 13.0% | 13.0% |
| <img src="results/figures/vendors/google.svg" width="16" height="16" alt="Google"> Gemma-3-4B | 6.7% | 6.7% |
| <img src="results/figures/vendors/mistralai.svg" width="16" height="16" alt="Mistral"> Ministral-3B | 4.9% | 1.9% |
| <img src="results/figures/vendors/qwen.svg" width="16" height="16" alt="Qwen"> Qwen3-8B | 3.4% | 1.8% |
| <img src="results/figures/vendors/meta.svg" width="16" height="16" alt="Meta"> Llama-3.2-3B | 2.7% | 0.0% |

Qwen3.6-35B-A3B 是约 3B 激活的 MoE，不是 27B dense 的下一档；它进入同一张排名，分数也不表示参数量越大越高。

在 197 次实验中，Agent 已经留下了正确结果，却没有按协议正常结束。Nemotron-3.5-Lightning 是最明显的例子：70 次结果正确，只有 18 次完整完成。

## 评测方式

每次实验都在独立 Linux 沙箱中运行。模型最多进行 20 轮终端交互，无法看到隐藏测试。每个模型与任务组合独立运行 3 次。

所有模型使用固定的 API 供应商、推理参数和交互接口。因此分数衡量的是「模型 + API 线路 + Agent 接口」这一完整配置，不能理解为模型权重本身的绝对能力。

完整协议、模型配置与可复现入口见 [`STANDARD.md`](STANDARD.md)。当前公开结果是 v1.0.1 canonical 16 配置表。

## 深入阅读

- [`项目说明.md`](项目说明.md)：为什么这样设计，以及主要发现
- [`结果报表.md`](结果报表.md)：全部模型、任务族和失败分析
- [`STANDARD.md`](STANDARD.md)：环境、参数和运行方式

<details>
<summary>运行一个任务</summary>

沙箱用 Novita，Agent 用 compact-shell。复制 `.env.example` 为 `.env`，不要提交 `.env`。已有一条评测任务在跑时不要再开第二条。

```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = (Get-Location).Path

harbor run --env-file .env -o jobs -p ./tasks/loc-member-discount `
  -a agents.compact_shell:CompactShellAgent `
  -m openrouter/qwen/qwen3.5-9b -k 1 -n 1 -e novita `
  --ak 'llm_call_kwargs={"extra_body":{"enable_thinking":false}}'

python scripts/score_standard.py jobs/<job>
```

锁定名单与补格子：`python scripts/run_locked.py`（见 [`STANDARD.md`](STANDARD.md)）。不要覆盖 `jobs/locked-core.json`、`jobs/locked-core-k3.json`、`jobs/locked-hard-release-k3.json`。

</details>

<details>
<summary>更多审计与开发文档</summary>

- [`DIFFICULTY.md`](DIFFICULTY.md)：Easy / Medium / Hard / Uncalibrated
- [`TRAPS.md`](TRAPS.md)：失败模式
- [`EVAL-NOTE.md`](EVAL-NOTE.md)：过程笔记
- [`HARD-RELEASE.md`](HARD-RELEASE.md)：Hard-15
- [`GATE-A.md`](GATE-A.md)：发布清单
- [`results/RELEASE-v1.0.1.md`](results/RELEASE-v1.0.1.md)：相对 v1.0 改了什么
- [`results/leaderboard.md`](results/leaderboard.md)：生成的五列排行榜
- [`results/hf_catalog.jsonl`](results/hf_catalog.jsonl)：公开目录元数据；[Hugging Face](https://huggingface.co/datasets/junjun77/small-ow-agent-bench)
- [`CITATION.cff`](CITATION.cff)：引用
- [`STANDARD.md`](STANDARD.md)：16 个配置的冻结协议、模型路由与复现入口

隐藏评分程序、标准答案和干扰补丁留在 Harbor `tasks/`，不会放进公开数据集。

</details>
