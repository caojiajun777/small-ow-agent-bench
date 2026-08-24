# 外部先验 → 出题（不是盲跑）

五项原子不变。已有 47 道能留则留，不能留就弃，不怕重出。先建先验，再决定去留，再按模型补题。

oracle/nop 只证明「题能跑」。证明「题好」靠：在 **已有 agentic coding 题库的题目级作答** 上拟合 IRT，精炼出对目标 \(\theta\) 有信息的题，再决定我们 47 道去留。

## 0. 正确的先验：题，不是模型卡总分

IRT 的对象是 **题目** \(j\) 的 \(a_j,b_j\)，数据必须是「谁在哪一题上 0/1」。模型卡上的 LCB 65.6 / SWE 19.2 只有一个平均数，**不能**拿来拟合题目 IRT（上一轮 `prior-theta-z.json` 只是人群序，已经降级为附录）。

已有公开矩阵（[Agent Psychometrics, arXiv 2604.00594](https://arxiv.org/abs/2604.00594)）：

| 题集 | 题 × agent | 1PL 有信息（0.2<p<0.8） | Easy 尾（p>0.8） | 零信息 |
|---|---|---:|---:|---:|
| SWE-bench Verified | 500 × 134 | 263 | 119 | 52 |
| Terminal-Bench 2.0 | 89 × 112 | 53 | 10 | 8 |
| SWE-bench Pro | 730 × 14 | 343 | 24 | 251 |

跑：`python scripts/distill_bench_irt.py` → [`prior-irt/distilled.json`](prior-irt/distilled.json)。

这些 \(b\) 是按 **前沿 agent** 标定的（abilities 里是 Opus / GPT-5 / OpenHands，没有 3B–9B）。所以：

- 原题原样给小模型 → 几乎全 0 → 没有斜率，估不出 \(a,b\)
- **精炼** = 只留 Easy / informative 尾的考点，改写成五项原子短题  
  TB Easy 尾例子：`modernize-scientific-stack`、`fix-git`、`git-leak-recovery`（\(b\approx -5\)～\(-3.5\)）  
  丢掉：`make-doom-for-mips`、`install-windows-3.11`
- SWE Easy 尾仍是复合修 issue（`django__*`、`scikit-learn__*`），对 3B–9B 仍然太整。拆成 Loc / Edit / Repro 才有信息量——这就是五项原子的来由，不是另起一套感觉题

## 1. 外部先验（已发布 agent 编程题 + 分数）

不同 harness 的分数 **不能直接当 \(b\)**。同一 9B，Aider 19%、小模型适配 scaffold 46%。模型卡总分只作附录人群序。题目难度以 §0 的 1PL 为准。

### 1.1 模型能力 \(\theta\) 先验（人群，不限于我们要跑的模型）

\(\theta\) 是「小模型 agentic coding」这整个人群上的能力序，不是「Qwen3.5-9B 和 Ministral-8B 两个点」。机读表见 [`prior-population.json`](prior-population.json)。同一篇 Seed-Coder 论文（[arXiv 2506.03524](https://arxiv.org/html/2506.03524v2)）给出目前最整齐的 7B–14B 切片（LCB 2410–2502、Aider whole tries=2、SWE-Verified Agentless / OpenHands）。

| 类 | 代表（含未列入我们评测名单的） | 公开信号 | \(\theta\) 先验 |
|---|---|---|---|
| 地板 vanilla | Gemma-3-4B-IT、Llama-3.2-3B、CodeLlama-7B | Gemma-3-4B LCB **12.6**；CodeLlama Aider **1.5** / LCB **3.6** | 低 |
| 地板–中 | Qwen3-4B-Instruct-2507、Llama-3.1-8B、OpenCoder-8B | Qwen3-4B LCB v6 **35.1**；Llama-3.1-8B SWE-A **1.0** / Aider **33.1** | 低–中 |
| 中（竞赛/编辑） | Qwen2.5-Coder-7B、Yi-Coder-9B、Qwen3-8B | Coder-7B Aider **57.9** 但 SWE-A 只有 **4.2**；Qwen3-8B LCB **23.5** / SWE-A **14.6** | 中（编辑≠修 issue） |
| 中高（同尺寸里最像 agent） | Seed-Coder-8B-Instruct | 同窗 LCB **24.7** / Aider **57.1** / SWE-A **19.2** / OpenHands **11.2** | 中高（8B 里最高） |
| 目标档 | Qwen3.5-9B | 官方 LCB v6 **65.6**（更新窗，不能和 2410–2502 直接减） | 中高 |
| agent-SFT（另一维） | SWE-Gym-7B、SWE-Hero-7B/14B、Devstral-Small-24B | Hero-7B OpenHands **52.7**；Devstral-2507 **53.6** | **不要和 vanilla 挤进同一条 \(\theta\)** |
| 尺子 | Qwen3.5-27B、GLM-4.5-Air | 27B SWE-V **72.4**；Air Edit SFT **0.46** | 高；锚定用 |

要点：人群里 **编辑能力（Aider）和修 issue（SWE）已经不是同一维**——Coder-7B 编辑接近 Seed-Coder，SWE 却只有 4%。我们的五项必须拆开拟合，不能拿一个总分当 \(\theta\)。SWE-Hero / Devstral 是轨迹微调过的，IRT 里要当协变量。

### 1.2 构造难度 \(b\) 先验（按五项）

来自 Ma & Liu（精确集合 loc、hidden 测 edit、gold+mutant testgen、双状态 repro、0/1 review）、Loc-Bench、SWT-Bench、2026 本地 agent 失败分析（定位往往不是主因；策略上「修完再停」常见）。

| 原子 | 偏易（\(b\) 低） | 偏难（\(b\) 高） | 3B–9B 信息量 |
|---|---|---|---|
| Loc | 单文件、无 decoy | 精确集合 + 共享字符串 / traceback / 再导出 | **高**（8B vs 9B 已拉开） |
| Edit | 点名函数、说明写清 | 跨文件、说明含糊 | **低**（9B/8B 都饱和；当 Easy 带） |
| Testgen | 测一个显式例子 | 闰年、mutant 要全杀 | **高** |
| Repro | 明显 off-by-one | 只复现不改仓；空白 / `or 0` | **中高**（instruction 必须禁止改仓） |
| Review | 补丁明显错或明显对 | 例子过、契约不过 | **中** |

Ma & Liu 在 **更大** 模型上：Edit 0.46、Testgen 0.36（SFT）。他们的 edit 是真仓库改动，比我们「点名小函数」难一档。所以我们的 Edit 先验应标 **Easy**，不能当 Medium 主区分。

### 1.3 公开分数表（带出处）

**警告：harness ≠ ability。** 同一套权重可以因 scaffold / thinking / pass@k / 题集窗口差十几到几十个百分点。下表只用来排 \(\theta\) 和构造难度，**不是**我们题的 \(b\)。完整行与 null 检索记录见 `prior-scores.json`。

| 模型 | 档 | LiveCodeBench | SWE-bench | Aider Polyglot | 原子 / Loc / SWT | 出处 |
|---|---|---|---|---|---|---|
| Qwen2.5-3B-Instruct | 地板 | 19.9（2305–2409）；v5 **9.2** | 未找到官方 resolved | 未找到 | HE 74.4 / MBPP 72.7（脚注） | [Qwen2.5 blog](https://qwenlm.github.io/blog/qwen2.5-llm/)；v5 见 [Qwen3 报告 T20](https://arxiv.org/html/2505.09388) |
| Ministral-3B-Reasoning | 地板 | v6 **54.8 pass@5**（不是 pass@1） | 未找到 | 未找到 | Base MBPP 63.0 | [Ministral 3 论文 T5](https://arxiv.org/pdf/2601.08584) |
| Qwen3-4B | 地板 | Instruct-2507 v6 **35.1**；Thinking v5 **54.2**；non-think v5 21.3 | 未找到 | 官方卡 **12.9** | 官方卡无 E/M/H | [Qwen3-4B-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507)；[Qwen3 报告 T17](https://arxiv.org/html/2505.09388) |
| Qwen3.5-4B | 低–中 | v6 **55.8** | 未找到 | 未找到 | — | 同 [Qwen3.5-9B 卡](https://huggingface.co/Qwen/Qwen3.5-9B) 对照列 |
| Qwen2.5-7B-Instruct | 中 | 28.7（旧窗）；v5 14.4 | Coder-7B MOpenHands **1.0** | 未找到 | LocAgent 原 7B「很差」、无数字；Coder-7B SWT-V **1.15** | [Qwen2.5 blog](https://qwenlm.github.io/blog/qwen2.5-llm/)；[SWE-Lego T6](https://arxiv.org/html/2601.01426v2)；[SWE-Tester](https://arxiv.org/html/2601.13713v1) |
| Qwen3-8B | 中 | Thinking v5 **57.5**；non-think 22.8 | OpenHands 未 SFT **7.6** | 官方 aider.chat 无 8B 行 | Loc-Bench 无 vanilla 行 | [Qwen3 报告 T17/T18](https://arxiv.org/html/2505.09388)；[SWE-Lego](https://arxiv.org/html/2601.01426v2) |
| Ministral-8B-Reasoning | 中 | v6 **61.6 pass@5** | 未找到 | 未找到 | Base MBPP 70.0 | [Ministral 3 T5](https://arxiv.org/pdf/2601.08584) |
| Qwen3.5-9B | 中高 | v6 **65.6** | **官方卡无 SWE** | vanilla Aider **19.11** vs little-coder **45.56**（Q4，第三方） | 无官方 Loc/SWT | [Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B)；[little-coder](https://github.com/itayinbarr/little-coder) |
| Qwen3.5-27B（尺子） | 高 | v6 **80.7** | Verified **72.4** | 官方 aider 无 27B 行 | TB2 41.6 | [Qwen3.5-27B](https://huggingface.co/Qwen/Qwen3.5-27B) |
| Qwen3.6-27B（尺子） | 高 | v6 **83.9** | Verified **77.2**；Multi **71.3** | 官方 aider 无行 | TB2 59.3 | [Qwen3.6-27B](https://huggingface.co/Qwen/Qwen3.6-27B) |
| GLM-4.5-Air 12B 激活（尺子） | 高 | 2407–2501 **70.7** | Verified **57.6**（OpenHands） | 未查到官方 Aider | Ma & Liu SFT Edit **0.458** / Testgen **0.359**；joint RL Edit **0.611** | [z.ai/glm-4.5](https://z.ai/blog/glm-4.5)；[arXiv 2604.05013](https://huggingface.co/papers/2604.05013) |

Loc-Bench 仅有 **LocAgent 微调后的** Qwen2.5-7B(ft)：SWE-Lite file Acc@1 **70.8**，Loc-Bench file Acc@5 **79.2**（[LocAgent](https://arxiv.org/html/2503.09089v1)）。这不是 vanilla 7B 的 \(\theta\)。

LCB Easy/Medium/Hard：各官方卡几乎都不拆。唯一接近的独立表是 arXiv 2603.07777 对 Qwen3-4B-Instruct：Easy 87.8 / Med 31.7 / Hard 8.1（8K，All 34.7）。**不能**外推到 9B。

### 1.4 公开总分不能做题目 IRT

一个模型在 LCB / SWE / Aider 上只有一个平均数，不是 47 道题的 0/1。把这些平均数丢进 Rasch，估出来的是「题集有多硬」，不是 `loc-bind-host` 的 \(b\)。

现在能做的：

1. **人群 \(\theta\) 序**（已做）：`python scripts/fit_irt.py --from-population` → `jobs/prior-theta-z.json`。只用 Seed-Coder 同窗切片的 z 均值。当前序：Seed-Coder-8B (1.23) ≈ Qwen2.5-Coder-14B (1.23) > Qwen3-8B (0.95) > Qwen2.5-Coder-7B (0.24) > Yi-Coder-9B ≈ 0 > Llama-3.1-8B (−0.66) > CodeLlama-7B (−1.99)。这是公开总分的标准化，**还不是**我们题的 \(\theta\)。
2. **我们题上的 1PL/2PL**：`python scripts/relabel_locked.py` 拆 Atomic / E2E；`python scripts/fit_irt.py --score both` 写 `jobs/irt-draft.json`（k=1 探索；7 道全 0 Loc 与 E2E 全 0 的人排除 MLE）。要 **IRT-main 里 ≥8 个已评分模型**。unfinished 不当缺失。Repro 已修到 oracle=1，默认进入拟合。

### 1.5 冻结名单：10 个 3B–14B 主模型 + 1 个 27B 尺子

**不再**等待缺失模型，也**不**根据正式分数换模型。完整 ID、HF、OpenRouter provider、quant、thinking 写在 [`models.lock.yaml`](models.lock.yaml)。目录核查：2026-08-24（北京）/ 2026-08-23（美西）。

这是 **OpenRouter 上当前可调用的 3B–14B 开源 instruct** 的 shell-agent 尺子，不是「专用 coder 小模型榜」。当前 OR 没有稳定可调的 dense 3B–14B 专用 coder。

| 组 | n | 进 \(\theta\) | 模型（固定上游） |
|---|---:|---|---|
| **IRT-main** | 10 | 是 | Llama-3.2-3B (`parasail/bf16`)、Ministral-3B (`mistral`)、Gemma-3-4B (`deepinfra/bf16`)、Qwen3-8B (`alibaba`)、Ministral-8B (`mistral`)、Granite-4.1-8B (`coreweave/bf16`)、Qwen3.5-9B (`parasail/bf16`)、Gemma-3-12B (`deepinfra/bf16`)、Qwen3-14B (`deepinfra/fp8`)、Ministral-14B (`mistral`) |
| **ruler** | 1 | 否 | Qwen3.8-27B (`akashml/bf16`) |

对照结构：Ministral 3B→8B→14B 同代规模；Qwen3 8B→14B 同代规模；Qwen3-8B→Qwen3.5-9B 迭代 vs 堆参数。Llama/Gemma 弱 agent 用来问「普通 instruct 会不会自己变成 shell agent」。

- 协议检查：`hello-world` + `collect-todos`（10×2=20；加尺子则 11×2=22）
- 正式题：10×47=**470**（加尺子 11×47=517）；batch 只表示执行次序
- 全 0 / 全 1 也留；`allow_fallbacks=false`，禁止自动换 provider / 量化
- Qwen3 / 3.5 / 3.8：`reasoning.enabled=false`
- 拟合只对 10 个 main；27B 只画五项通过率

命令：`python scripts/run_locked.py --run --full --group main`（协议 20 + Core 470；中断可续跑）。尺子：`--group ruler` 或 `--group all`。

## 2. 用先验审 47 道：留 / 改 / 弃

不怕从零开始。原则：合五项、题本身没问题、落在 3B–9B 信息量上（Easy 带给地板，Medium 拉 8/9，Hard 候选拉 9 与尺子）。

### 留（对齐先验，k=1 不打架）

**Easy（留作地板，不进「很难」叙事）**

- Edit 11/12：除 `edit-timeout-zero` 外，8B/9B 几乎全 1
- `loc-member-discount`
- Review 完整补丁：`review-slug-complete`（`review-prefix-complete` 8B 挂，更偏 Medium）
- Repro 烟测：`repro-end-exclusive`、`repro-first-index`、`repro-empty-mean`

**Medium（主区分，优先留）**

- Loc：`loc-similar-filenames`、`loc-failing-test-impl`、`loc-reexport`、`loc-unused-fix`
- Edit：`edit-timeout-zero`（唯一 9B=1、8B=0）
- Testgen：clip / unique-order / mean / parse / greet-none / window / timeout-zero / cents
- Repro：`repro-none-name`
- Review：clip-incomplete、slug-almost、mean-wrong、configured-timeout、rotate-right

**Hard 候选（先留，多模型后再定档；不叫 Frontier）**

- Loc：`loc-bind-host`、`loc-vip-two-files`、`loc-traceback-helper`
- Testgen：`testgen-gregorian`
- Repro：`repro-whitespace`、`repro-zero-timeout`、`repro-truthy-flag`

### 改（题型对，写法不对）

- **所有 Repro 的 instruction**：写死「只写 `/app/repro.py`，禁止改 `/app/repo`」。否则测的是策略，9B 会系统性低于 8B。
- `repro-off-by-one` / `repro-keep-zero` / `repro-float-cents`：9B=0、8B=1，先改 instruction 再重测，不先弃。
- `testgen-anagram`：9B=0、8B=1，先当噪声，k 次重复后再决定。
- `loc-traceback-helper`：Terminus-2 上 27B 也 0/3。若 compact-shell 尺子仍 0 → **弃或重出**，不当 Hard。

### 弃（现在就能定）

- 库存同构（本来就不在 47）：不升主表
- oracle/nop 失败的题：修不好就弃（等当前 Gate 跑完）
- 复合 `rec-*`：不当原子

暂不整表推倒。Edit Easy 带 **留着**，否则 3B 没有台阶。信息量不够的是「把 Easy 当成 Medium 讲」，不是题本身非法。

## 2.1 逐题先验表

机读表：[`prior-item-map.json`](prior-item-map.json)。构造档来自 §1 + `TRAPS.md` + 本节，不是 IRT，也不是 Frontier。k=1 来自 compact-shell Novita draft（`jobs/core-k1-screen.json`）；oracle 来自 `jobs/gate-a-oracle-nop.json`。

**Gate A 对 Repro 的含义：** 2026-08-24 已修 verifier `PYTHONPATH=/app/repo` 与 oracle `sys.path`。10 道 MAIN_47 Repro 的 oracle=1、nop=0（`jobs/gate-a-repro-oracle-nop.json`）。draft k=1 重测后 9B 0.30 / 8B 0.40。both_miss **仍不能**叫 Hard；正式 \(b\) 等冻结 16 模型矩阵。

| keep × 档 | Easy | Medium | Hard 候选 | 合计 |
|---|---:|---:|---:|---:|
| keep | 13 | 20 | 4 | **37** |
| rewrite | 4 | 2 | 4 | **10**（全是 Repro） |
| drop | 0 | 0 | 0 | **0** |
| 合计 | 17 | 22 | 8 | **47** |

- **keep × Easy（13）：** `loc-member-discount`；Edit 11 道（除 `edit-timeout-zero`）；`review-slug-complete`。
- **keep × Medium（20）：** Loc 4（similar-filenames / failing-test-impl / reexport / unused-fix）；`edit-timeout-zero`；Testgen 9（除 gregorian）；Review 6（除 slug-complete）。
- **keep × Hard 候选（4）：** `loc-bind-host`、`loc-vip-two-files`、`loc-traceback-helper`、`testgen-gregorian`。都不叫 Frontier；L5 在 Terminus-2 上 27B 也 0/3。
- **rewrite × Easy（4）：** `repro-off-by-one`、`repro-end-exclusive`、`repro-first-index`、`repro-empty-mean`。
- **rewrite × Medium（2）：** `repro-none-name`、`repro-float-cents`。
- **rewrite × Hard 候选（4）：** `repro-zero-timeout`、`repro-keep-zero`、`repro-whitespace`、`repro-truthy-flag`。
- **drop：0。** 47 道都贴合五项原子；Repro 先修 gold，不整表推倒。

`testgen-anagram`（9B TLE / 8B=1）当 k=1 噪声，keep。Loc/Edit/Testgen/Review 的 oracle 均为 1。IRT 仍要等 ≥8 个模型跑 **我们的题**。

## 3. 按模型补题（五项里哪项题不够）

先验 + k=1 显示缺口：

| 原子 | 问题 | 补什么 |
|---|---|---|
| Loc | Medium 够；Hard 可能全是 Unscored | 尺子能过的精确集合（少 decoy、路径规范），不要再堆 L9 |
| Edit | 几乎全 Easy | 若要 Medium Edit：说明仍清楚，但要 **两个约束同时满足**（不改输入 + 稳定排序 + 显式 0）。不要上真实多文件 SWE |
| Testgen | Medium 够；Hard 只有闰年 | 再 1–2 个「例子过、mutant 不过」的历法 / 钱 / 时区类 |
| Repro | 被「修仓」污染 | 先改 instruction；稳定后再看要不要加题 |
| Review | Medium 够 | 可补 1 道「例子过、契约不过」且 9B 也会晃的 |

新题必须：唯一陷阱、oracle=1、nop=0、能估 \(b\) 落在哪一档。

## 4. 之后怎么证明 bench 好

1. 外部先验（本文）定出题档。  
2. oracle/nop 清题。  
3. **冻结的 10 个 main 模型**、同一 compact-shell、固定 OpenRouter provider，才能在 **我们的题** 上做探索性 1PL。27B 尺子不进 \(\theta\)。draft 两个模型不够。  
4. 丢掉 \(a\) 过低的题，主表只留信息量高的，发布 ICC / 测验信息函数。

## 5. 现在不做什么

- 不根据第一批分数换模型
- 不把 both_miss 改名为 Frontier
- 不把 LCB/SWE 平均数当成我们题的 \(b\)，也不在 2 个模型上报告 1PL
- 不把 SWE-Hero / Devstral 和 vanilla 7B 收进同一条未分层的 \(\theta\)
