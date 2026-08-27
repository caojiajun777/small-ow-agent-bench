# small-ow-agent-bench：评测笔记（草稿）

状态：协议已冻、Core 47 已冻；k=1 探索矩阵已齐；**正式 Core 主表 k=3 已齐**（10×47 + 尺子 7 道 Loc，每格 `n_valid=3`，产物 `jobs/locked-core-k3.json`，不覆盖 `locked-core.json`）。Hard-Release-15 已冻并跑完 6 个受试 × k=3（`jobs/locked-hard-release-k3.json`，90 格 `n_valid=3`，infra=0）。6 个缺测 compact 的 Hard-15 补全已齐（`jobs/locked-hard-floor-k3.json`，90 格 `n_valid=3`，**不覆盖**官方 Hard 锁，见 §12.4）。27B / 35B 全量 Base-47 k=3 已齐（`jobs/locked-upper-base-k3.json`，94 格 `n_valid=3`，**不进** compact-10 均值，见 §13）。Gemma-4B 429 side table 已齐（`jobs/locked-gemma4b-rerun-k3.json`，67/67，**不覆盖** core lock，见 §14）。13 格 infra 已替换（`jobs/locked-infra-rerun-k3.json`，13/13，见 §15）。**当前对外主表**是 v1.0.1 canonical matrix `results/canonical-coverage.json`（Hard 补全 + Gemma-4B 429 + infra 13；Gemma-4B 11/186；`remaining_dirty` 0；Headline 9B 0.786 / 27B 0.863）。冻结审计表仍见 §6.2（缺测记 0）。k=3 探索性 1PL 已拟合（`jobs/irt-k3.json`，Binomial(3)，不进发表均值）。Core Frontier 现为 2 道 Loc + 1 道 Testgen + 3 道 Repro + Hard-15 `loc-hook-plugin`（§11 / §13 / §15）。**v1.0 = API Standard（系统表）**。公开仓库：https://github.com/caojiajun777/small-ow-agent-bench。Local Reference 全表未跑。本文不是正式论文，给公开仓库和评测实习答辩用。

一句话：在 compact-shell 下用五个诊断维度，区分从玩具档到部署档（约 3B–35B）的开源小模型在 shell agentic coding 上「哪一列会、哪一列不会」。不是追求大家都考 50 分，也不主张这五项是基础智力或相互正交。

## 1. 测什么，不测什么

测的是：**固定 text-only compact-shell 协议下，完成原子 coding 任务的端到端可靠性。** 分数刻画模型 + 钉死的 OpenRouter 线路/量化 + Novita + harness 组成的**系统**，不是隔离后的权重智力。

| 层面 | 判断 |
|---|---|
| 工程与计分 | 对。同一语法与预算；产物经 hidden verifier；`atomic_correct` 与 `termination` 正交；oracle=1 / nop=0；infra 不进 mean；三次独立 `-k 1`；禁止 fallback；冻题后不按分改题。没有产物 / 没改仓库 / 没提交 → Atomic 0。不能因「可能看懂了」给分。 |
| 规则是否同一 | **程序公平**：没有为 9B 放宽、为 35B 加难、按模型身份判分。 |
| 是否无混淆的权重表 | **否。** provider、BF16/FP8、chat template、服务端与延迟不同。这是 **API 系统表**。可引用的权重表是 Local Reference。 |
| 是否固有 coding 能力 | **不能代表。** 通过还要求行动规划、合同、格式、提交与终止。 |

通过一次试验需要同时做到：理解任务、选出行动、写出规定产物、在需要时提交并终止。不要把这写成独立概率的乘积。

不测：

- 模型「固有」coding 能力（换一套更重的 agent，分数会变）
- 谁更会填 JSON / `task_complete`
- 真实 GitHub 多文件 issue（SWE-bench 式复合修复）
- 推理开着的 Reasoner（进 Reasoning 表）
- 把 27B / 35B 的名次塞进 3B–14B 主均值（它们是部署档 / Frontier，不是那张表的选手）

**能写：** 在固定 compact-shell + 钉死线路下，某模型某原子的端到端通过率。  
**不能写：** 本 bench 证明 Qwen 35B 的固有代码能力低于 Qwen 9B。  
**也不能写：** 35B 低分全是协议导致的，所以该从 mean 里剔除 protocol failure。

协议**限制**（声明，v1.0 不改）：每轮一个 bash；不接受 XML/native tool call；20 轮；180s 含 LLM 等待；Loc 必须写 `answer.txt`；Repro 坏仓必须非零退出。`finish` 约束的是 E2E / `termination=clean`，**不是 Atomic**——产物对但没停仍记 Atomic 1。

协议**错误**才是否决项：instruction 与 verifier 矛盾；正确产物被判 0；模型预算不同；parser 与文档不符；provider 偷偷 fallback；infra 记成任务 0；attempt 串线。Hard-15 轨迹里没有这些。改回合数 / parser / finish / Repro 合同 / Atomic 规则等于新实验。宽松协议或 Local vLLM 只做后续 sensitivity，不覆盖主表。

两张表不要混：

| 表 | 问题 | 题从哪来 |
|---|---|---|
| **Core** | 3B / 8B / 9B 差在哪一列 | 47 道 unique-trap Medium |
| **Frontier** | 9B 在 v1.0 为 0/3、27B 或 34B Atomic 为 3/3 | Core 47 里 5 道（§11 / §13）；Hard-15 按同一梯子只锁住 `loc-hook-plugin`（§12） |

9B 在 Core 上偏高，如果题确实在档内，**不是 bench 坏了**。不要为了压分改成 subset loc、露出 hidden tests、或加 planner。

## 2. 相关工作：借了什么，没搬什么

我们不主张 Agentic Coding 只有五种基础能力。选 Loc / Edit / Testgen / Repro / Review，是因为它们同时满足：仓库级 issue 里高频出现；能通过任务设计隔离；产物明确；可确定性判分。SWE / Terminal-Bench 只有复合 Pass/Fail；Loc-Bench / Agentless 说明定位可单独测；SWT-Bench 说明复现可单独测；Aider 与 SWE 经常对不上，说明编辑 ≠ 修 issue。本 bench 把这五列写成同一套短题协议。能力解耦看完整 62 的列间差。

单列前人已经分别测过，我们借构造和验收，不借原题：

| 工作 | 他们测 | 我们借 | 我们不搬 |
|---|---|---|---|
| SWE-bench / TB3 | 真实仓库复合任务 | 「执行即奖励」 | 整仓 issue；3B 会全 0 |
| LocAgent / Loc-Bench / Agentless | 真实仓定位 | 精确文件集合；decoy / 再导出 / 测文件当干扰 | Loc-Bench 原实例 |
| SWT-Bench | 复现测试 F2P | 坏仓失败、补丁后成功 | GitHub 复现脚本原题 |
| LiveCodeBench / HumanEval / Aider | 单次写代码 | 边角陷阱（`or` 默认值、闰年） | 竞赛题当 agent 原子 |
| SmallCode 内部 100 题 | 产品烟测 | — | 不当研究主表 |

`TRAPS.md`：同一任务族内不重复同一失败模式；跨任务族允许复用（如显式 `0` 被 `or` 吃掉）并记录。同构换皮进库存，不算公开 47。

## 3. 协议（冻结对象）

Agent 是 `compact-shell`：每轮只输出一个 ` ```bash ` 或 ` ```finish `。钉死的是交互接口和资源预算（无 JSON 工具、无 harness 侧 planner / 自动停）。规划、搜索和上下文管理仍是影响五项结果的潜在机制，暂不做成独立产物任务；格式、提交和终止作为交互可靠性单独报告。Harbor 管沙箱和 hidden verifier。Terminus-2 只做对照，不进正式表。测量对象的完整表述见 §1 与 [`STANDARD.md`](STANDARD.md)。

评分只看冻结沙箱：

- hidden pytest 全过 → `atomic_correct = 1`
- 否则 0
- 超时仍打分；已经写对但没停 → 1，只标 `termination = tle`（或 Hard-15 上未 `finish` 则 `protocol_error`，Atomic 仍可以是 1）
- 429 / BuildException → `infra`，不进 mean，白名单可重试
- 错产物、空转、格式失败 → **不重跑**

正式发表：每题 \(p_i =\)（k 次里 atomic=1 的次数）/ k。主表 k=3。k=1 只用来区分 Core 题，标 draft。同时报 E2E（Atomic ∧ 干净停）和失败构成（§12.2），不从 Atomic 里抠 protocol。

五行：Localization / Editing / Testgen / Repro / Review。不强制总分排名。

## 4. Core 47 在诊断什么

| 原子 | n | 产物 | 会 = |
|---|---|---|---|
| Loc | 8 | `/app/answer.txt` 文件列表 | canonicalize 后与 gold 集合相等 |
| Edit | 12 | 改 `/app/repo` | hidden `/tests` 全过 |
| Testgen | 10 | `tests/test_*.py` | gold 过且全部 mutant 挂 |
| Repro | 10 | `/app/repro.py` | 坏仓失败、gold 后成功 |
| Review | 7 | `/app/answer.txt` 的 0/1 | 抽出唯一 bit == 标签（Patch Validation，不是完整代码审查） |

Loc 仍是 Core 最硬的一列。compact-shell k=3 上 8B Loc 0.21、9B Loc 0.33，都远谈不上「多数能过精确集合」（那是 Terminus-2 标定，不要混进主表）。Edit 对 9B 饱和（12/12，`p=1.00`）。完整题表见 [`README.md`](README.md)。Hard 锁法见 §11。

## 5. 难度梯子（经验，不进正式表）

| 角色 | 模型 | 上 3B–9B 主榜？ |
|---|---|---|
| 地板 | Ministral 3B | 附录 |
| 目标 | Qwen3.5-9B | 是 |
| 同档 | Ministral 8B | 是 |
| 尺子 | Qwen3.8-27B（thinking 关，`akashml/bf16`）；34B 可选 | **否** |

- Medium：8B 或 9B 能过，且不是 Easy
- Hard / Frontier：v1.0 观察到 9B 为 0/3，且 27B 或 34B Atomic 为 3/3
- 未标定：9B 为 0/3，尺子达不到 3/3（仍计分，不是有序「极难」）

不准用一次 k=1 零、TLE、或 halt 失败造 Hard。Terminus-2 2026-08-22 标定当时没有 Frontier。compact-shell k=3 先锁了 2 道 Atomic Hard Loc（`loc-member-discount`、`loc-vip-two-files`），见 §11。27B Base-47 k=3 齐了之后又锁 `testgen-anagram`、`repro-first-index`、`repro-whitespace`（§13）。infra 勘误后另锁 `repro-nested-alias`（§15）。L5 `loc-traceback-helper` 在本协议下是 9B 3/3、27B 0/3，更不是 Hard。

## 6. 结果表

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

读法：Core **有区分度**，主要在 Loc / Testgen / Review，不在 Edit。9B Repro（0.40）低于 8B（0.60）——和 10 题烟测一样，9B 更容易写完 repro 再去改仓库。both_miss **不是 Hard**，除非尺子在 v1.0 为 Atomic 3/3。

### 6.2 正式 Core 表（compact-shell k=3，API，2026-08-25）

跑法：`python scripts/run_locked.py --run --k3-fill --group main`，再 `--group ruler`。attempt=1 来自 `jobs/locked-core.json`，只补 2 和 3。产物 **`jobs/locked-core-k3.json`**（**不覆盖** k=1）。范围 477 格，全部 `n_valid=3`。尺子只补 7 道 Loc（不含易题 `loc-unused-fix`）。轨迹仍是 OpenRouter API；Local Reference 未做。

格子分数是三次独立沙箱的 \(p_i\)。技能列是该原子上全部 62 道 \(p\) 的均分（\(S_{\mathrm{atom}}\)：Loc 11 / Edit 15 / Testgen 13 / Repro 13 / Review 10）。**五项宏平均** = 五列再平均；**题微平均** = 成功 attempt / \(186\)。v1.0 冻结表把未跑的 Hard-15 记 \(p=0\)（标 †）。补测见 §12.4。需要一个标题分时用五项宏平均。

**Atomic（规定产物正确率；写对但没停仍记 1）**

| 模型 | Loc | Edit | Testgen | Repro | Review | 五项宏平均 | 题微平均 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen3.5-9B | 0.242 | 0.933 | 0.923 | 0.769 | 1.000 | **0.774** | 0.785（146/186） |
| Ministral-14B | 0.091 | 0.689 | 0.026 | 0.846 | 0.833 | 0.497 | 0.500（93/186） |
| Ministral-8B | 0.152 | 0.689 | 0.308 | 0.564 | 0.533 | 0.449 | 0.462（86/186） |
| Qwen3-14B | 0.091 | 0.467 | 0.462 | 0.436 | 0.567 | 0.404 | 0.409（76/186） |
| Gemma-3-12B † | 0.000 | 0.467 | 0.179 | 0.256 | 0.300 | 0.241 | 0.253（47/186） |
| Granite-4.1-8B † | 0.000 | 0.289 | 0.077 | 0.077 | 0.200 | 0.129 | 0.134（25/186） |
| Ministral-3B † | 0.030 | 0.089 | 0.103 | 0.000 | 0.000 | 0.044 | 0.048（9/186） |
| Qwen3-8B † | 0.091 | 0.000 | 0.000 | 0.077 | 0.000 | 0.034 | 0.032（6/186） |
| Gemma-3-4B †‡ | 0.000 | 0.022 | 0.000 | 0.000 | 0.133 | 0.031 | 0.027（5/186） |
| Llama-3.2-3B † | 0.000 | 0.000 | 0.000 | 0.000 | 0.133 | 0.027 | 0.022（4/186） |
| Qwen3.8-27B（上沿） | 0.576 | 0.978 | 0.923 | 0.846 | 0.967 | 0.858 | 0.866（161/186） |
| Qwen3.6-35B-A3B（上沿） | 0.364 | 0.644 | 0.923 | 0.462 | 0.767 | 0.632 | 0.634（118/186） |

**E2E（Atomic ∧ 干净 `finish`）**

| 模型 | Loc | Edit | Testgen | Repro | Review | 五项宏平均 | 题微平均 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen3.5-9B | 0.242 | 0.867 | 0.923 | 0.692 | 1.000 | **0.745** | 0.753（140/186） |
| Ministral-14B | 0.091 | 0.644 | 0.026 | 0.846 | 0.833 | 0.488 | 0.489（91/186） |
| Ministral-8B | 0.091 | 0.578 | 0.282 | 0.538 | 0.533 | 0.405 | 0.414（77/186） |
| Qwen3-14B | 0.091 | 0.467 | 0.462 | 0.410 | 0.233 | 0.333 | 0.349（65/186） |
| Granite-4.1-8B † | 0.000 | 0.178 | 0.077 | 0.077 | 0.200 | 0.106 | 0.108（20/186） |
| Gemma-3-12B † | 0.000 | 0.000 | 0.077 | 0.026 | 0.300 | 0.081 | 0.070（13/186） |
| Gemma-3-4B †‡ | 0.000 | 0.022 | 0.000 | 0.000 | 0.133 | 0.031 | 0.027（5/186） |
| Ministral-3B † | 0.000 | 0.044 | 0.051 | 0.000 | 0.000 | 0.019 | 0.022（4/186） |
| Qwen3-8B † | 0.091 | 0.000 | 0.000 | 0.000 | 0.000 | 0.018 | 0.016（3/186） |
| Llama-3.2-3B † | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000（0/186） |
| Qwen3.8-27B（上沿） | 0.485 | 0.978 | 0.923 | 0.846 | 0.967 | 0.840 | 0.849（158/186） |
| Qwen3.6-35B-A3B（上沿） | 0.364 | 0.644 | 0.923 | 0.103 | 0.767 | 0.560 | 0.559（104/186） |

† v1.0 冻结时 Hard-15 未跑，15 道 \(p=0\)。补测见 §12.4。‡ Gemma-4B 已评格子含 67 次被记成 `protocol_error` 的 429。side table 重跑后 Atomic/E2E 均为 8/186，仍是地板。正式锁不改。见 §14。

读法（细节 §11 / §12）：

- 排序：9B ≫ 两个 Ministral ≫ Qwen3-14B ≫ Gemma-12B。Qwen3-8B 仍贴地板，和同代 9B 不是一条带。
- Gemma-12B Edit Atomic 0.47、E2E Edit **0.00**——产物对了几乎从不干净停；v1.0 表 Hard-15 记 0。补测后 `edit-blank-name` 3/3 Atomic 仍全部 `protocol_error`，E2E Edit 还是 0。
- 3B / 4B / Qwen3-8B 已评格子里 `protocol_error` 占 77–96%。这是能力地板，不是 harness 坏了。
- 9B Hard-15 实测 Atomic 30/45，不是 0。正式 Hard 只锁 **9B 0/3 且 27B 3/3（Atomic）**。

### 6.3 已有、但不得写入上表的标定（Terminus-2）

仅作历史。9B rest 38/39；8B rest 28/39；8B loc 0/8；Granite 47 题 Harbor mean 0.40。详见 [`DIFFICULTY.md`](DIFFICULTY.md)。

## 7. 已经看到的负结果

- k=1 的 4 道 Hard 候选里，k=3 只锁住 **2** 道（§11）。`loc-similar-filenames`（9B 1/3）、`loc-failing-test-impl`（9B 2/3）不是 Hard。
- `loc-bind-host`、`loc-reexport` 尺子也 0/3 → **未标定**。`loc-traceback-helper` 是 9B 2/3、27B 0/3 → **Medium**。
- L9 精确集合：9B / 14B / 27B 都是 gold+decoy → 库存未标定，不在发表的 62 里，不改成 subset。
- `review-dollar-cents`：9B 过过、27B k=1 写过 1 → 不是 Hard。
- compact-shell 10 题烟测：9B 9/10；唯一 0 是 `repro-whitespace`（写出 repro 后又修了仓库）。协议 clean。这是任务理解，不是 JSON 税。k=3 上 9B 这道仍是 0/3，但 27B 未补 k=3，**还不能**锁 Hard。

## 8. 10-model k=1 正式判断（2026-08-24）

工程链路成功（490/490，infra=0，无 `timeout_loop`）。Core 是有效的 **E2E 探索矩阵**（model + compact-shell），不是纯代码能力。legacy `protocol_pass` 命名错误：它是 `preflight_both_pass`（两道烟测都做对且干净停），**不能**说 8 个模型协议不兼容。Qwen3.5-9B 标了 fail 却 37/47，只因 `collect-todos` 写对了没干净 `finish`。

同一批数据拆三张矩阵（`python scripts/relabel_locked.py` → `jobs/locked-matrices.json`，**不覆盖** `locked-core.json`）：Atomic / Termination / E2E。unfinished 记 0/1，不当缺失。主表报 E2E；Atomic-IRT 作能力分析；差值是「会做但不会停」。失败要拆：atomic / format / termination。7 道全 0 Loc 标 `uncalibrated_above_range`，不进普通 Rasch MLE；先看 precision/recall，不要先当 verifier bug 或「都不会定位」。

尺子 k=1 见 §10。正式 Core 表 k=3 见 §6.2 / §11；Hard-15 见 §12；27B/35B Base-47 k=3 见 §13。k=3 探索性 1PL 见 §9。tag **`benchmark-v1.0`** = 本 API Standard。Local Reference 的权重 SHA 在 [`models.local.yaml`](models.local.yaml)，全表未跑。

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

这是 k=1 探索拟合，不是正式量表。**不要**用这些 \(b\) 贴标签。k=3 二项重拟合见下。尺子进矩阵后的题角色以 §11 为准。

**k=3 探索性 1PL（Binomial(3)，不是多数通过；`python scripts/fit_irt.py --k3` → `jobs/irt-k3.json`）：**

主分析 = 10 compact × Base-47。每格 3 次 Bernoulli，不压成 2/3 算通过。Hard-15 不单独拟合。发表均值不是 IRT；只看序。

- Atomic：44 道进 MLE（全 0 的 3 道 Loc 出量表：`loc-member-discount`、`loc-vip-two-files`、`loc-reexport`）。10 个模型都有有限 θ。
- Atomic θ 序：Qwen3.5-9B (4.28) > Ministral-14B (1.92) > Ministral-8B (1.61) > Qwen3-14B (1.35) > Gemma-12B (0.62) > Granite (−0.49) > Ministral-3B (−1.82) > Qwen3-8B (−2.28) > Gemma-4B (−2.48) > Llama-3.2-3B (−2.72)。与 k=1 序一致。
- E2E：Llama 在校准题上全 0，无有限 θ。其余与 Atomic 的 θ Spearman **0.933**，b Spearman **0.923**。Gemma-12B 仍掉到 −1.09（停机损失）。
- Sensitivity：加入 27B/35B 后 9B 仍第一、27B 最高（5.05）；去掉 35B 后序不变。35B Atomic θ 2.03，介于 9B 与 Ministral-14B 之间——这是 **10+2 的相对位置**，不是 Compact Main 的官方 θ。
- 最易：`edit-hhmmss`、`review-slug-complete`。最难（仍在量表内）：`loc-bind-host`，然后三条只对极少数模型为 1 的 Loc。

答辩时用这句话：这是 3B–9B 的技能剖面仪，不是 SWE-bench 替代品，也不是「小模型已经能当完整交互式 coding agent」的证据。

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

那 4 道当时只是 **k=1 候选**。k=3 锁法与结果见 §11：只留下 `loc-member-discount` 与 `loc-vip-two-files`（后者 Atomic 3/3、E2E 0/3）。不要把 27B 塞进 \(\theta\)。

## 11. compact-shell k=3（正式主表，2026-08-25）

补跑，不是 Harbor `-k 3` 整表重来。main 940 格 + 尺子 Loc 14 格，与 attempt=1 池化。477 格全部 `n_valid=3`。中途 Gemma Review 撞过 DeepInfra 429（记 infra，不记 0）；UTF-8 坏 `result.json` 曾让 runner 崩过一次，修了 `classify_timeouts` / `RateLimitError` 之后续跑。终表 `infra_count` 合计 0。

**相对 k=1（同一 47 题，main）：**

| 模型 | k=1 A | k=3 A | k=1 E | k=3 E |
|---|---:|---:|---:|---:|
| Qwen3.5-9B | 0.787 | **0.823** | 0.745 | **0.780** |
| Ministral-14B | 0.532 | 0.546 | 0.532 | 0.532 |
| Ministral-8B | 0.468 | 0.496 | 0.447 | 0.440 |
| Qwen3-14B | 0.404 | 0.454 | 0.362 | 0.404 |
| Gemma-3-12B | 0.319 | 0.333 | 0.106 | 0.092 |
| Granite-4.1-8B | 0.213 | 0.177 | 0.170 | 0.142 |
| Ministral-3B | 0.064 | 0.064 | 0.000 | 0.028 |
| Gemma-3-4B | 0.064 | 0.035 | 0.064 | 0.035 |
| Qwen3-8B | 0.043 | 0.043 | 0.021 | 0.021 |
| Llama-3.2-3B | 0.021 | 0.028 | 0.000 | 0.000 |

k=1 一次成功会虚高（Gemma-4B、Granite），三次平均把地板压实。9B / 14B 略升，是 k=1 漏掉的真阳性，不是换题。技能列见 §6.2。

**停机（141 次/模型）：** Ministral-14B clean 0.94，9B 0.89，Ministral-8B 0.84，Qwen3-14B 0.73。Gemma-12B clean 0.45 而 Atomic 仍 0.33——停机损失。Llama / Ministral-3B / Qwen3-8B 的 `protocol_error` 为 0.96 / 0.91 / 0.82。

**Loc 题级（Hard = 9B 0/3 且 27B Atomic 3/3；不是「10 main 全 0」）：**

| 题 | 9B | 27B A | 27B E | 10-main \(\bar p\) | 档 |
|---|---:|---:|---:|---:|---|
| loc-member-discount | **0/3** | **3/3** | 3/3 | 0.000 | **Hard** |
| loc-vip-two-files | **0/3** | **3/3** | **0/3** | 0.000 | **Hard（Atomic）**；E2E 未锁（尺子三次都写对没停） |
| loc-similar-filenames | 1/3 | 3/3 | 3/3 | 0.067 | 不是 Hard（9B 不稳 0） |
| loc-failing-test-impl | 2/3 | 3/3 | 3/3 | 0.067 | Medium（k=1 的 0 是噪声） |
| loc-traceback-helper | 2/3 | 0/3 | 0/3 | 0.067 | **Medium**；9B 能过 |
| loc-bind-host | 0/3 | 0/3 | 0/3 | 0.033 | **未标定**（尺子过报 decoy） |
| loc-reexport | 0/3 | 0/3 | 0/3 | 0.000 | **未标定** |
| loc-unused-fix | 3/3 | **3/3** | 3/3 | 0.533 | 易题 / smoke（k=3 来自 §13，不在 `locked-core-k3.json`） |

两道 Loc Hard **仍留在冻结的 47 里出分**（10 个 main 全是 0，不改变 main 内部名次），另表叫 Frontier。不事后抽成 45 题来抬 9B。Terminus-2 上 9B 过 `loc-vip-two-files` 3/3——那是另一套 harness，**不能**用来否掉 compact-shell 的 Hard。

**9B 另外三道 k=3 仍 0/3，27B Base-47 k=3（§13）现为 Atomic 3/3，故锁 Hard（Atomic）：** `testgen-anagram`、`repro-first-index`、`repro-whitespace`。27B 这三道的 k=3 只在 `jobs/locked-upper-base-k3.json`，不在 `locked-core-k3.json`。Hard-Release-15 **不改**。Edit / Review 9B 均为 \(p=1.00\)。

**Frontier 在 Core 47 里现有 5 道**（2 Loc + `testgen-anagram` + 2 Repro）。Hard-Release-15 的梯子归类见 §12。探索性 1PL 的 k=3 二项拟合见 §9（`jobs/irt-k3.json`）。Local Reference 全表未跑（pins：`models.local.yaml`）。

## 12. Hard-Release-15（compact-shell k=3，API，2026-08-26）

官方 Hard 题集 15 道（Gate-B：oracle=1、nop=0、≥2 foils；见 [`HARD-RELEASE.md`](HARD-RELEASE.md)）。Hard-Dev-10 是废纸，不进 mean。题已冻：**不按本表改 instruction / verifier。**

受试不是 12 个 Core 全跑。Base-47 Atomic 47 均低于 0.40 的地板 / Medium 挣扎模型不是官方 Hard 受试。跑的 6 个：Ministral-8B、Qwen3.5-9B、Qwen3-14B、Ministral-14B、Qwen3.8-27B、Qwen3.6-35B-A3B。官方锁不写另外 6 个。v1.0 发表 62 均值把那 15 道记 0（标 †）。后来的完整性补测见 §12.4，不进本锁。

跑法：`python scripts/run_locked.py --run --hard-release`。三次独立 Harbor `-k 1`，不是 `harbor run -k 3`。产物 **`jobs/locked-hard-release-k3.json`**（不覆盖 Base lock / Hard-Dev）。90 格全部 `n_valid=3`，infra=0。270 次：clean 209、`protocol_error` 60、TLE 1。线路仍是钉死的 OpenRouter provider（9B Parasail BF16、27B Akash BF16、35B Venice FP8）。Local Reference 未做。

格子是 \(p_i=\#\{atomic=1\}/3\)。技能列是该原子 3 道 \(p\) 的均分。Hard-15 每原子正好 3 道，所以 **五项宏平均 = 题微平均（15 均）**。**主表不扣 protocol、不给未交卷补分。**

**Atomic**

| 模型 | Loc | Edit | Testgen | Repro | Review | 五项宏平均 | 15 均 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen3.8-27B | 0.444 | 0.889 | 0.667 | 0.556 | 0.889 | 0.689 | **0.689**（31/45） |
| Qwen3.5-9B | 0.000 | 0.667 | 1.000 | 0.667 | 1.000 | 0.667 | **0.667**（30/45） |
| Qwen3.6-35B-A3B | 0.667 | 0.000 | 0.667 | 0.333 | 0.667 | 0.467 | 0.467（21/45） |
| Ministral-8B | 0.000 | 0.333 | 0.222 | 0.667 | 0.556 | 0.356 | 0.356（16/45） |
| Ministral-14B | 0.000 | 0.333 | 0.000 | 0.667 | 0.778 | 0.356 | 0.356（16/45） |
| Qwen3-14B | 0.000 | 0.111 | 0.222 | 0.111 | 0.889 | 0.267 | 0.267（12/45） |

**E2E（Atomic ∧ 干净 `finish`）**

| 模型 | Loc | Edit | Testgen | Repro | Review | 五项宏平均 | 15 均 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen3.8-27B | 0.444 | 0.889 | 0.667 | 0.556 | 0.889 | 0.689 | **0.689**（31/45） |
| Qwen3.5-9B | 0.000 | 0.667 | 1.000 | 0.667 | 1.000 | 0.667 | **0.667**（30/45） |
| Qwen3.6-35B-A3B | 0.667 | 0.000 | 0.667 | 0.000 | 0.667 | 0.400 | 0.400（18/45） |
| Ministral-14B | 0.000 | 0.333 | 0.000 | 0.667 | 0.778 | 0.356 | 0.356（16/45） |
| Ministral-8B | 0.000 | 0.222 | 0.222 | 0.667 | 0.556 | 0.333 | 0.333（15/45） |
| Qwen3-14B | 0.000 | 0.111 | 0.222 | 0.111 | 0.444 | 0.178 | 0.178（8/45） |

35B Atomic 21/45、E2E 18/45：差的 3 次全是 `repro-nested-alias`（产物对，20 轮没 `finish`）。27B 与 9B 只差 1/45，**不排明确高低**。35B-A3B 是 ~3B 激活 MoE，不是 27B dense 的下一档，禁止当参数定律。

### 12.1 题级梯子（Hard = 9B 0/3 且 27B Atomic 3/3）

| 题 | 9B | 27B A | 35B A | 档 |
|---|---:|---:|---:|---|
| `loc-hook-plugin` | **0/3** | **3/3** | 0/3 | **Hard** |
| `loc-vendor-shadow` | 0/3 | 1/3 | 3/3 | **未标定**（27B 不稳） |
| `loc-env-wrapper` | 0/3 | 0/3 | 3/3 | **未标定**（尺子三次不交卷） |
| `edit-config-beside` | 0/3 | 2/3 | 0/3 | **未标定**（27B 不稳 3/3） |
| `repro-nested-alias` | 0/3 | 2/3 | 3/3 A · 0/3 E | **未标定** |
| 其余 10 道 | 9B 均为 3/3 | — | — | **不是 Hard**（目标档会过） |

Core 47 里的 Frontier（`loc-member-discount`、`loc-vip-two-files`，以及 §13 新锁的 `testgen-anagram` / `repro-first-index` / `repro-whitespace`）仍有效。Hard-15 **没有**把 Edit / Testgen / Repro / Review 推到 Frontier；9B 在 Testgen / Review 上仍是 1.00（Hard-15 那 3 道 Testgen / Review）。这是题带与梯子不一致，不是 270 格记分记反。不改题。

### 12.2 失败构成（六模型同一套 lock 标签）

正交分类来自 `jobs/locked-hard-release-k3.json` 的 `atomic_correct` × `termination`（`python scripts/fail_compose.py` → `jobs/locked-hard-failure.json`）。**不以轨迹备注替代这张表。** missing 受试不当 0。

270 次：`task_pass_clean` 118，`task_pass_unfinished` 8，`task_fail_clean` 91，`task_fail_unfinished` 53，infra 0。与 termination 合计一致（clean 209 = 118+91；非 clean 61 = 8+53）。

| 模型 | Atomic 过 | E2E 过 | pass+未停 | 干净失败 | 未停且失败 | E2E 总失败 |
|---|---:|---:|---:|---:|---:|---:|
| Qwen3.8-27B | 31 | 31 | 0 | 5 | 9 | 14 |
| Qwen3.5-9B | 30 | 30 | 0 | 6 | 9 | 15 |
| Qwen3.6-35B-A3B | 21 | 18 | **3** | 12 | 12 | **27** |
| Ministral-8B | 16 | 15 | 1 | 19 | 10 | 30 |
| Ministral-14B | 16 | 16 | 0 | 28 | 1 | 29 |
| Qwen3-14B | 12 | 8 | 4 | 21 | 12 | 37 |

35B：24 次 Atomic 失败 + 3 次写对没停 = 27 次 E2E 失败。不要读成「除了 3 次没停只剩 12 次失败」。把未停且失败全部当成若提交则全对，上限是 \((21+12)/45=0.73\)。**这不是修正分。**

轨迹备注（不改 lock 计数）：35B 的 3 次 `task_pass_unfinished` 全是 `repro-nested-alias`。未停且失败里包括空转/不交卷（`edit-retry-discount`、`edit-blank-name`、`loc-hook-plugin`、部分 Review）以及 Repro 合同写反。干净失败包括 `edit-config-beside`（旁路径）和 `testgen-tie-order`（导入写错）——这两类不要并成一个「clean verifier=6」。27B 的 14 次失败里交互/格式/不交卷仍是多数；9B 的 9 次未停全是三条 Loc 不交卷，6 次干净失败是 `edit-config-beside` 与 `repro-nested-alias`。

### 12.3 怎么读 35B 低于 9B

§1 的测量对象在这里落地。协议规则相同，没有记分错误。测量仍是混合的（任务理解、行动、产物、提交/终止、provider/量化）。

- **当作端到端 agent：** 在 compact-shell + Novita + 钉死 OpenRouter 线路 + k=3 下，35B-A3B（Venice FP8）的端到端可靠性低于 9B。读了 20 轮但不改、不交卷，在 Agent 场景里仍是失败。
- **当作固有代码能力：** **不能** 证明 Qwen 35B 推理弱于 Qwen 9B。不能从本表推出参数定律。
- **不要** 从 Atomic mean 剔除 protocol failure 来「修正」35B；halt-ceiling 0.73 不是正式分。

v1.0 不改回合数、parser、finish、Repro 合同或 Atomic 规则。宽松协议或 Local vLLM 只做后续 sensitivity。v1.0 正式发表的是本 API 系统表；Local Reference 以后补，不覆盖本表。

### 12.4 Hard-floor 补全（6 个缺测 compact × Hard-15，2026-08-27）

完整性，不是新的官方 Hard 受试。命令：`python scripts/run_locked.py --run --hard-floor`。产物 **`jobs/locked-hard-floor-k3.json`**。**没有覆盖** `locked-hard-release-k3.json`。90 格 `n_valid=3`，incomplete 0。270 次：`protocol_error` 189、clean 80、TLE 1。不按本表改题。对外表见 [`结果报表.md`](结果报表.md) §2.4。

**Atomic**

| 模型 | Loc | Edit | Testgen | Repro | Review | 五项宏平均 | 15 均 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Gemma-3-12B | 0.000 | 0.333 | 0.000 | 0.556 | 0.556 | 0.289 | 0.289（13/45） |
| Granite-4.1-8B | 0.000 | 0.333 | 0.000 | 0.000 | 0.333 | 0.133 | 0.133（6/45） |
| Gemma-3-4B | 0.000 | 0.000 | 0.000 | 0.000 | 0.333 | 0.067 | 0.067（3/45） |
| Ministral-3B | 0.000 | 0.111 | 0.000 | 0.000 | 0.000 | 0.022 | 0.022（1/45） |
| Qwen3-8B | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000（0/45） |
| Llama-3.2-3B | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000（0/45） |

**E2E**

| 模型 | Loc | Edit | Testgen | Repro | Review | 五项宏平均 | 15 均 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Granite-4.1-8B | 0.000 | 0.333 | 0.000 | 0.000 | 0.333 | 0.133 | 0.133（6/45） |
| Gemma-3-12B | 0.000 | 0.000 | 0.000 | 0.000 | 0.556 | 0.111 | 0.111（5/45） |
| Gemma-3-4B | 0.000 | 0.000 | 0.000 | 0.000 | 0.333 | 0.067 | 0.067（3/45） |
| Ministral-3B | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000（0/45） |
| Qwen3-8B | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000（0/45） |
| Llama-3.2-3B | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000（0/45） |

合计 Atomic 23/270、E2E 14/270。Gemma-12B Hard Edit / Repro 的 Atomic 成功几乎全是 `protocol_error`（没 `finish`）。冻结 Base-47 + 本文件并成 62 后，Gemma-12B Atomic 0.313（60/186）、Granite 0.162（31/186）。compact-10 前六名不变。Headline 9B / 27B 不动。

## 13. 27B / 35B Base-47 k=3（部署档，不进 compact-10 均值，2026-08-26）

跑法：`python scripts/run_locked.py --run --base-fill`。27B 先从 `locked-core-k3.json` 种子已有格（47 题 a1 + 7 道 Loc a2/a3），再补其余；35B 从零 141 格。产物 **`jobs/locked-upper-base-k3.json`**（`kind=locked_upper_base_k3`，`enters_official_mean=false`）。**没有覆盖** `locked-core.json` / `locked-core-k3.json`。94 格全部 `n_valid=3`，infra=0，TLE=0。282 次：27B clean 131 / `protocol_error` 10；35B clean 97 / `protocol_error` 44。

发表均值用 §6.2 的 62 道（v1.0 缺测记 0；地板 Hard-15 补全见 §12.4）。本跑是 Base-47 补齐；下表已并进官方 Hard-15。9B 行来自 `locked-core-k3.json` + `locked-hard-release-k3.json`。35B-A3B 仍是 ~3B 激活 MoE。不按本表改 Hard-15，不给 35B 加分，不从 Atomic 剔除 protocol。

**Atomic**

| 模型 | Loc | Edit | Testgen | Repro | Review | 五项宏平均 | 题微平均 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen3.8-27B | 0.576 | 0.978 | 0.923 | 0.846 | 0.967 | **0.858** | 0.866（161/186） |
| Qwen3.5-9B | 0.242 | 0.933 | 0.923 | 0.769 | 1.000 | 0.774 | 0.785（146/186） |
| Qwen3.6-35B-A3B | 0.364 | 0.644 | 0.923 | 0.462 | 0.767 | 0.632 | 0.634（118/186） |

**E2E（Atomic ∧ 干净 `finish`）**

| 模型 | Loc | Edit | Testgen | Repro | Review | 五项宏平均 | 题微平均 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen3.8-27B | 0.485 | 0.978 | 0.923 | 0.846 | 0.967 | **0.840** | 0.849（158/186） |
| Qwen3.5-9B | 0.242 | 0.867 | 0.923 | 0.692 | 1.000 | 0.745 | 0.753（140/186） |
| Qwen3.6-35B-A3B | 0.364 | 0.644 | 0.923 | 0.103 | 0.767 | 0.560 | 0.559（104/186） |

读法：

- 27B 在 62 道上明显高于 9B（Atomic 161/186 vs 146/186）。Hard-15 上 27B 31/45、9B 30/45。Atomic−E2E 差里含 `loc-vip-two-files`（产物对、没 `finish`）。
- 35B Testgen 天花板。拖均值的是 Loc 和 Repro。Base Loc 另外 6 道是 **Atomic 0 + `protocol_error`**（没交卷），不是 Hard-15 `repro-nested-alias` 那种产物对但没停。
- 35B Atomic 118/186、E2E 104/186：Base Repro 里有 11 次产物对没停，Hard-15 `repro-nested-alias` 另有 3 次。不要从 Atomic 里抠这些。
- 35B Edit 非满分：`edit-deep-merge` 0/3；`edit-timeout-zero`、`edit-pad-left` 各 1/3；Hard-15 Edit 0/9。Review 非满分：`review-clip-incomplete` 0/3；`review-slug-almost` 2/3。

**梯子（Hard = 9B 0/3 且 27B Atomic 3/3；27B 非 Loc 的 k=3 以本 JSON 为准）：**

| 题 | 9B | 27B A | 27B E | 35B A | 档 |
|---|---:|---:|---:|---:|---|
| `loc-member-discount` | 0/3 | 3/3 | 3/3 | 3/3 | **Hard**（已在 §11） |
| `loc-vip-two-files` | 0/3 | 3/3 | 0/3 | 0/3 | **Hard（Atomic）**（已在 §11） |
| `testgen-anagram` | 0/3 | 3/3 | 3/3 | 3/3 | **Hard**（本表新锁） |
| `repro-first-index` | 0/3 | 3/3 | 3/3 | 0/3 | **Hard**（本表新锁） |
| `repro-whitespace` | 0/3 | 3/3 | 3/3 | 0/3 | **Hard**（本表新锁） |
| `repro-zero-timeout` | 0/3 | 1/3 | 1/3 | 2/3 | 不是 Hard（27B 不稳） |

Hard-Release-15 题集与分数不改。k=3 探索性 1PL 见 §9。Local Reference 全表未跑。

## 14. 两张发表表、`finish`、以及「没停 ≠ 不会做」

v1.0 对外两张表（同一冻结试验，不要混）：

| 表 | 问题 | `finish` |
|---|---|---|
| **Atomic** | 隐藏评分器看产物过没过 | **不要求。** 写对了但没停仍记 1 |
| **E2E** | Atomic=1 **且** `termination=clean` | **要求。** 这是停机合规，不是「原子技能的端到端」 |

第三张表（Aider / 用户口中的 Adam）是 **微调之后的迁移实验**，不是现在这张 E2E。Core 47 / Hard-15 / Aider 34 都不进训练集。

### 没停的时候模型在干什么

对 Core k=3 + upper-base + Hard-15 里 **Atomic=1 且非 clean** 的 99 次轨迹逐条看最后一轮（不是只看 `termination` 标签）：

| 最后行为 | n | 典型 |
|---|---:|---|
| 20 轮上限仍在行动 | 44 | 继续写文件 / grep |
| pytest 验证环 | 33 | 几乎全是 Gemma-12B Edit |
| 反复改写直到上限 | 19 | 35B Repro、Granite |
| 非协议终止表达（shell 里喊完成） | 2 | 9B `echo "Task complete."` |
| 未归入上表 | 1 | 归类缺口；合计仍是 99 |

**0** 次是「已经打出空的 ` ```finish `、评分器漏解析」。49/99 在撞上限至少 5 轮之前就已经写出正确产物。所以 E2E 掉分主要是 **不会按契约停**，不是「不会做这道题」。

### 教学弱在哪（不是「整个 system prompt 被忽略」）

`finish` **只**写在 `agents/protocol.py` 的 `SYSTEM_PROMPT`（塞进第一轮 user 的那坨）。任务 `instruction.md` 只写「You have 180/240 seconds」「You may run pytest」——**从不提 finish**。第二轮起模型只看见 `exit 0` + stdout。解析器是严格围栏：

```
FINISH_FENCE = r"```finish\s*```"
```

围栏**里面**写 `finish`（如 Qwen3-14B 的 `finish\n0`）不算。同一段 prompt 也教了 bash；bash **每轮都在用**。被丢掉的是「做完之后发一次空围栏」这一条——只出现一次、容易被非协议终止表达替代（`echo done`、`cat` 再确认、再改一版）。

不要把这写成「模型无视了整个 system prompt」。要写成：**弱教学 + 非协议终止表达 + 严格围栏**。

Atomic 已过、其中又干净 finish 的比例（v1.0 冻结 Core 62；† 的 Hard-15 成功数为 0，不进分子）：

| 模型 | Atomic 成功里干净停 |
|---|---|
| Ministral-14B | 91/93（98%） |
| **Qwen3.5-9B** | **140/146（96%）** |
| Qwen3-14B | 65/76（86%） |
| Ministral-8B | 77/86（90%） |
| Granite-8B † | 20/25（80%） |
| **Gemma-12B †** | **13/47（28%）** — 这是停机税，不是 Edit 不会 |
| Llama-3.2-3B † | 0/4 |

9B 不是「不会 finish」。Gemma-12B 才是。Hard-floor 补测后 Gemma-12B 是 18/60（30%），停机税还在。27B 在 `loc-vip-two-files` 上 Atomic 3/3、E2E 0/3：三次都是产物对了还 `cat` 到 20 轮。

### 设计判断（v1.0 不改）

**不要**为了把 E2E 刷好看，把「请 `finish`」写进每道 `instruction.md`。现在的 Atomic / E2E 分裂就是要测的东西。把 finish 写进题面是 **v1.1 / sensitivity**，新实验，不覆盖冻结分。Headline 是五项 Atomic 宏平均；E2E 是干净完成率。

Grok 4.6 探针（**非正式**，k=1，`openrouter/x-ai/grok-4.6`，`tasks/loc-vip-two-files`，job `jobs/2026-08-26__18-05-30`）：Atomic=1，`termination=clean`，7 轮（探目录 → 写 `checkout.py` + `pricing/vip.py` → `cat` 一次 → `finish`）。对照 27B 同题 Atomic 3/3 E2E 0/3。说明「做完就停」对强模型不是难动作；27B 在这道题上的 E2E 0 是 **这套薄 agent + 弱教学** 下的停机失败。

### 计分器旁注（不改 v1.0 分）

Harbor 抛的是 **`RateLimitError`**；v1.0 `RETRY_INCLUDE` 当时只有 `RateLimitException`。Gemma-3-4B Core 有 **67/141** 格锁成 `protocol_error`，trial `result.json` 实际是 429。现 `scripts/score_standard.py` 已认 `RateLimitError` 为 infra。这 67 格已重跑到 side table `jobs/locked-gemma4b-rerun-k3.json`（2026-08-26，67/67），**不覆盖** `locked-core-k3.json`。并进 v1.0.1 canonical matrix 后 Gemma-4B 是 **11/186**（Base 重跑 8/141 + Hard-15 的 3 次）。冻结审计仍是 5/186。仍是低表现端；429 没有藏着一个会做题的 4B。另外 13 格 infra 已替换，见 §15。

另外会漏进 `protocol_error`、也不该当任务 0 的：`OutputLengthExceededError`（`max_tokens=4096` 直接掐死 episode；Llama / Qwen3-14B Core 各 18 次）。这仍按协议/模型计分，不按 infra 重跑。

## 15. infra 13 格勘误（2026-08-27）

命令：`python scripts/rerun_infra.py --run`。产物 **`jobs/locked-infra-rerun-k3.json`**（13/13，**不覆盖**冻结锁）。v1.0.1 canonical matrix 第六层。`remaining_dirty` 0。

| 配置 | n | 原异常 | 替换后 |
|---|---:|---|---|
| Llama-3.2-3B | 4 | RateLimitError | 全部 Artifact=0，`protocol_error` |
| Qwen3.5-9B | 4 | RateLimitError | 2× Artifact=1 clean（`loc-failing-test-impl`、`loc-traceback-helper`）；2× Artifact=0（`loc-similar-filenames`、`loc-vip-two-files`） |
| Qwen3-8B | 2 | ConnectError | 全部 Artifact=0，`protocol_error` |
| Qwen3.8-27B | 2 | ServiceUnavailableError | `repro-nested-alias` a3 Artifact=1 clean；`repro-stale-quote` a1 Artifact=0 |
| Ministral-8B | 1 | AuthenticationError | `review-rotate-right` a3 Artifact=1 clean |

当前阅读表：9B Artifact **0.786**（148/186），Clean 0.757（142/186）；27B Artifact **0.863**（162/186）。halt 仍是 105。Hard-15：9B 30/45，27B 32/45。难度从 canonical 全表重算：Easy 12 / Medium 38 / Hard 7 / Uncalibrated 5。`repro-nested-alias` 升为 Hard。脱敏 trials：`results/v1.0.1_trials.jsonl`。本表对应 tag `benchmark-v1.0.1`。§6.2 / §13 冻结表不改写。Infra replacement 在后续时间窗口完成；路由与采样冻结，API 后端时间漂移无法完全排除。
