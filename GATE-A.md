# Gate A / 发布清单

正式数字和 Hard 等 k=1 筛查。本清单不占 Novita。打 tag 前每一项都要绿。

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

条件：oracle/nop 绿、EVAL-NOTE §6.1 / §8–10 已填、README 不再把 Terminus-2 写成默认 agent。本地已打；**未 push**。

tag 之后改 instruction / verifier → 升 `v1.1` 或整表重跑。

## tag 之后才做（不要提前）

- Core k=3 正式表（API 或 Local Reference）
- Frontier / Hard（9B 稳 0 且尺子稳 1；不能用 draft both_miss）
- 公开 GitHub

## 不要做

- 同时再开一条 Novita job（并发沙箱上限 5）
- 把 k=1 筛查或 Terminus-2 标定写进 published mean
- 为了压 9B 合并 Frontier 或放宽 loc
- 看完第一批分数再换模型 / 自动换 OpenRouter provider / 把缺失槽换成 26B MoE 或 30B
