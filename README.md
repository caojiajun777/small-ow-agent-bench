# Small-OW-Agent-Bench

[![Leaderboard](https://img.shields.io/badge/leaderboard-v1.0.1-0f4c81)](results/leaderboard.md)
[![License](https://img.shields.io/badge/license-Apache%202.0-2f6f4e)](LICENSE)
[![Hugging Face](https://img.shields.io/badge/Hugging%20Face-catalog-ffcc00)](https://huggingface.co/datasets/junjun77/small-ow-agent-bench)
[![GitHub](https://img.shields.io/badge/GitHub-caojiajun777-181717)](https://github.com/caojiajun777/small-ow-agent-bench)

> 一台家用主机上的小模型，能接住多少 Coding Agent 的工作？

Coding Agent 花钱的地方不只在最后那段答案。为了改三行代码，它可能要先扫目录、读文件、运行测试、修改代码，再把测试跑一遍，整条操作轨迹都在消耗 token。难题值得交给最强的模型，但工程任务并不都难到同一个程度。找文件、修一处局部逻辑、补几条测试或复现一个 Bug，范围明确，结果也能直接验证。如果小模型做得来，每次都调用最高规格的 API 就未必划算。

开放权重模型还可以留在本地或公司内网。代码不必发给外部服务，模型版本可以固定，也方便量化和定制；团队不再按调用量支付 API 费用，也不会受第三方限流影响。榜单中的 16 个配置总参数量介于 3B 和 35B。经过合适的低比特量化，它们都能在一台内存或显存足够的家用高性能主机或个人工作站上运行，不需要多机服务器、专用集群或定制加速器。3B 至 14B 的部署门槛较低，20B 至 35B 则需要更多内存或显存。

当然，本地部署也有硬件和运维成本。模型如果做不对，省下来的 API 费用没有意义。我们做 Small-OW-Agent-Bench，就是想把问题先问清楚：这些能在个人设备上部署的小模型，究竟能完成哪些 Coding Agent 任务；做不出来时，又卡在哪一步？

评测包含 62 道自动判分的代码任务，题目中保留了软件工程里常见的陷阱。我们测试了 16 个开放权重模型配置，每个模型在每道题上独立运行 3 次，共完成 2,976 次沙箱实验。这套题既可以比较现有模型，也可以继续接入以后发布的模型，找出它们擅长和薄弱的环节，为后训练和 Coding 能力改进提供依据。

## 为什么用代码来测

因为代码可以直接运行，答案对不对可以交给程序验收。模型要进入终端、阅读仓库、修改文件、运行测试，还要根据反馈调整做法，并在任务完成后停下来。这些动作串在一起，正好构成一个 Coding Agent 的基本工作循环。评分只看最后留下的结果，不看回答写得是否漂亮，也不需要另一个 LLM 充当裁判。

这只是观察通用智能的一个窄窗口。它测的是模型能否在一批可执行、有反馈、能验收的软件工程任务中完成工作，不是一套 AGI 测试。

## 我们怎么拆任务

一次失败可能有很多原因：文件找错了、代码没改对、测试没写好，或者任务已经完成，Agent 却没有停下来。单个 Pass/Fail 看不出问题出在哪，所以我们把工作流程拆成五个可以单独验收的环节：

| 任务 | 模型要做什么 | 怎样算成功 |
|---|---|---|
| 找文件（Localization） | 根据问题描述找出需要修改的文件 | 文件一个不能少，也不能多报 |
| 修改代码（Editing） | 已经告诉目标文件，完成指定修改 | 隐藏测试全部通过 |
| 编写测试（Test Generation） | 为给定函数编写测试 | 正确实现通过，错误实现被测试发现 |
| 复现 Bug（Reproduction） | 编写能稳定触发问题的复现程序 | 修复前失败，修复后成功 |
| 判断补丁（Patch Validation） | 判断给出的补丁是否真的解决问题 | 输出的判断与标准答案一致 |

五列分别对应定位、实现、测试、复现和补丁判断。两个总分相近的模型，短板可能完全不同。

## 两个分数

代码改对了，不代表 Agent 完整走完了流程。我们分别记录结果和过程。

| 通俗名称 | 技术名称 | 意思 |
|---|---|---|
| **结果正确率** | Artifact Correctness | Agent 最终是否留下了正确结果 |
| **完整完成率** | Clean Completion | 结果正确，而且 Agent 正常宣布完成并停止 |

例如，Agent 已经正确修改了文件，却继续反复运行测试，直到 20 轮预算耗尽。这次实验的结果正确率记 1，完整完成率记 0。下文把这种情况叫作 `做对但没停`。

排行榜将五类任务等权平均，避免题目更多的类别占便宜。每一次尝试的分子、分母和五列明细都在 [`结果报表.md`](结果报表.md)。

## 为什么这些题能分出差异

题目难只是一个条件。更重要的是，分数差异要能指向具体行为，评分还要经得起重复检查。

五类任务各有明确的输入和产物。找文件只提交文件集合；修改代码会直接给出目标文件；编写测试不能改实现；复现 Bug 不能修仓库；判断补丁只提交判断结果。验收规则同样具体：文件集合必须完全一致，多报一个相似文件也算错；代码修改必须通过隐藏测试；生成的测试既要放过正确实现，也要找出人为构造的错误实现；Bug 复现要在修复前失败、应用标准补丁后通过；补丁判断则与固定标签核对。每套评分程序都经过标准解和空操作基线检查，标准解必须通过，什么都不做必须失败。

62 道题也不是同一个难度。在当前冻结系统下，经验分布为 Easy 12、Medium 38、Hard 7、Uncalibrated / Out-of-range 5，既有小模型能够完成的题，也有当前上界模型仍然不稳定的题。这些标签只描述当前模型集合和协议下的经验难度；我们不会看完排行榜，再回头修改题目或评分程序。每个 `模型配置 × 任务` 组合在独立沙箱中运行 3 次，Agent 接口、20 轮预算、隐藏验证器和评分规则保持不变。API 或平台故障不算模型失败；选错文件、产物错误、格式错误、耗尽预算和未正常结束仍按协议计分。

结果正确率看模型留下了什么，完整完成率再看它是否正常停下。排行榜比较的是模型在冻结 compact-shell 协议中的端到端表现，不是脱离 API 供应商、推理参数和 Agent 接口之后的所谓模型固有能力。

## 排行榜（v1.0.1）

16 个配置放在同一张表中，按结果正确率排序。深色条是结果正确率，浅色条是完整完成率；两者之间的差距，就是模型已经留下正确产物，却没有正常结束的实验。

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

Qwen3.6-35B-A3B 是约 3B 激活的 MoE，不能把它当成 27B dense 的下一档。表格只按实测分数排序，与参数量顺序无关。

## 这张榜怎么用

这张榜更适合用来做模型路由，而不是简单挑一个总分最高的模型。先看五类任务的分数，再按实际工作选择候选模型。范围小、调用频繁、能够自动验收的任务，可以先交给小模型，再用测试或确定性规则检查；没有通过验证或风险较高的任务，再升级给更强的模型或人工处理。榜单不能替团队划定风险边界，但可以帮助团队决定先试哪个模型。

## 口径和限制

所有实验都在独立 Linux 沙箱中运行。模型看不到隐藏测试，最多进行 20 轮终端交互。我们固定了 API 供应商、推理参数和 Agent 接口，所以比较的是 `模型 + API 线路 + Agent 接口` 这套完整配置，而不是单独比较模型权重。实验走固定 API 线路，并非本地推理测试。上文所说的消费级单机可部署，是指开放权重经过合适量化，并有足够内存或显存时可以运行；这不表示本次实验使用了本地硬件，也不表示量化后的表现与榜单配置相同。完整协议、16 个模型配置和复现入口见 [`STANDARD.md`](STANDARD.md)。

v1.0.1 没有统一测量本地 GPU 成本、吞吐量、延迟或单位成功任务成本，也没有把最强闭源模型放进同一协议对照。这是一份能力与可靠性数据，不是价格性能榜。结果不能证明小模型已经达到闭源前沿模型的能力，也不能证明本地部署一定更省钱。完整的性价比比较还需要计入硬件、量化方式、利用率和部署规模。

## 深入阅读

- [`项目说明.md`](项目说明.md)：设计动机、方法和主要结论
- [`结果报表.md`](结果报表.md)：全部模型、任务族和失败分析
- [`STANDARD.md`](STANDARD.md)：环境、参数和运行方式

<details>
<summary>运行一个任务</summary>

沙箱使用 Novita，Agent 使用 compact-shell。先把 `.env.example` 复制为 `.env`，不要提交 `.env`。如果已有评测任务在运行，请等它结束后再启动下一条。

```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = (Get-Location).Path

harbor run --env-file .env -o jobs -p ./tasks/loc-member-discount `
  -a agents.compact_shell:CompactShellAgent `
  -m openrouter/qwen/qwen3.5-9b -k 1 -n 1 -e novita `
  --ak 'llm_call_kwargs={"extra_body":{"enable_thinking":false}}'

python scripts/score_standard.py jobs/<job>
```

批量运行入口：`python scripts/run_locked.py`（见 [`STANDARD.md`](STANDARD.md)）。不要覆盖 `jobs/locked-core.json`、`jobs/locked-core-k3.json`、`jobs/locked-hard-release-k3.json`。

</details>

<details>
<summary>更多审计与开发文档</summary>

- [`DIFFICULTY.md`](DIFFICULTY.md)：Easy / Medium / Hard / Uncalibrated
- [`TRAPS.md`](TRAPS.md)：失败模式
- [`EVAL-NOTE.md`](EVAL-NOTE.md)：过程笔记
- [`HARD-RELEASE.md`](HARD-RELEASE.md)：Hard-15
- [`GATE-A.md`](GATE-A.md)：发布清单
- [`results/RELEASE-v1.0.1.md`](results/RELEASE-v1.0.1.md)：v1.0.1 技术审计
- [`results/leaderboard.md`](results/leaderboard.md)：生成的五列排行榜
- [`results/hf_catalog.jsonl`](results/hf_catalog.jsonl)：公开目录元数据；[Hugging Face](https://huggingface.co/datasets/junjun77/small-ow-agent-bench)
- [`CITATION.cff`](CITATION.cff)：引用

隐藏评分程序、标准答案和干扰补丁保留在 Harbor `tasks/` 中，不进入公开数据集。

</details>
