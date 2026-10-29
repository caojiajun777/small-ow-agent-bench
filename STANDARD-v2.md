# SmallOWBench 2.0 评测协议

2026-10-29 收口修订：对 32 个未访槽位续跑，并仅对原 HTTP 429 槽追加一次单独获批的尝试；有效评分仍为 496 个唯一槽位，实际尝试上限为 497。两条原已判零的采集异常仅通过严格限定的负观察证据补充验收，原记录不改。完整条件与新分析入口见[收口协议](analysis/v2/release-20261028/CLOSEOUT-PROTOCOL-20261029.md)。

2026-10-29 运营修订：本轮费用准入上限已按用户要求取消，评测资源和总尝试次数不变。原 US$40 记录属于初始执行阶段；后续实际费用策略、续跑来源与报告要求见[修订说明](analysis/v2/release-20261028/MONETARY-POLICY-AMENDMENT-20261029.md)。

发布说明更新于 2026-10-28。本次组件版本：benchmark／task／grader 为 `2.0.0-rc.2`，harness 为 `2.0.0-rc.1`。本文只约束 2.0；旧版 `STANDARD.md`、榜单、实验锁和原始结果保持历史口径。

## 范围与发布状态

本次题库位于 `task-banks/rc2/tasks`，沿用原有 62 个 ID：Loc 11、Edit 15、Testgen 13、Repro 13、Review 10。任务已改写为人工设计的小型 Python 工程工作流，在开发过程中已检查、修复和试跑；不视为未见保留集，不标为真实 GitHub issue，也不宣称覆盖大型仓库或长程自主维护。

题目身份以 `task-banks/rc2/task-bank-v2.manifest.json` 为准，新入口为 `scripts/run_release_v2.py`，独立使用 `release_v2_*` 执行与分析模块。根 `VERSION`、原 `tasks`、`task-bank-v2.manifest.json` 和旧 pipeline 保留 RC1 身份，仍是候选来源指纹核对的依赖，不静默修改。原候选 manifest 的“未激活／未授权”元数据也不原地改写；新发布运行使用独立 manifest、execution lock 与授权文件。同名 ID 不意味着语义相同；旧成绩不能用于本次排名或难度校准。经验难度仍是 `uncalibrated`，不沿用旧 IRT 结论。

必须分别记录三个状态：

1. 离线可信参考解与空提交验收。
2. 真实 Linux／Harbor 容器验收。
3. 授权后的模型工程试跑、预算校准与正式模型测评。

前一道通过不能代替后一道。RC2 现有证据为 2026-10-27 固定五题的 10 个 oracle/nop 槽符合预期（5 参考解 pass、5 空提交 fail），及 232 passed、1 skipped 离线回归；全库 RC2 容器门仍未通过。新发布入口显式绑定这五题的已有原始证据，并另外冻结 62 题双镜像和版本记录；镜像初始化不是新的题目验收，不将 `full_bank_container_validated` 改为 true，也不追加 smoke 或模型校准。详见 [公开证据摘要](analysis/v2/release-20261028/PUBLIC-EVIDENCE.md) 与 [本次发布说明](analysis/v2/release-20261028/RELEASE-NOTES.md)。该摘要是去标识投影，列出原件哈希与覆盖范围，不是原始报告、完整轨迹或 validator 替代输入。

初始阶段配置是 8 个原配置 × 62 题 × 1 次重复，最多 496 个任务尝试、US$40、4 workers、整槽 infra 重试 0 次。后续费用上限已撤销；唯一 HTTP 429 重试例外的条件与记录见本页顶部的修订说明。任务尝试不是 HTTP 请求；多轮交互与客户端调用级重试会产生更多请求。模型路由故障可能导致缺槽。当前已验收的 7 个完整配置结果见[首轮结果](analysis/v2/release-20261028/RESULTS-PARTIAL-20261029.md)，原计划 8 配置未全部完成。

历史 RC1 `full124` 的 124/124 无模型门和 mc4 的 62/62 单模型工程证据仍保留，但不转移为 RC2 验收或新榜。版本边界见 [公开证据摘要](analysis/v2/release-20261028/PUBLIC-EVIDENCE.md)。所有旧实验 STOP 保持不变，不使用云沙箱，不沿用旧运行授权或费用封套。

## 轻量 harness

入口：`agents.compact_shell_v2:CompactShellV2Agent`。旧 `CompactShellAgent` 和旧 parser 不改写。

- 只提供 bash 与 finish，保持线性对话；没有规划器、多 Agent、自动改答案、自动重试模型失败或隐藏测试反馈。
- 运行约定与题面放在首条 **user 消息**，不是 system role。各模型路由与实际请求配置独立冻结，不声称具有完全相同的供应商实现。
- 每轮独立 `bash -c`，cwd 为 `/app`。`cd` 和 `export` 不跨轮保存；需要时写在同一动作内。文件系统修改跨轮保存。
- 每条回复只能有一个完整动作。bash＋finish、多动作、无效包裹均拒绝解析；不再让 finish 静默抢占 bash。bash 命令字符串中的 inline finish 文本不是停止指令。
- 默认 20 轮、单命令 60 秒、观察长度 8,000 字符。观察采用确定性的头＋尾截断并记录原长度；完整完成的 stdout／stderr 另行归档。实际值必须写入模型配置，不能只在介绍中声明。
- 记录 API／命令尝试、耗时、解析失败和终止原因。API 失败不能因为尝试过一次就算成完成了一轮。
- 主动 finish、轮数耗尽、命令超时、取消、API 错误分别保存。超时／归档失败不会自动改成模型成功或覆盖原始异常。
- 明确的单回复输出上限与上下文上限分别记 `output_limit`／`context_limit`；截断文本单独归档，绝不解析执行。已有产物照常采集、判卷，Clean 不成功。与 `max_turns` 一并归为预算耗尽，不是平台故障，不追加模型重试；未拿到的截断请求账单保持未知费用预留。

总时限默认来自每题 task.toml，包含 API 等待。单路由校准不证明预算对所有模型充分；本轮保持题目时限和原请求配置，不追加预算诊断或校准，不按每个模型的正式得分临时加时。

历史 RC1 `run_v2.py --diagnostic-file` 支持不超过 16 槽、单次重复的工程预算诊断，按其冻结条件覆盖 agent 总时限／轮数；通过 Harbor agent override 设置，不修改 task.toml、镜像或 verifier 时限，仍绑定其 RC1 全库 124 槽预检，始终无正式 leaderboard。该诊断接口不是新 release CLI 的模式。本次所有模型执行同一 62 题，没有按旧 Base-47 分数决定是否执行 Hard-15 的门。

## 提交与产物

| 技能 | 主提交 | 额外观察 |
|---|---|---|
| Loc | `/app/answer.txt` | repo 不得被改写 |
| Edit | `/app/repo` | 公开行为与隐藏回归 |
| Testgen | `/app/repo/tests` | 应用源码保持不变 |
| Repro | `/app/repro.py` | repo 保持不变 |
| Review | `/app/review.json`，schema 2 | repo 保持不变，候选为任务内诊断 |

终止后执行一次有界采集，归档 repo 上下文和明确的根目录提交文件。manifest 包含路径、大小、哈希、缺失与排除原因；不追踪 symlink，不收集任意 `/app` 内容，敏感文件名会排除并记录。文件名规则不是任意 secret 内容识别器，因此不得向模型运行容器注入 API 密钥。

`compact-shell-v2.json`、`agent/artifacts/manifest.json` 和实际文件可用于复核。采集明确标为 `atomic=false`、`final_state_verified=false`；它不是原子快照。Harbor 另按 task.toml 白名单采集交付物，传给新的 verifier 容器。分析器比对两侧收到的字节，发现不一致不会选择较好版本或自动宣布通过。

## 独立判卷与结构化证据

62 题均声明 `verifier.environment_mode="separate"`；agent 与 verifier 阶段禁网。verifier 从各题 `tests/Dockerfile` 构建，只接收声明的产物／观察 repo。隐藏测试属于 verifier 镜像，不进入 agent 镜像；镜像中去除了测试文件的普通写权限，判卷有独立 CPU、内存和总时限约束。文件模式不是 root 权限下不可篡改的证明。

本地 Docker 在内核不支持 nftables 动态禁网时，仅对 Linux、无额外／自定义 Compose、全部阶段保持 `no-network` 的任务使用静态 `network_mode: none`。启动后须由 Docker inspect 核验实际 NetworkMode，并保存与 trial、角色、实际双镜像绑定的主机侧证据；该兼容不支持 allowlist 或动态网络切换。

独立容器改善执行隔离，不是任意恶意 Python／pytest 的完整防篡改安全证明。可信控制器、源码检查、环境白名单和私有重放各有边界，不能把它们描述成形式化安全保证。

每题 test.sh 调用相同版本的 `verdict_v2.py`。控制器在有界 worker 中执行可信 test_state，保存：

- task／grader 版本、收到的产物 manifest 与摘要；
- `status=pass|fail|error`；`artifact_correct=1|0|null`；
- 失败类别、执行检查、候选细分证据、耗时及运行时版本；
- 受限的 worker 输出和资源上限。

通过写 reward=1；模型提交失败写 reward=0；可信判卷器 error 不写数值 reward，不能冒充模型零分。控制器清除自己上次遗留的 reward，防止错误执行继承旧分数。

用户非法 JSON、缺少提交、错误复现和测试导入失败仍是 **模型失败**。可信测试无法收集、判卷器内部异常或不完整结果是 **判卷错误**。整 worker 超时保守保留错误状态，不能在缺少证据时强行归因。

Testgen／Repro 的正确与错误实现重放、Review 的候选行为证据，成功时也保存。Review 的 40 个候选嵌套在 10 个任务中，不当作 40 个独立题计算主榜。

## 容器证据与环境冻结

历史 RC1 的 `scripts/validate_v2_containers.py` 默认只输出离线计划；`--check-runtime` 只读检查 Docker，不启动 Docker Desktop，不改用云后端。它不接入本次 RC2 题根。

旧入口显式 `--execute --directory experiments/smallowbench-v2/<新ID>` 才构建本地镜像并运行真实 Harbor oracle／nop；其全库门必须精确覆盖 62×2 项，不能用部分报告替代。RC2 已有独立的固定五题报告，只表示这五题链路的验收，不能宣称全库门通过。本轮不再执行新的 oracle/nop。

本次 `scripts/build_release_v2_images.py` 默认仅打印只读计划，显式 `--execute` 才在新的短目录中初始化镜像；它保留五题原绑定，准备其余题目的 agent／grader 镜像，检查 Python／pytest 依赖版本和精确探针的清理状态。允许构建网络必须显式给出 `--allow-build-network`；运行角色和版本探针禁网。该步骤的 `task_evaluation_runs=0`、`model_calls=0`，不会将镜像构建或版本探针冒充题目验收。

Dockerfile 中的 Ubuntu tag／apt 源不是不可变依赖锁。容器门记录每题 agent 与 grader 的实际 content-addressed image ID，以及两侧 Python／pytest 版本。新的实验任务副本使用这些固定 ID，不在测评时凭浮动 tag 重建。复制出的 staged task 哈希单独冻结，不修改原题或旧锁。

原始配置、结果、verdict、reward 与产物文件都绑定哈希。新任务改变后，旧预检不能复用。normalized task hash 和 legacy raw-tree hash 分列，不能混填。

真实容器证据还必须检查 Harbor 的传输行为和有效权限。例如 Windows 后端的目录上传可能规范化脚本换行，必须由两侧实际字节一致性检查发现，不能忽略差异或拿本地副本回放代替。五题报告的传输核对不能外推到未执行题目；正式运行继续逐槽核对产物字节与实际双镜像，未验收的范围如实披露。

## 新实验与执行安全

新目录只能为 `experiments/smallowbench-v2/<id>`，不能续跑旧 2,976 槽矩阵。模型名单、路由、请求参数、重复次数、预算和有限 infra 重试策略必须显式提供。

`run_release_v2.py prepare`、`lock`、`plan` 默认只读；加 `--write` 才写新文件。prepare 同时绑定 RC2 五题原始报告与 62 题镜像 runtime 记录，生成独立 manifest 和 STOP；lock 冻结执行身份，plan 生成本次 staged tasks 与配置。锁定与生成 job 配置都不是模型执行授权，不移除 STOP。旧 `run_v2.py` 保留历史能力，不接管新发布运行。

模型执行还要求独立的 `authorization.json`，其 `approved_by_user=true` 明确绑定 manifest、execution lock 和正数预算。本轮用户已同意上述 8×62×1、US$40 范围，由授权操作者将批准内容绑定到新运行并处理新 STOP；这个批准不解除任何旧实验 STOP，也不授权改变模型、路由、精度、题目时限或追加模型校准。文档命令本身不创建授权或证明模型已经执行。

事务 ClaimStore 控制槽位与模型内串行；worker 分配不拆分同一模型。只有原始证据确认的 infra 可按冻结上限重试，任务／协议失败不重试。费用未知保留预留，不假定 $0；过期心跳、无输出、异常抛出都不是免费或进程已停止的证明。预算是入场控制，不是供应商账单的强制封顶。

新实验可在 `prepare --isolate-model-infra` 显式冻结 `model_infra_policy=pause_model_continue_others`。确认的供应商连接／路由／限流／服务故障会生成绑定 manifest、execution lock、原始结果与 trace 哈希的持久 `model-holds/` 记录；暂停该模型、跳过其后续槽位，其他模型可继续。重启不会自动清除 hold，也不会自动重试或换供应商。认证、权限、账户余额故障（包括 HTTP 401/402/403）、全局预算不足、源码漂移、可信判卷／传输故障仍全局 STOP。模型答错、格式不合规、超时及预算耗尽不借此增加尝试。缺失槽位保持缺失，不能生成完整正式榜；旧 manifest 未声明该策略时不追溯改变行为。

整槽重试与 HTTP 客户端内部重试分开披露：当前 job 配置 `max_retries=0` 只禁止 Harbor 整槽重跑；已安装 Harbor 的 LiteLLM 适配器仍有最多三次的调用级重试。不能把一次 harness API call 计数描述成必然只有一次 HTTP POST。费用记录仅覆盖拿到的响应，丢失／失败请求继续保留预算预留。本次主机侧 `route_probe_v2.py` 使用独立的单次 HTTP 请求实现，零自动重试，不代表已经改写正式 harness 的重试语义。

STOP 排空当前任务后停止新入场。异常后的 running／unknown 需要进程和沙箱清理的正向证据，不按年龄抢占或重跑。

启动前按实际解析后的完整运行路径、Harbor job／trial 名、重复的禁网证据文件名及原子写临时后缀校验 Windows 路径预算。目录名长度不是跨机器保证；尚未产生的模型自建深层路径和宿主 TEMP 仍有边界，不能据此宣称任意文件名均可运行。

## 路由健康检查的边界

`scripts/v2_routes.py` 仅查询官方公开目录，不调用模型。候选必须保持原模型身份与广告精度，采用精确端点 `order`＋`only`、禁用 fallback，并要求支持声明的请求参数。原厂托管的未知精度如实标注未知，不把它写成 BF16。供应商变更是新配置，不能混合为原路由的配对结果；无端点不替换成后继模型，也不记模型零分。

`scripts/route_probe_v2.py` 的有界请求仅测试短请求可用性、响应身份与参数兼容性，不执行模型生成的命令、不运行题目、不产生成绩。每候选最多三次独立短请求、每模型最多两个同精度候选；格式不合规是单独的模型行为观察，不能据此挑换供应商。关闭推理声明若仍返回推理内容或正数推理 token，该配置不放行；隐藏推理输出不等于关闭推理。三次通过不证明长期容量、长上下文、长任务或所有参数均被服务端实际执行。

探针准备、用户授权、请求前预算预留、原始收据和结束 STOP 分开保存。后续参数修复必须承接已结束父轮的累计支出与未知预留，不得换目录重复分配同一授权残余。探活通过的配置只是下一次显式冻结的输入，不是正式矩阵授权，也不解除任何旧 STOP。

## 评分

主统计单位是 62 个任务。分别报告：

1. Artifact：隐藏 verifier 验证产物正确。
2. Clean：Artifact 正确且协议正常结束。

Clean 不命名为真实软件开发 E2E 成功。五技能分别报告；技能内题等权、五技能等权 macro，同时给 62 题 task-micro。不以旧经验难度权重、五技能通过率相乘或旧 IRT 解释新版。

本次 release CLI 的重复次数固定为 1，8 个模型各面对完整 62 题；历史 RC1 支持的 3 次重复不自动沿用。单次重复不能估计模型内重复运行的方差。每个模型必须完成完整计划才能有正式排名；infra／缺失不填零，不完整数据只给明确标注的部分结果。重复评分、版本错配、配置漂移、产物哈希不符和未解决 claim 会阻止正式榜单。

分析器从原始 Harbor 结果、v2 trace、verdict 与产物重算，不信任账本缓存成功标记，也不覆写历史结果。

## 入口

先按 [Harbor 固定依赖说明](vendor/harbor-patches/README.md) 安装相邻 Harbor checkout：upstream `https://github.com/harbor-framework/harbor`，base `f03db62fd2ed2ed1f79aefe024cfcbc68a0d759e`，应用发布的 runtime patch，再用该 base 的完整 `uv.lock` 执行 `uv sync --locked`。从本仓库根目录使用该环境中的 Python 和本地 Linux Docker。

首次外部克隆若没有本机原始五题证据，可先初始化自己机器的 `r2smk`（目录必须尚不存在）：

跨宿主平台复现限制：旧 `validate_upgraded_tasks.task_digest` 使用 `sorted(Path.rglob(...))`，Windows 与 Linux 的 `Path` 大小写排序规则不同。冻结文件字节及逐文件 SHA-256 清单可复核，旧目录聚合摘要尚未确认跨平台一致；Linux 宿主不保证直接通过原聚合摘要检查。本轮 Windows 同平台运行不变，不修改冻结函数或值，不新增测试阶段。

```powershell
python scripts/validate_rc2_containers.py --directory experiments/smallowbench-v2/r2smk --execute --allow-build-network
```

这在复现者本机生成 profile、五题 10 个 oracle/nop 槽及原始传输收据，无模型调用；构建联网、执行禁网。它不复用发布者绝对路径，不把公开脱敏摘要当原始 validator 输入。**本轮正式运行已拥有原始五题证据，不再执行这个初始化选项，也不增加正式跑前 smoke 或校准。**

随后使用以下新入口。路径是本轮示例；新运行与镜像初始化均须使用尚不存在的短目录，不能覆盖已有证据。读取状态与分析不会调用模型。

```powershell
python scripts/build_release_v2_images.py --output experiments/smallowbench-v2/im2 --execute --workers 4 --allow-build-network
python scripts/run_release_v2.py prepare --directory experiments/smallowbench-v2/rel2 --models-file analysis/v2/models.route-ready.json --preflight experiments/smallowbench-v2/r2smk/preflight-rc2.json --runtime experiments/smallowbench-v2/im2/runtime.json --budget-usd 40 --workers 4 --max-infra-retries 0 --visit-reserve-usd 3.5 --repetitions 1 --isolate-model-infra --write
python scripts/run_release_v2.py lock --directory experiments/smallowbench-v2/rel2 --write
python scripts/run_release_v2.py plan --directory experiments/smallowbench-v2/rel2 --write
python scripts/run_release_v2.py status --directory experiments/smallowbench-v2/rel2
python scripts/run_release_v2.py analyze --directory experiments/smallowbench-v2/rel2
```

独立授权与新 STOP 处理完成后，执行命令为：

```powershell
python scripts/run_release_v2.py execute --directory experiments/smallowbench-v2/rel2 --execute --worker 0 --workers 4
```

该命令只执行 worker 0；四 worker 调度分别以 `--worker 0`、`1`、`2`、`3` 启动独立进程，全部保持 `--workers 4`。省略 `--execute` 只打印执行计划。源码、配置、预算或证据身份不符时停止，不自动更换模型或重建历史验收。

本机生成的五题报告及其完整依赖、运行时原始绑定是这些命令的输入；仓库公开的去标识摘要不能替代完整本地证据，新安装也不证明与发布运行字节一致。发布包依赖和证据可获得范围见 [发布清单](analysis/v2/release-20261028/PUBLICATION-CHECKLIST.md)。旧实验的复算继续使用其原版本入口，不能拿旧 CLI 配合 RC2 目录绕过版本核对。
