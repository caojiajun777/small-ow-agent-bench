# small-ow-agent-bench

Harbor 上的 **小量级模型 Agentic Coding** 评测集（大约 3B～9B，本地可部署）。目标不是替代 Claude Code / SWE-bench / Terminal-Bench 3，也不是按模型尺寸做 IRT 梯子，而是按五项原子能力看这一量级的 coding agent 会做什么、在哪一类题上掉。

原子能力按 [Scaling Coding Agents via Atomic Skills](https://arxiv.org/abs/2604.05013)（Ma & Liu et al., 2026）拆成五项。每项自己的输入、结构化输出和沙箱奖励；SWE-bench 式修 issue 是这五项的复合，不当原子。

**Phase 1 评测切片已冻住。** 公开发布就是这个 GitHub 仓库：clone 下来用 Harbor 跑。后训练、Aider、Harbor registry 都先不做。题库可以大于切片；报告分数只用下面这 12 道。

提交成绩：开一个 GitHub Issue，写清模型 ID、agent（默认 terminus-2）、`-k`、每题 0/1。维护者把数字填进下面的表。

这是诊断集，不是尺寸梯子。7B～9B 不是同一能力带；编辑在现有题上容易饱和；Hard 定位考精确集合，不是「更大就该过」；Hard 评审考例子过了不等于实现对。

| 档 | 含义 |
|---|---|
| **Medium** | 走完该原子的 agent 闭环（命名 I/O、沙箱奖励）。 |
| **Hard** | 只保留定位（活路径 vs decoy）和评审（例子过了 ≠ 实现对）。 |

不设 Easy 主表。旧 easy / 同轴加题都并进 Medium 题库。

## 五个原子

| 原子 | 输入 | 输出 | 奖励（论文） |
|---|---|---|---|
| **Code Localization** | issue + 仓库 | 相关文件集合 | 与 gold patch 改动文件 **集合精确匹配** |
| **Code Editing** | 代码上下文 + **明确的改动说明** | patch | 仓库单测 / 回归测试全过 |
| **Unit-Test Generation** | 目标函数 + 说明 | 单测 | 在正确实现上全过，且能抓住注入的 mutant |
| **Issue Reproduction** | issue + 仓库 | 可执行复现脚本 | 当前（有缺陷）代码上失败，打上 gold patch 后不再失败 |
| **Code Review** | issue + 已应用的候选改动 | 二进制判断 0/1 | 与「该改动是否真的解决问题」的标签一致 |

## 冻切片（报告用）

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

### Hard（2 道）

| 题 | Qwen3.5-9B | Ministral 8B |
|---|---|---|
| `loc-hardcoded-fast-timeout` | 0 | 0 |
| `review-dollar-cents` | 1 | 0 |

### 失败怎么记

- **定位**：精确集合对不上。9B 在 `loc-bind-host` 多写 decoy `netutil.py`；8B 在 `loc-member-discount` 写成散文标题 + `app/repo/` 前缀；`loc-bind-host` 超时且没有 `answer.txt`。Hard loc：9B 是 gold + decoy，8B 列了 profile、漏了 `resolve.py`。
- **测例**：隔离前 9B 因 `sys.path.insert(0, "/app/repo")` 被记 0，测例本身能抓住 mutant。那是脚手架/量法问题，**不要记成「不会写测」**。隔离后两家切片 testgen 都是 1。
- **Hard 评审**：8B 只跑了 issue 里的 `'10'` / `'1.00'` 就写 1（例子过了 ≠ 实现对）。9B 这次跑了 `0.29` 才判 0。k=1，换一次可能翻。
- **协议/JSON**：单独记。8B 若干 loc/review 轨迹里有 JSON 脚手架噪音；超时且 0 token 记超时，不记定位能力。

不宣称：3B/8B/14B 梯子；官方 aider.chat 分数；7B～9B 是一条能力带。

## 题库（大于切片）

instruction 只写契约。隐藏 gold / mutant / 标签在 `tests/`。

### Medium

| 原子 | 题 |
|---|---|
| Localization | `loc-member-discount`, `loc-vip-two-files`, `loc-similar-filenames`, `loc-config-key`, `loc-traceback-helper`, `loc-failing-test-impl`, `loc-bind-host`, `loc-log-path`, `loc-retry-max`, `loc-cache-ttl` |
| Editing | `edit-slugify`, `edit-covered-length`, `edit-deep-merge`, `edit-int-list`, `edit-top-k`, `edit-jsonl-keep`, `edit-hhmmss`, `edit-pad-left`, `edit-prefix-sums`, `edit-digits-only`, `edit-rotate-left` |
| Unit-test generation | `testgen-clip`, `testgen-unique-order`, `testgen-gregorian`, `testgen-mean`, `testgen-parse`, `testgen-anagram`, `testgen-pad`, `testgen-digits`, `testgen-rotate` |
| Issue reproduction | `repro-off-by-one`, `repro-end-exclusive`, `repro-zero-timeout`, `repro-none-name`, `repro-float-cents`, `repro-truthy-flag`, `repro-start-index`, `repro-keep-zero`, `repro-first-index` |
| Code review | `review-clip-incomplete`, `review-slug-almost`, `review-mean-wrong`, `review-slug-complete`, `review-configured-timeout`, `review-hi-only`, `review-no-lower`, `review-digits-complete`, `review-rotate-right` |

### Hard

| 原子 | 题 |
|---|---|
| Localization | `loc-hardcoded-vip-branch`, `loc-hardcoded-fast-timeout`, `loc-hardcoded-digital-vat` |
| Code review | `review-floor-mean`, `review-dollar-cents` |

Hard 定位：gold 是单文件硬编码分支，旁边的 `VIP_RATE` / `FAST_SECONDS` / `DIGITAL_RATE` 是死 decoy。Hard 评审：issue 里的例子会过，一般定义不过。`review-configured-timeout` 契约写得太直，9B 能过，已降回 Medium。

`rec-*` 是更早的复合修复题，不在五项里。

## 机器限制

本机 Docker Desktop 内存紧张。一律：

```bash
harbor run -p <task_dir> -a <agent> -k 1 -n 1
```

不要 `-n 8`。

## 先验证题（不调模型）

每题 oracle 必须 1.0，nop 必须 0.0。

```powershell
$env:PYTHONIOENCODING = "utf-8"
harbor run -p ./tasks/loc-bind-host -a oracle -k 1 -n 1
harbor run -p ./tasks/review-no-lower -a nop -k 1 -n 1
```

## 再跑模型（OpenRouter）

复制 `.env.example` 为 `.env`，填入你自己的 OpenRouter key，不要提交 `.env`。切片命令：

```powershell
$env:PYTHONIOENCODING = "utf-8"
harbor run --env-file .env -p ./tasks/loc-member-discount -a terminus-2 -m openrouter/qwen/qwen3.5-9b -k 1 -n 1
```

## 附录：8 道终端题

`collect-todos` 等 8 题是 Harbor 冒烟 / 附录（grep / JSON / CSV），**不是**本 bench 的 coding 原子轴。

## 以后才做（现在不做）

- 3B DPO / SFT / 论文里的 joint RL
- Aider Polyglot 迁移与官方榜
- 再扩同构 Medium；loc k=3
- Hard 编辑 / 测例 / 复现（现有题 9B 仍过，不硬凑尺寸梯子）
- 五项拼起来的复合 Issue Resolve
- 把精确集合改成子集匹配
