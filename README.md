# small-ow-agent-bench

Harbor 上的 **Atomic Shell-Agent Benchmark for OpenRouter-Available 3B–14B Open-Weight Instruct Models**。测的是 compact-shell 下、当前 OpenRouter **能稳定调用** 的 3B–14B 开源 instruct，不是「专用 coder 小模型榜」（OR 上目前没有稳定的 dense 3B–14B 专用 coder）。

**核心思想：** 不是追求大家都考 50 分，而是测清 3B–14B instruct 在真实 shell agent 里会什么、不会什么，以及和 27B 尺子的边界。用五项原子：`Core` 区分小模型内部；`Frontier` / Hard 找「目标档稳定做不到、27B 稳定能过」的题。大模型只作标尺，不进主 \(\theta\)。

原子能力按 [Scaling Coding Agents via Atomic Skills](https://arxiv.org/abs/2604.05013)（Ma & Liu et al., 2026）拆成五项。每项自己的输入、结构化输出和沙箱奖励；SWE-bench 式修 issue 是这五项的复合，不当原子。

**公开仓库还没推。** 先把题收成 **v1 公开集**（陷阱不重复），同构题只进库存。GitHub 等 v1 基线跑完再发。

测的是 **固定极薄 shell harness（`compact-shell`）下的模型表现**，不是「模型固有 coding 能力」，也不是谁更会填 Terminus-2 的 JSON。正式协议见 [`STANDARD.md`](STANDARD.md)。Terminus-2 只做 harness 对照。旧 8B/9B/Granite job 只当 calibration，不进正式主表；Core 主表 47 道、k=3、n=1。难度标签见 [`DIFFICULTY.md`](DIFFICULTY.md)。超时分型见 [`TIMEOUT.md`](TIMEOUT.md)（只做诊断，不改 atomic 分）。打分字段由 `python scripts/score_standard.py jobs/<job>` 写出。

| 集 / 档 | 作用 | 何时才能用这个名字 |
|---|---|---|
| **Core（Medium）** | 区分 3B–14B instruct 内部差异；小模型主榜 | 目标档（8B 或 9B）能过 |
| **Frontier（Hard）** | 找与 27B 尺子的能力边界；不进小模型主榜 mean | 9B **稳定**不过，并且 27B **稳定**能过 |
| **不入档** | 诊断 / 库存 | 尺子也过不了 |

27B 只当尺子。正式冻结尺子是 OpenRouter `qwen/qwen3.8-27b`（`akashml/bf16`，thinking 关）。还没有锁死的 Frontier 题。

## 文档地图

| 文件 | 看什么 |
|---|---|
| 本文 | 核心思想、47 道题表、怎么跑 |
| [`EVAL-NOTE.md`](EVAL-NOTE.md) | 测什么 / 不测什么、相关工作、k=1 结果（§8–10）；k=3 主表仍空 |
| [`PRIOR.md`](PRIOR.md) | 外部先验 → 47 道留 / 改 / 弃；按五项补题 |
| [`models.lock.yaml`](models.lock.yaml) | 冻结 10+1 模型；固定 OpenRouter provider |
| [`STANDARD.md`](STANDARD.md) | compact-shell 协议、打分、轨道不要混 |
| [`DIFFICULTY.md`](DIFFICULTY.md) | Medium / Hard / 不入档 梯子 |
| [`TRAPS.md`](TRAPS.md) | 每条陷阱只进 Core 一次 |
| [`TIMEOUT.md`](TIMEOUT.md) | 超时分型（不改 atomic） |
| [`GATE-A.md`](GATE-A.md) | 发布 / tag 清单 |

## 当前进度（2026-08-24）

- 协议和 Core 47 构造已冻。正式主表仍是 **47 × k=3**，还没开。
- **模型名单已冻**（[`models.lock.yaml`](models.lock.yaml)）：10 个 3B–14B main + Qwen3.8-27B 尺子。OpenRouter provider 钉死、禁止 fallback。**不根据分数换模型，也不再等缺失模型。**
- k=1 探索矩阵已齐：10×47 = 470，外加尺子 49 格（`jobs/locked-core.json`，517 格，incomplete 0）。三矩阵 / Loc 审计 / 探索性 1PL 见 [`EVAL-NOTE.md`](EVAL-NOTE.md) §8–10。27B **不进** \(\theta\)。
- draft k=1（9B/8B）只作草稿，不进 published mean，也不当 wave2 选模依据。
- Repro oracle/nop 已绿（10/10）。本地 tag **`benchmark-v1.0-rc1`** 已打（未推远程）。Frontier / Hard 仍空。

## 五个原子

| 原子 | 输入 | 输出 | 奖励（论文） |
|---|---|---|---|
| **Code Localization** | issue + 仓库 | 相关文件集合 | 与 gold patch 改动文件 **集合精确匹配** |
| **Code Editing** | 代码上下文 + **明确的改动说明** | patch | 仓库单测 / 回归测试全过 |
| **Unit-Test Generation** | 目标函数 + 说明 | 单测 | 在正确实现上全过，且能抓住注入的 mutant |
| **Issue Reproduction** | issue + 仓库 | 可执行复现脚本 | 当前（有缺陷）代码上失败，打上 gold patch 后不再失败 |
| **Code Review** | issue + 已应用的候选改动 | 二进制判断 0/1 | 与「该改动是否真的解决问题」的标签一致 |

完整陷阱表在 [`TRAPS.md`](TRAPS.md)：每个陷阱只进公开集一次。同构题仍在 `tasks/` 里，不算公开集。instruction 只写契约；gold / mutant / 标签在 `tests/`。

## v1 Core 主集（47 道 unique-trap Medium）

按**陷阱**去重，不是按换皮。这是小模型主榜。L9 等不入档只进诊断，不算五项 mean。Frontier / Hard 另表，目前为空。正式跑法见 [`STANDARD.md`](STANDARD.md)。

### Core / Medium（47）

| 原子 | 题 | 考的陷阱 |
|---|---|---|
| Loc | `loc-member-discount` | 配置是对的，活代码写死错值 |
| Loc | `loc-bind-host` | 同上，但 decoy 文件共享同一字符串 |
| Loc | `loc-vip-two-files` | gold 是两个文件，文件名相近 |
| Loc | `loc-similar-filenames` | 多个 helper 文件名相近，gold 只有一个 |
| Loc | `loc-traceback-helper` | 要标 parser，不要标 traceback 包装 |
| Loc | `loc-failing-test-impl` | 要标实现，不要标失败的测试文件 |
| Loc | `loc-reexport` | 要标定义模块，不要标 `__init__.py` 再导出 |
| Loc | `loc-unused-fix` | 未引用文件已经长得像修复，不要标它 |
| Edit | `edit-slugify` | 文本规范化（大小写、标点、连字符） |
| Edit | `edit-covered-length` | 半开区间并集长度 |
| Edit | `edit-deep-merge` | 嵌套合并、列表替换、不改输入 |
| Edit | `edit-int-list` | 逗号分隔整数，空白和空项 |
| Edit | `edit-top-k` | 按分数稳定 top-k |
| Edit | `edit-jsonl-keep` | 过滤 JSONL，跳过坏行 |
| Edit | `edit-hhmmss` | 时长格式、零填充 |
| Edit | `edit-prefix-sums` | 前缀和，不修改输入 |
| Edit | `edit-clip` | 上下界都要夹 |
| Edit | `edit-timeout-zero` | 显式 `0` 不是缺省（`or` 默认值） |
| Edit | `edit-unique-keep` | 去重且保持首次出现顺序 |
| Edit | `edit-pad-left` | 已经够长时 pad 必须是 no-op |
| Testgen | `testgen-clip` | 缺下界 / 缺上界 / 恒等 mutant |
| Testgen | `testgen-unique-order` | `set()` 丢序、last-wins |
| Testgen | `testgen-gregorian` | 闰年不是 `year%4`；不能只测 2024/2023 |
| Testgen | `testgen-mean` | sum / 只取首元素 |
| Testgen | `testgen-parse` | 不 strip / 保留空项 |
| Testgen | `testgen-anagram` | 大小写、空格 |
| Testgen | `testgen-timeout-zero` | `or` 默认值丢掉显式 `0` |
| Testgen | `testgen-greet-none` | 缺 key / `None` vs 有名字 |
| Testgen | `testgen-cents` | `float` 变分 |
| Testgen | `testgen-window` | 切片 `end+1` / `start+1` |
| Repro | `repro-off-by-one` | 切片 `end+1` |
| Repro | `repro-end-exclusive` | 右端点包含，内部点测不出来 |
| Repro | `repro-zero-timeout` | `or 30` 把显式 `0` 吃掉 |
| Repro | `repro-keep-zero` | `if n` 丢掉 `0` |
| Repro | `repro-none-name` | 缺 key / `None` |
| Repro | `repro-float-cents` | `float` 变分 |
| Repro | `repro-first-index` | last-wins，必须用重复元素 |
| Repro | `repro-empty-mean` | 空输入必须报错；返回 `0` 测不出来 |
| Repro | `repro-whitespace` | 周围空白；`'1,2'` 过、`' 1, 2'` 不过 |
| Repro | `repro-truthy-flag` | 缺 key vs 显式 `0`（flag） |
| Review | `review-clip-incomplete` | 只处理下界，标签 0 |
| Review | `review-slug-almost` | 近乎完整但 collapse/strip 不对，标签 0 |
| Review | `review-mean-wrong` | 返回总和，标签 0 |
| Review | `review-slug-complete` | 完整实现，标签 1 |
| Review | `review-configured-timeout` | `or` 默认值丢掉显式 0 |
| Review | `review-rotate-right` | 方向写反，标签 0 |
| Review | `review-prefix-complete` | 完整前缀和，标签 1 |

### 经验档（27B + 目标档 loc 之后）

| 档 | 题 | 依据 |
|---|---|---|
| **不入档** | L9 精确集合（`loc-hardcoded-digital-vat` 等同构） | 9B / 14B / 27B 都是 gold+decoy |
| **不是 Hard** | L2 `loc-bind-host` | 9B `k=3` 为 **2/3**；v0 的一次 0 是噪声 |
| **不是 Hard** | L3 `loc-vip-two-files` | 9B `k=1` 漏文件，`k=3` 为 **3/3** |
| **不是 Hard** | `testgen-gregorian` | 9B `k=1` 为 0；27B `k=1` 为 1；9B `k=3` 为 **3/3** |

**定位分界在家族，不在 Hard：** Ministral 8B 本轮 unique-trap loc **0/8**（超时、多报 decoy、`app/repo/` 前缀）；Qwen3.5-9B 多数能过精确集合。没有「9B 稳定不过、27B 能过」的 Hard loc。

**其余原子（Novita `-n 5`，`k=1`）：** 9B **38/39**，8B **28/39**。9B 编辑 / 复现 / 评审全过。`testgen-gregorian` 的一次 0 是噪声：27B 为 1，9B `k=3` 为 **3/3**，**不是 Hard**。8B Harbor 上 11 次超时：5 次是已经写对但没停（`timeout_after_pass`），6 次空转（`timeout_loop`），**0 次卡顿**。真正写错只有 4 道。不要用空转超时标 Hard。完整数字见 [`DIFFICULTY.md`](DIFFICULTY.md) 和 [`TIMEOUT.md`](TIMEOUT.md)。

## 同构库存（不算公开集）

| 原子 | 题 | 相对 v1 重复了什么 |
|---|---|---|
| Loc | `loc-config-key`, `loc-log-path`, `loc-retry-max`, `loc-cache-ttl` | 配置对、活代码写死，同 `loc-member-discount` |
| Loc | `loc-hardcoded-vip-branch`, `loc-hardcoded-digital-vat` | 活分支 vs 死 RATE，同 `loc-hardcoded-fast-timeout` |
| Edit | `edit-digits-only`, `edit-rotate-left` | 点名小函数 + 边角，分别近过滤 / 不改输入 |
| Testgen | `testgen-pad`, `testgen-digits`, `testgen-rotate` | 近 clip / 字符类 / 方向 mutant |
| Repro | `repro-start-index` | 近 `repro-off-by-one` |
| Review | `review-hi-only`, `review-no-lower` | 近 `review-clip-incomplete`（只做了一半） |
| Review | `review-digits-complete` | 近 `review-slug-complete`（标签 1） |

`rec-*` 是复合修复，不在五项里。

## v0 内部切片（已跑，不是公开集）

当时每原子 1 旧 + 1 同构，用来看小模型掉在哪。terminus-2，OpenRouter，`-k 1 -n 1`。testgen verifier 已隔离 `PYTHONPATH`。

| 角色 | Harbor 模型 | 权重发布 |
|---|---|---|
| 主力 | `openrouter/qwen/qwen3.5-9b` | 2026-03-02 |
| 同档对照 | `openrouter/mistralai/ministral-8b-2512` | 2025-12-02 |

更早浅题还跑过 Ministral 3B/14B（2025-12-02）、Nemotron Nano 9B v2（2025-08-18）、Granite 4.1 8B（2026-04-29），不进切片表。

### Medium（10 道）

terminus-2，OpenRouter，`-k 1 -n 1`。testgen verifier 已隔离 `PYTHONPATH`，防止测例 `sys.path.insert(0, "/app/repo")` 绑到活仓库里的 gold。

| 角色 | Harbor 模型 | 权重发布 |
|---|---|---|
| 主力 | `openrouter/qwen/qwen3.5-9b` | 2026-03-02 |
| 同档对照 | `openrouter/mistralai/ministral-8b-2512` | 2025-12-02 |

更早浅题还跑过 Ministral 3B/14B（同日 2025-12-02）、Nemotron Nano 9B v2（2025-08-18）、Granite 4.1 8B（2026-04-29）。那些不进本切片主表。

### Medium（10 道）

每原子 1 道旧题 + 1 道同构新题。

| 原子 | 题 | Qwen3.5-9B | Ministral 8B |
|---|---|---|---|
| Loc | `loc-member-discount` | 1 | 0 |
| Loc | `loc-bind-host` | 0 | 0 |
| Edit | `edit-slugify` | 1 | 1 |
| Edit | `edit-digits-only` | 1 | 1 |
| Testgen | `testgen-clip` | 1 | 1 |
| Testgen | `testgen-digits` | 1 | 1 |
| Repro | `repro-off-by-one` | 1 | 1 |
| Repro | `repro-keep-zero` | 1 | 1 |
| Review | `review-clip-incomplete` | 1 | 1 |
| Review | `review-rotate-right` | 1 | 1 |
| | **合计** | **9/10** | **8/10** |

### 当时叫 Hard 的 2 道（经验档作废前）

| 题 | Qwen3.5-9B | Ministral 8B |
|---|---|---|
| `loc-hardcoded-fast-timeout` | 0 | 0 |
| `review-dollar-cents` | 1 | 0 |

### 失败怎么记

- **定位**：精确集合对不上。9B 在 `loc-bind-host` 多写 decoy `netutil.py`；8B 在 `loc-member-discount` 写成散文标题 + `app/repo/` 前缀；`loc-bind-host` 超时且没有 `answer.txt`。Hard loc：9B 是 gold + decoy，8B 列了 profile、漏了 `resolve.py`。
- **测例**：隔离前 9B 因 `sys.path.insert(0, "/app/repo")` 被记 0，测例本身能抓住 mutant。那是脚手架/量法问题，**不要记成「不会写测」**。隔离后两家切片 testgen 都是 1。
- **Hard 评审**：8B 只跑了 issue 里的 `'10'` / `'1.00'` 就写 1（例子过了 ≠ 实现对）。9B 这次跑了 `0.29` 才判 0。k=1，换一次可能翻。
- **协议/JSON**：单独记。8B 若干 loc/review 轨迹里有 JSON 脚手架噪音；超时且 0 token 记超时，不记定位能力。

不宣称：3B/8B/14B 梯子；官方 aider.chat 分数；7B～9B 是一条能力带。v0 切片里的 `edit-digits-only` / `testgen-digits` 是同构题，正式分数改看 v1。

## 怎么跑

沙箱用 **Novita**（`-e novita`，`n=1`）。本机 Docker 内存紧，不要 `-n 8`。Agent 用 **compact-shell**，不要默认 Terminus-2。复制 `.env.example` 为 `.env`，不要提交 `.env`。先不要推 GitHub。

```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = (Get-Location).Path

# 10 个 IRT-main 全跑（协议 20 + MAIN_47 470 = 490）。当前若已有一条 Novita job，不要再开第二条。
# 中断后同样命令会跳过已完成的格子。尺子用 --group ruler 或 --group all。
python scripts/run_locked.py
python scripts/run_locked.py --run --full --group main

# 单题
harbor run --env-file .env -o jobs -p ./tasks/loc-member-discount `
  -a agents.compact_shell:CompactShellAgent `
  -m openrouter/qwen/qwen3.5-9b -k 1 -n 1 -e novita `
  --ak 'llm_call_kwargs={"extra_body":{"enable_thinking":false}}'

# 打分（单 job）
python scripts/score_standard.py jobs/<job>

# 冻结 490 重标：A / T / E 三矩阵 + 失败分类 + Loc P/R（不覆盖 locked-core.json）
python scripts/relabel_locked.py
python scripts/audit_loc.py
python scripts/fit_irt.py --score both --group main
```

题自洽（等当前筛查结束后再跑，避免 429）：

```powershell
harbor run --env-file .env -o jobs -p ./tasks/loc-bind-host -a oracle -k 1 -n 1 -e novita
harbor run --env-file .env -o jobs -p ./tasks/review-clip-incomplete -a nop -k 1 -n 1 -e novita
```

oracle 必须 1.0，nop 必须 0.0。清单见 [`GATE-A.md`](GATE-A.md)。

## 附录：协议检查 / 终端烟测

`hello-world` 与 `collect-todos` 只是 **preflight**（两题都对且干净停 = `preflight_both_pass`）。legacy 字段仍叫 `protocol_pass`，**不是** harness 兼容性。真协议率从 `compact-shell.json` 重算。

## 以后才做

顺序：冻结名单 → 10×47 已齐 → 三矩阵 / Loc 审计 / 探索性 1PL → 尺子 k=1（已完成，见 EVAL-NOTE §8–10）→ tag `benchmark-v1.0-rc1`（本地已打）→ Frontier / 正式表 k=3。

先不做：

- 用「9B 掉了」或 both_miss 发明 Hard
- 把 L9 精确集合改成子集匹配来制造通过者
- 为了压 9B 把 Frontier 并进 Core mean
- 3B DPO / SFT / 论文里的 joint RL
- Aider Polyglot 迁移与官方榜
- 五项拼起来的复合 Issue Resolve
- Harbor registry / 自建提交站
