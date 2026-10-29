# SmallOWBench 2.0 — release notes

Results status: the resumed configuration encountered another shared-upstream-pool 429. Seven configurations have complete 62-task results; Qwen3.5-9B remains partial at 29/62 with two infra attempts and 31 unvisited slots. The separately approved retry has not executed. [Completed-configuration results](RESULTS-PARTIAL-20261029.md) are published with the global full-roster acceptance flag still false.

2026-10-29 closeout update: 32 unvisited slots continue, and the user separately approved exactly one HTTP-429 retry. The unique scored-slot target remains 496; the attempt ceiling is 497 with the original infra preserved. Two existing fail/zero capture errors have a limited negative-evidence supplement. No complete result is claimed before final acceptance. See the [closeout protocol](CLOSEOUT-PROTOCOL-20261029.md).

2026-10-29 update: the user waived the monetary admission cap for the ongoing run. Its initial 120 scored attempts are retained; the remaining 376 continue with unchanged evaluation resources. US$40 references below describe the initial phase. See the [dated execution amendment](MONETARY-POLICY-AMENDMENT-20261029.md).

原始源码发布日期：2026-10-28；结果状态更新于 2026-10-29。发布组件为 task／grader `2.0.0-rc.2`、harness `2.0.0-rc.1`，使用独立 release CLI。已公开 7 个完整配置的首轮成绩，整个原定名册仍不完整；运行身份和状态以冻结记录及本页修订为准。

SmallOWBench 是面向紧凑开放权重 Coding Agent 的可执行诊断基准。2.0 将 62 个任务改写为人工设计的小型 Python 工程工作流，用确定性验证器检查交付物，并区分产物正确与协议正常完成。任务在开发过程中已经被检查、修复和试跑；它们不是未见保留集，也不代表真实大型仓库 issue 或长程自主软件维护。

**当前成绩来自实际运行与原始证据验收。** 初始范围为 8 个原配置 × 62 题 × 1 次重复、最多 496 个任务尝试、US$40、4 workers、整槽 infra 重试 0 次。费用条件随后撤销，唯一 429 重试例外的批准与条件见本页顶部。496 是唯一评分槽位目标，不是 HTTP 请求数；多轮交互和客户端调用级重试会产生更多请求。旧版榜单、RC1 校准和工程诊断保持各自历史口径，未混入新成绩。

## 发布身份与内容

| 内容 | 当前可核对身份 |
|---|---|
| 任务库 | `task-banks/rc2/tasks`，62 个任务 |
| 任务／grader | `2.0.0-rc.2` |
| 轻量 harness | `2.0.0-rc.1`，`agents.compact_shell_v2:CompactShellV2Agent` |
| 候选 manifest | `task-banks/rc2/task-bank-v2.manifest.json` |
| 候选 manifest 文件 SHA-256 | `c2e36e21eff887a688149347d47c7af45c0cf0aa072ef3eff95d684ef4c92b87` |
| 候选 manifest 内部规范摘要 | `dafae53f5ee3aa0afd4c02bd952399a7fe2179217c65e48457b2dd4989e2e889` |

2.0 是项目发布名称。任务、harness、grader 的实际版本分别记录，不把仍为 RC 的组件改称经过全部验收的稳定版。新的 release manifest 额外绑定本轮执行配置与证据，不修改原 manifest 中的候选状态，也不改变历史 `VERSION`、题库和运行记录。

这次交付包含任务源码、公开工作区、参考解、独立判卷器、交付格式自检工具，以及版本和证据绑定的执行／分析代码。参考解与隐藏判卷材料供评测维护者复核；运行时仍须与 Agent 工作区分离，不能把整个题目目录挂载给 Agent。

## 五项技能

| 技能 | 题数 | 要求与主要产物 |
|---|---:|---|
| Localization / Loc | 11 | 依据问题定位完整文件集合，提交 `/app/answer.txt`；不得改写 repo |
| Editing / Edit | 15 | 在已指定范围内修改 `/app/repo`，通过行为与回归检查 |
| Test Generation / Testgen | 13 | 向 `/app/repo/tests` 提交测试，放过正确实现并发现错误实现；不得改应用源码 |
| Reproduction / Repro | 13 | 提交 `/app/repro.py`，在缺陷版本触发问题、标准修复后通过；不得修 repo |
| Patch Validation / Review | 10 | 提交 schema-2 `/app/review.json`，判断候选补丁并给出所需证据；不得改 repo |

Review 的 40 个候选嵌套在 10 道任务中，主统计单位仍是 62 道任务。

## 分数如何解释

- **Artifact**：隐藏 verifier 确认交付物正确。
- **Clean**：Artifact 正确，并且 Agent 按协议正常 finish。Clean 不是实际软件开发的端到端成功率。
- 每项技能内任务等权，五项技能等权得到 macro；另报全部 62 题的 task-micro。新版不使用旧版经验难度权重或旧 IRT 结论。
- 基础设施故障、可信 grader 错误和未完成槽位保留各自状态，不填成模型零分。缺失或未解决的证据不能生成完整正式排名。

榜单比较的是模型、供应商路由、请求参数、harness 和预算组成的系统配置。API 运行结果不能直接外推到相同模型的所有本地量化、推理引擎、延迟或成本条件。

## 已有验证证据

[公开证据摘要](PUBLIC-EVIDENCE.md) 汇总了 2026-10-27 RC2 流水线原始报告中的以下事实。它是去标识投影，保留原件哈希与覆盖范围，不是原始报告、完整轨迹或 validator 的替代输入：

- 合并离线回归 **232 passed、1 skipped**，没有失败或错误；跳过项是本机没有创建真实 symlink 的权限，不能算作通过。
- 五技能固定抽样各一题，共 **10 个 oracle/nop 槽符合预期**：5 个参考解 pass、5 个空提交 fail。题目为 `loc-bind-host`、`edit-clip`、`testgen-timeout-zero`、`repro-keep-zero`、`review-clip-incomplete`。
- 10 槽均经过真实 Linux agent／grader 容器；原始产物重验通过，含 20 份双角色禁网证据、原生 grader `/tmp`、82 个传输文件的双向字节核对。82 是传输文件数，包含预置文件，不是 82 道题或 82 份新答案。
- 镜像构建显式联网，agent、grader 与版本探针运行禁网；这次验证没有模型调用，也没有新增模型费用。

这些是所选链路的工程证据，不构成 62 题完整容器验收、模型表现估计或新版优于旧版的结论。该报告明确保留 `container_validated/full_bank_coverage/release_gate_passed=false`。RC1 的旧 `full124` 证据不转移到 RC2。没有为这次源码发布追加 smoke 或校准。

## 使用与复现

新入口为 `scripts/run_release_v2.py`，使用独立 `release_v2_*` 模块，显式绑定 RC2 题根。不得将旧 `run_locked.py`、旧 `./tasks` 单任务示例或旧 RC1 `run_v2.py` 命令当成 RC2 发布入口。

先按 [Harbor 固定依赖说明](../../../vendor/harbor-patches/README.md) 安装相邻 checkout：固定 upstream `https://github.com/harbor-framework/harbor` 的 base `f03db62fd2ed2ed1f79aefe024cfcbc68a0d759e`，应用 `0001-smallowbench-runtime.patch`，再通过 base 中的 `uv.lock` 执行 `uv sync --locked`。使用该虚拟环境的 Python，从本仓库根目录运行。

首次外部克隆若没有本机五题原始证据，可先在自己的机器生成它们；`r2smk` 必须尚不存在：

```powershell
python scripts/validate_rc2_containers.py --directory experiments/smallowbench-v2/r2smk --execute --allow-build-network
```

这只初始化复现者本机 profile、五题 10 个 oracle/nop 槽和传输记录，无模型调用；构建显式联网、运行禁网。**本轮正式运行已经拥有原始证据，不重新执行这一步，不追加 smoke 或校准。** 不复制发布者的绝对路径收据，也不将公开脱敏摘要直接喂给 validator。

随后初始化 62 题双镜像并冻结正式运行。新运行应使用尚不存在的短目录，不能覆盖已有证据；这里的 `rel2` 为运行目录示例。

```powershell
# 只构建／绑定双镜像并记录版本；无 oracle/nop、模型调用或校准。
python scripts/build_release_v2_images.py --output experiments/smallowbench-v2/im2 --execute --workers 4 --allow-build-network
python scripts/run_release_v2.py prepare --directory experiments/smallowbench-v2/rel2 --models-file analysis/v2/models.route-ready.json --preflight experiments/smallowbench-v2/r2smk/preflight-rc2.json --runtime experiments/smallowbench-v2/im2/runtime.json --budget-usd 40 --workers 4 --max-infra-retries 0 --visit-reserve-usd 3.5 --repetitions 1 --isolate-model-infra --write
python scripts/run_release_v2.py lock --directory experiments/smallowbench-v2/rel2 --write
python scripts/run_release_v2.py plan --directory experiments/smallowbench-v2/rel2 --write
python scripts/run_release_v2.py status --directory experiments/smallowbench-v2/rel2
python scripts/run_release_v2.py analyze --directory experiments/smallowbench-v2/rel2
```

prepare 创建新 STOP；prepare／lock／plan 默认只读，`--write` 才落盘。用户对本轮矩阵和 US$40 的同意还需由授权操作者绑定到独立 `authorization.json`（manifest、execution lock、预算），并处理新运行的初始 STOP。随后执行：

```powershell
python scripts/run_release_v2.py execute --directory experiments/smallowbench-v2/rel2 --execute --worker 0 --workers 4
```

这只启动编号 0 的 worker；四 worker 运行分别启动 0–3 的独立进程，均传 `--workers 4`。省略 `--execute` 只打印计划，不调用模型。预算控制可能提前停止新任务入场，供应商故障按冻结策略暂停该模型；缺槽不能生成完整正式排名，也不释放历史未知费用预留或解除旧 STOP。

以上命令依赖自己机器生成的五题原始证据及新 runtime 记录的完整文件绑定。公开脱敏摘要有单独哈希，不能直接代替原始输入；新安装不证明与发布运行字节一致。公开材料可复核到什么范围，应在最终包清单中说明。

复现需同时保留候选题库及其受保护的 RC1 来源文件：当前候选完整性检查会核对原 `tasks`、原 manifest、`VERSION` 和所绑定源码。文件在包内共存不表示可混用题根或成绩。

**跨宿主平台摘要限制**：旧 `validate_upgraded_tasks.task_digest` 使用 `sorted(Path.rglob(...))`，Windows 与 Linux 的 `Path` 大小写排序规则不同。冻结的文件字节与逐文件 SHA-256 清单可复核，但旧目录聚合摘要尚未确认跨平台一致；因此不能承诺 Linux 宿主的新克隆直接通过原聚合摘要检查。本轮继续在 Windows 宿主同平台运行，不修改冻结函数或摘要值，也不为此增加测试阶段。

宿主执行依赖 Python 3.12 或更高版本、本轮绑定的 Harbor 源码与 Python 依赖，以及 Linux Docker。固定依赖补丁及 Harbor Apache-2.0 许可证随 `vendor/harbor-patches` 分发，项目完整许可证和署名见根 `LICENSE`／`NOTICE`。已验证五题容器实际使用 Python 3.12.3／pytest 7.4.4；这不是对所有题目镜像版本的声明。复现应记录本机实际 Harbor 源树身份、依赖版本和 agent／grader 镜像摘要，不能只安装任意同名 Harbor 版本或凭浮动镜像标签声称重建了发布环境。

公开交付自检工具只检查提交结构、格式和路径约束；它不执行提交，不判断语义正确，也不等于 Artifact 或 Clean 通过。完整协议和公开证据范围见 [STANDARD-v2.md](../../../STANDARD-v2.md) 与 [公开证据摘要](PUBLIC-EVIDENCE.md)；发生版本范围差异时，以本次发布的组件绑定和证据范围为准。

## 已知限制

- 62 题均为人工开发的小型 Python 工作流，规模、语言、来源和开发期反馈覆盖有限。当前经验难度为 `uncalibrated`，不能继承旧版难度校准，也不能把开发样本视为独立验证集。
- 固定五题的容器通过不证明其余 57 题已通过相同链路。正式新分数必须来自本轮完整、版本一致且可复核的运行；本草案未声明这项结果已经发生。
- 分离 verifier、运行禁网和普通文件只读权限具有各自边界，不能当作对任意恶意 Python／pytest 的完整安全保证。终止后的有界产物采集也不是原子快照。
- 历史 2026-10-20 路由盘点中，Gemma-3-4B 遭遇共享池 429，Qwen3-14B 未验证关闭推理，Qwen3-8B／Granite-4.1-8B 没有可用端点，未加入本轮 8 配置。2026-10-28 的 [8 配置公开目录核对](ROUTES.md) 确认原端点元数据匹配，没有新增生成请求；目录匹配和历史短请求通过不代表长期可用性、长任务容量或参数实际生效。本轮以冻结路由和实际记录为准；缺失路由不替换成后继模型，不填零，不混入完整榜单。
- 请求调用级重试与整槽重试不同；拿不到账单的请求保留未知费用。费用与本地硬件性价比均不能由现有工程证据推断。

## 引用与许可证

引用本项目时应使用发布包中的 `CITATION.cff`（软件版本 `2.0.0-rc.2`），同时记录准确的发布标识和组件版本；尚无本次发布对应的论文或 DOI，不构造引用条目。仓库声明 Apache-2.0；发布包需携带完整许可证及所再分发依赖所需的署名／许可证材料。发布文件范围与私密产物排除规则见 [PUBLICATION-CHECKLIST.md](PUBLICATION-CHECKLIST.md)。

本次新提交中的 14 份旧 `jobs` JSON 是明确标注的去标识历史投影：Windows 用户 home 前缀替换为 `<HISTORICAL_USER_HOME>/`，其余字段与数值保留。它们不能代替原始配置或用于核对旧原件哈希。原始版本可从 [历史提交 `fa5a1d5527d945f64053dd75c48bd9553febffc4`](https://github.com/caojiajun777/small-ow-agent-bench/tree/fa5a1d5527d945f64053dd75c48bd9553febffc4) 获取，其中包含历史宿主目录。旧公开分数与 `results` 不改。

## English summary

SmallOWBench 2.0 is an execution-based diagnostic benchmark for compact open-weight coding agents: 62 authored, developed small Python workflows across localization, editing, test generation, bug reproduction and patch validation. Artifact measures verified deliverables; Clean additionally requires a normal protocol finish and is not a real-world software-development E2E success rate. The current task/grader components are `2.0.0-rc.2`, while the harness remains `2.0.0-rc.1`. Existing evidence covers 232 passing offline tests with one skipped test, and five selected tasks with ten oracle/no-op container slots meeting their expected outcomes. Results for seven completed configurations are published; one provider-limited configuration remains partial. Legacy scores, RC1 container acceptance and development diagnostics do not transfer to the new task bank.
