# small-ow-agent-bench：评测笔记（草稿）

状态：协议已冻、Core 47 已冻；**k=1 探索矩阵已齐**（10 main + Qwen3.8-27B 尺子）。正式主表仍是 k=3，还没开。本文不是正式论文，给公开仓库和评测实习答辩用。

一句话：不是追求大家都考 50 分，而是测清 3B–9B 小模型会什么、不会什么，以及它和更大模型的能力边界在哪里。

## 1. 测什么，不测什么

测的是：**固定极薄 shell harness（`compact-shell`）下，五项原子能力的 0/1 剖面**。

不测：

- 模型「固有」coding 能力（换 Terminus-2 / SWE-agent 分数会变）
- 谁更会填 JSON / `task_complete`
- 真实 GitHub 多文件 issue（SWE-bench 式复合修复）
- 推理开着的 Reasoner（进 Reasoning 表）
- 27B / 34B 在小模型主榜上的名次（它们只当尺子）

两张表不要混：

| 表 | 问题 | 题从哪来 |
|---|---|---|
| **Core** | 3B / 8B / 9B 差在哪一列 | 47 道 unique-trap Medium |
| **Frontier** | 9B 稳定不会、27B 或 34B 稳定会的边界 | 目前为空；k=1 尺子见 §10，Hard 仍要 k=3 |

9B 在 Core 上偏高，如果题确实在档内，**不是 bench 坏了**。不要为了压分改成 subset loc、露出 hidden tests、或加 planner。

## 2. 相关工作：借了什么，没搬什么

五项原子的接口来自 Ma & Liu et al., 2026，[Scaling Coding Agents via Atomic Skills](https://arxiv.org/abs/2604.05013)。那篇是对 GLM-4.5-Air（106B / 12B 激活）做 joint RL 的**训练**工作。公开小模型评测集、Core vs Frontier、3B–9B 主榜，他们没有做。我们做的是同一组原子的 **小模型评测对照**。

单原子前人已经分别测过，我们借构造和验收，不借原题：

| 工作 | 他们测 | 我们借 | 我们不搬 |
|---|---|---|---|
| SWE-bench / TB3 | 真实仓库复合任务 | 「执行即奖励」 | 整仓 issue；3B 会全 0 |
| LocAgent / Loc-Bench / Agentless | 真实仓定位 | 精确文件集合；decoy / 再导出 / 测文件当干扰 | Loc-Bench 原实例 |
| SWT-Bench | 复现测试 F2P | 坏仓失败、补丁后成功 | GitHub 复现脚本原题 |
| LiveCodeBench / HumanEval / Aider | 单次写代码 | 边角陷阱（`or` 默认值、闰年） | 竞赛题当 agent 原子 |
| SmallCode 内部 100 题 | 产品烟测 | — | 不当研究主表 |

`TRAPS.md` 每条陷阱只进 Core 一次。同构换皮进库存，不算 47。

## 3. 协议（冻结对象）

Agent 是 `compact-shell`：每轮只输出一个 ` ```bash ` 或 ` ```finish `。没有 JSON 工具、planner、记忆、自动停。Harbor 管沙箱和 hidden verifier。Terminus-2 只做对照，不进正式表。

评分只看冻结沙箱：

- hidden pytest 全过 → `atomic_correct = 1`
- 否则 0
- 超时仍打分；已经写对但没停 → 1，只标 `termination = tle`
- 429 / BuildException → `infra`，不进 mean，白名单可重试
- 错产物、空转、格式失败 → **不重跑**

正式发表：每题 \(p_i =\)（k 次里 atomic=1 的次数）/ k。主表 k=3。k=1 只用来区分 Core 题，标 draft。

五行：Localization / Editing / Testgen / Repro / Review。不强制总分排名。

## 4. Core 47 在诊断什么

| 原子 | n | 产物 | 会 = |
|---|---|---|---|
| Loc | 8 | `/app/answer.txt` 文件列表 | canonicalize 后与 gold 集合相等 |
| Edit | 12 | 改 `/app/repo` | hidden `/tests` 全过 |
| Testgen | 10 | `tests/test_*.py` | gold 过且全部 mutant 挂 |
| Repro | 10 | `/app/repro.py` | 坏仓失败、gold 后成功 |
| Review | 7 | `/app/answer.txt` 的 0/1 | 抽出唯一 bit == 标签 |

Loc 的分界已经在家族、不在「Hard」：标定里 8B unique-trap loc 接近 0，9B 多数能过精确集合。Edit 对 9B 接近饱和。完整题表见 [`README.md`](README.md)。

## 5. 难度梯子（经验，不进正式表）

| 角色 | 模型 | 上 3B–9B 主榜？ |
|---|---|---|
| 地板 | Ministral 3B | 附录 |
| 目标 | Qwen3.5-9B | 是 |
| 同档 | Ministral 8B | 是 |
| 尺子 | Qwen3.8-27B（thinking 关，`akashml/bf16`）；34B 可选 | **否** |

- Medium / Core：8B 或 9B 能过
- Hard / Frontier：9B **稳定**不过，且 27B 或 34B **稳定**能过（优先 k=3）
- 不入档：尺子也过不了（如 L9 精确集合）

不准用一次 k=1 零、TLE、或 halt 失败造 Hard。2026-08-22 Terminus-2 标定：**没有锁死的 Frontier 题**。L5 loc 是 9B 和 27B 一起挂。

## 6. 结果表（待填）

### 6.1 compact-shell k=1 Core 筛查（draft，2026-08-23）

跑法：`python scripts/run_core_k1.py --run`。9B 然后 8B。产物：`jobs/core-k1-screen.json`。约 86 分钟，incomplete 0。**不是正式表。**

| 模型 | Loc | Edit | Testgen | Repro | Review | 五列均分 |
|---|---|---|---|---|---|---|
| Qwen3.5-9B | 0.625 | 1.000 | 0.800 | 0.400 | 1.000 | 0.765 |
| Ministral 8B | 0.125 | 0.917 | 0.300 | 0.600 | 0.429 | 0.474 |

题级角色：

| 角色 | n | 题 |
|---|---|---|
| discriminator | 20 | Loc：similar-filenames / failing-test-impl / reexport / unused-fix。Edit：timeout-zero。Testgen：clip / unique-order / mean / parse / anagram / greet-none / window。Repro：off-by-one / keep-zero / none-name / float-cents。Review：mean-wrong / configured-timeout / rotate-right / prefix-complete |
| smoke | 20 | 几乎全是 Edit；另有 loc-member-discount、testgen-timeout-zero / cents、若干 repro、3 道 review |
| both_miss | 7 | loc-bind-host、loc-vip-two-files、loc-traceback-helper、testgen-gregorian、repro-zero-timeout、repro-whitespace、repro-truthy-flag |
| incomplete | 0 | — |

读法：Core **有区分度**，主要在 Loc / Testgen / Review，不在 Edit。9B Repro（0.40）低于 8B（0.60）——和 10 题烟测一样，9B 更容易写完 repro 再去改仓库。both_miss **不是 Hard**，除非 27B/34B 稳定能过。

### 6.2 正式 Core 表（k=3，未开）

| 模型 | Loc | Edit | Testgen | Repro | Review | 轨迹 |
|---|---|---|---|---|---|---|
| Qwen3.5-9B | — | — | — | — | — | API / Local Reference |
| Ministral 8B | — | — | — | — | — | 同上 |

### 6.3 已有、但不得写入上表的标定（Terminus-2）

仅作历史。9B rest 38/39；8B rest 28/39；8B loc 0/8；Granite 47 题 Harbor mean 0.40。详见 [`DIFFICULTY.md`](DIFFICULTY.md)。

## 7. 已经看到的负结果

- 没有锁死的「9B 稳定不过、27B 稳定能过」loc。k=1 上有 4 道候选，见 §10；3 道尺子也 0，不入 Hard。
- L9 精确集合：9B / 14B / 27B 都是 gold+decoy → 不入档，不改成 subset。
- `review-dollar-cents`：9B 过过、27B k=1 写过 1 → 不是 Hard。
- compact-shell 10 题烟测：9B 9/10；唯一 0 是 `repro-whitespace`（写出 repro 后又修了仓库）。协议 clean。这是任务理解，不是 JSON 税。

## 8. 10-model k=1 正式判断（2026-08-24）

工程链路成功（490/490，infra=0，无 `timeout_loop`）。Core 是有效的 **E2E 探索矩阵**（model + compact-shell），不是纯代码能力。legacy `protocol_pass` 命名错误：它是 `preflight_both_pass`（两道烟测都做对且干净停），**不能**说 8 个模型协议不兼容。Qwen3.5-9B 标了 fail 却 37/47，只因 `collect-todos` 写对了没干净 `finish`。

同一批数据拆三张矩阵（`python scripts/relabel_locked.py` → `jobs/locked-matrices.json`，**不覆盖** `locked-core.json`）：Atomic / Termination / E2E。unfinished 记 0/1，不当缺失。主表报 E2E；Atomic-IRT 作能力分析；差值是「会做但不会停」。失败要拆：atomic / format / termination。7 道全 0 Loc 标 `uncalibrated_above_range`，不进普通 Rasch MLE；先看 precision/recall，不要先当 verifier bug 或「都不会定位」。

尺子已跑，见 §10。本地 tag `benchmark-v1.0-rc1` 已打。还没做（不抢 Novita）：Frontier；正式表 k=3。

## 9. Loc 审计 + 探索性 1PL（同一批 490，未重跑）

`python scripts/audit_loc.py` → `jobs/loc-audit.json`。`python scripts/fit_irt.py --score both` → `jobs/irt-draft.json`。

**7 道全 0 Loc 不是「都不会定位」。** Instruction 要的是必须改的最小集合；exact-set 0/1 保留。诊断：

| 题 | gold | 写了 answer | 召回=1（含 gold 但多报） | 读法 |
|---|---|---:|---:|---|
| loc-member-discount | `pricing.py` | 7 | 3 | 过报 catalog/checkout |
| loc-bind-host | `serve.py` | 7 | 5 | 典型 decoy `netutil.py`（9B/8B/14B 同错） |
| loc-vip-two-files | `checkout.py` + `pricing/vip.py` | 6 | 2 | 过报；Gemma-12B 写成 `repo/...`（路径前缀，不是找不到） |
| loc-similar-filenames | `text/normalize.py` | 6 | 2 | decoy `normalize_legacy.py` |
| loc-traceback-helper | `codec.py` | 4 | 4 | gold 在，多报 loader/records |
| loc-failing-test-impl | `tax.py` | 6 | 3 | 过报 invoice / 测文件 |
| loc-reexport | `pkg/core.py` | 7 | 4 | 典型 decoy `pkg/net.py` |
| loc-unused-fix | `serve.py` | 8 | 6 | **唯一有 atomic=1 的 Loc**（6/10） |

9B 在 bind-host / reexport 上是 **R=1 P=0.5** 后干净停，不是没交卷。它对另外 5 道没写出 `answer.txt`，但题级模式仍是过报，不是 verifier 坏了。不改成 subset，不铸 Hard。

**探索性 1PL（40 道 calibrated；7 道 Loc 全 0 不进 MLE）：**

- Atomic θ 序：Qwen3.5-9B (4.43) > Ministral-14B (1.94) > Ministral-8B (1.52) > Qwen3-14B (1.11) > Gemma-12B (0.56) > Granite (−0.21) > Gemma-4B = Ministral-3B (−1.91) > Qwen3-8B (−2.39) > Llama-3.2-3B (−3.16)
- E2E 丢掉 Llama / Ministral-3B（校准题上 E 全 0，无有限 θ）。其余序与 Atomic 一致（θ Spearman **0.976**，b Spearman **0.88**）
- Gemma-12B Atomic 中等、E2E 掉到 −1.37：停机损失，不是不会做
- 40 道 irt_candidate 的 corrected item-total \(r\) 均 ≥ 0.2，**没有负区分题**
- 最易：`review-slug-complete`、`loc-unused-fix`、`edit-hhmmss`。最难（仍在量表内）：`testgen-parse`、`repro-whitespace`、`review-configured-timeout`

这是 k=1 探索拟合，不是正式量表。k=3 之前不要用这些 \(b\) 贴标签。尺子进矩阵后的题角色见 §10（7 道全 0 Loc 里 4 道被 27B 拉开）。

答辩时用这句话：这是 3B–9B 的技能剖面仪，不是 SWE-bench 替代品，也不是「小模型已经能当 Cursor」的证据。

## 10. Qwen3.8-27B 尺子（k=1，不进 θ，2026-08-24）

跑法：`python scripts/run_locked.py --run --full --group ruler`。约 33 分钟，协议 2 + Core 47 = **49** 格，并入已有 `jobs/locked-core.json`（**不擦** 10 模型行）。`n_incomplete=0`。`python scripts/relabel_locked.py` / `audit_loc.py` 已重跑。拟合仍 `--group main`：27B **不进** \(\theta\)。

协议：`preflight_both_pass=true`（`hello-world`、`collect-todos` 都对且干净停）。

| | Atomic | E2E | 停机 clean |
|---|---|---|---|
| 总分 | **44/47 (0.94)** | 43/47 (0.92) | 45/47 (0.96) |
| Loc | **5/8 (0.625)** | 4/8 | |
| Edit / Testgen / Repro / Review | **全 1.0** | 全 1.0 | |

失败只有 Loc 四格：`task_pass_clean` 43、`task_pass_unfinished` 1、`task_fail_clean` 2、`task_fail_unfinished` 1。无 `format_fail` / `no_attempt` / infra。

**Loc 明细（exact-set 保留）：**

| 题 | 10 main 过 | 27B Atomic | 27B 交卷 | 读法 |
|---|---:|---|---|---|
| loc-unused-fix | 6/10 | 1 干净 | `serve.py` | 易题；不是边界 |
| loc-member-discount | 0/10 | 1 干净 | `pricing.py` | k=1 Hard **候选** |
| loc-vip-two-files | 0/10 | 1 **没停** | gold 两文件 | Atomic 过、E2E 0；9B 在 Terminus-2 `k=3` 已 3/3 |
| loc-similar-filenames | 0/10 | 1 干净 | `text/normalize.py` | k=1 Hard **候选** |
| loc-failing-test-impl | 0/10 | 1 干净 | `tax.py` | k=1 Hard **候选** |
| loc-bind-host | 0/10 | 0 干净 | `serve.py`+`netutil.py`（R=1 P=0.5） | 尺子也过报 decoy；**不是 Hard** |
| loc-traceback-helper | 0/10 | 0 干净 | 只写 `data/records.txt`（读过 `codec.py`） | 与 Terminus-2 L5 同错；**不是 Hard** |
| loc-reexport | 0/10 | 0 没停 | 没写 `answer.txt`（摸过 `pkg/core.py`） | 未交卷，不是「提交了 decoy」；**不是 Hard** |

全 11 模型仍全 0 的三道标 `uncalibrated_above_range`：`loc-bind-host`、`loc-traceback-helper`、`loc-reexport`。`n_both_miss` 7→**3**，`n_discriminator` 40→**44**，smoke 0。不改 subset，不铸 Hard，不把 27B 塞进 θ。

Frontier 仍空。那 4 道「main 全 0 / 27B Atomic=1」只是 **k=1 候选**；正式 Hard 要 9B **稳定** 0 且尺子 **稳定** 1（优先 k=3）。`loc-vip-two-files` 尤其不能从这次没停的 1 铸 Hard。
