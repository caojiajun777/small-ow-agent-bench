# Gate A / 发布清单

正式数字见 [`EVAL-NOTE.md`](EVAL-NOTE.md) §6.2 / §11 / §12 / §13。Hard 按 k=3 在 Core 47 锁了 5 道（2 Loc + 1 Testgen + 2 Repro）。v1.0 发表口径是 **API Standard（系统表）**；Local Reference 不是本 tag 的前置。公开仓库已推：https://github.com/caojiajun777/small-ow-agent-bench。v1.0 本身是 API Standard。

## 现在就能勾（不跑模型）

- [x] 五项原子 + unique-trap Core 47
- [x] Loc canonicalize、review 唯一 0/1
- [x] Testgen 隔离、repro 双状态（`scripts/test_verifier_chain.py`）
- [x] `compact-shell` + 冻结语法
- [x] 核心思想写进 README / STANDARD / DIFFICULTY / EVAL-NOTE
- [x] 旧 Terminus-2 / 8B / 9B / Granite job **不进**正式表
- [x] 10 题 compact-shell Novita 通路（9/10；`repro-whitespace` 过修仓）
- [x] `test_std_normalize.py` / `agents/test_protocol.py` / `test_verifier_chain.py`（2026-08-23 本地再跑，exit 0）
- [x] `.env` / `jobs/` 确认不进 git

## draft k=1 筛查（9B / 8B，不是冻结矩阵）

旧命令：`python scripts/run_core_k1.py --run`。产物：`jobs/core-k1-screen.json`。

- [x] 9B 47 题都有非 infra 的 `atomic_correct`
- [x] 8B 同上
- [x] 填 [`EVAL-NOTE.md`](EVAL-NOTE.md) §6.1
- [x] 列出 discriminator / smoke / both_miss（Repro 修补后见最新 screen）
- [ ] **不**根据 both_miss 造 Hard；**不**根据这轮分数换模型

## 冻结 11 模型（[`models.lock.yaml`](models.lock.yaml)）

10 个 3B–14B main + Qwen3.8-27B 尺子。OpenRouter `provider.order` 钉死，`allow_fallbacks=false`。batch 只表示执行次序。一次只开一条 Novita。中断后重跑会跳过已完成的 `(模型, 题)`。

10 模型全跑（不含尺子）：

```text
python scripts/run_locked.py --run --full --group main
```

协议 20 + Core 470 = **490**。先协议再 Core，写 `jobs/protocol-check.json` 和 `jobs/locked-core.json`。尺子：`--group ruler`（已跑，并入同一 JSON，不擦 10 模型行）。

- [x] 10 个 main 协议检查（`hello-world` + `collect-todos`）；legacy `protocol_pass` = `preflight_both_pass`，不是 harness 兼容性
- [x] 10 × 47 = 470；全 0 / 全 1 也留（2026-08-24，infra=0）
- [x] Qwen3.8-27B 尺子 k=1（49 格）；**不进** \(\theta\)。见 [`EVAL-NOTE.md`](EVAL-NOTE.md) §10
- [x] `python scripts/fit_irt.py --score both --group main`（10 个 main；27B 不进 \(\theta\)）→ `jobs/irt-draft.json`

## 筛查之后、tag 之前（再占 Novita，串行）

- [x] MAIN_47 Repro 10：oracle=1、nop=0（`jobs/gate-a-repro-oracle-nop.json`）
- [x] 其余 MAIN_47 + `loc-hardcoded-digital-vat`：oracle = 1、nop = 0（`jobs/gate-a-oracle-nop.json` 里非 Repro 38+1 全绿；Repro 用上一行补跑）
- [x] 命令：`python scripts/run_oracle_nop.py --run`。产物 `jobs/gate-a-oracle-nop.json` / `jobs/gate-a-repro-oracle-nop.json`

## 打 tag

```text
benchmark-v1.0-rc1
```

条件：oracle/nop 绿、EVAL-NOTE §6.1 / §8–10 已填、README 不再把 Terminus-2 写成默认 agent。tag 已打并已推到 [github.com/caojiajun777/small-ow-agent-bench](https://github.com/caojiajun777/small-ow-agent-bench)。k=3 主表后来写进 §6.2 / §11；正式发布 tag 是 `benchmark-v1.0`。

tag 之后改 instruction / verifier → 升 `v1.1` 或整表重跑。

## rc1 之后（k=3 已齐）

正式 Core 表：补 attempts 2–3，使总重复数达到 k=3。**不要** `harbor run -k 3`，**不要**覆盖 `jobs/locked-core.json`。attempt=1 是已有 k=1 格子。

```text
python scripts/run_locked.py --k3-fill --group main
python scripts/run_locked.py --run --k3-fill --group main
python scripts/run_locked.py --run --k3-fill --group ruler
```

- [x] dry-run `--k3-fill --group main` 打出 **940**（10×47×2）
- [x] dry-run `--k3-fill --group ruler` 打出 **14**（7 道 Loc 边界 ×2；不含 `loc-unused-fix`）
- [x] 单条 Novita 串行补 main；每格 `n_valid=3` 才进 mean；infra 重试不占 attempt 号
- [x] 尺子只补 7 道 Loc；产物 `jobs/locked-core-k3.json`（477 格，incomplete 0；未覆盖 `locked-core.json`）
- [x] Core k=3 正式表（EVAL-NOTE §6.2 / §11）
- [x] Frontier / Hard：`loc-member-discount`、`loc-vip-two-files`（9B 0/3 且 27B Atomic 3/3；后者 E2E 未锁）；另 §13 新锁 `testgen-anagram`、`repro-first-index`、`repro-whitespace`
- [x] k=3 探索性 1PL（Binomial(3)，`python scripts/fit_irt.py --k3` → `jobs/irt-k3.json`；不进发表均值）
- [x] 公开 GitHub：https://github.com/caojiajun777/small-ow-agent-bench（`main` + `benchmark-v1.0` / `benchmark-v1.0-rc1`）
- [x] Local Reference：**权重 SHA 已钉**（[`models.local.yaml`](models.local.yaml)，HF `main` @ 2026-08-26）。全表未跑（Linux vLLM + `VLLM_BASE_URL`；`python scripts/run_local_ref.py`）。不覆盖 API 均值。

## 12 模型 Core（2026-08-25 起）

锁文件改为 **12 个正式 Core 模型**（10 compact_dense + Qwen3.8-27B + Qwen3.6-35B-A3B）。`--group main` 仍是原来 10 个。`jobs/locked-core.json` / `locked-core-k3.json` **不覆盖**。Hard-Dev 是 **10** 道，不是 12。

- [x] 35B 协议烟测：`hello-world` + `collect-todos`，Venice，thinking 关，`protocol_pass=true`（2026-08-25）
- [x] Hard-Dev-10（每项 2 道）oracle/nop 后冻结（`jobs/gate-a-hard-dev-oracle-nop.json`）
- [x] Hard-Release-15 Gate-B（foil + 独立性 + grep 锚点）后重新 oracle/nop 冻结（`jobs/gate-a-hard-release-oracle-nop.json`）
- [x] 27B Base-47 k=3 补缺口 + 35B Base-47 k=3 从零。2026-08-26 跑完：`jobs/locked-upper-base-k3.json`，94 格 `n_valid=3`，incomplete 0，infra 0。**未覆盖** `locked-core.json` / `locked-core-k3.json`。`enters_official_mean=false`。命令：`python scripts/run_locked.py --run --base-fill`。数字见 [`EVAL-NOTE.md`](EVAL-NOTE.md) §13。
- [x] Hard-15：6×15×k=3 = 270（Base 47 均 ≥ 0.40 的 compact + 27B + 35B；跳过的不当 0）。2026-08-26 跑完：`jobs/locked-hard-release-k3.json`，90 格 `n_valid=3`，incomplete 0，infra 0。失败构成：`python scripts/fail_compose.py` → `jobs/locked-hard-failure.json`（EVAL-NOTE §12.2）

## 不要做

- 同时再开一条 Novita job（并发沙箱上限 5）
- 把 k=1 筛查或 Terminus-2 标定写进 published mean
- 为了压 9B 合并 Frontier 或放宽 loc
- 看完第一批分数再换模型 / 自动换 OpenRouter provider / 把缺失槽换成 26B MoE 或 30B
