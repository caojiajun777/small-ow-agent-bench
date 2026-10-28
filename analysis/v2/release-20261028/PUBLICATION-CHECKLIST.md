# SmallOWBench 2.0 — publication checklist and package allowlist

日期：2026-10-28。此清单是本地发布准备草案，记录源码发布、结果发布与私密原始运行材料的边界。本文件不执行 commit、push、远端 Release、Docker 或模型请求，也不要求追加 smoke 或校准。最终发布负责人逐项记录事实，不以改写旧版本号或历史证据的方式勾选。

## 当前已经核实

- [x] 读取中英文 README、`STANDARD-v2.md`、`analysis/v2/STATUS.md` 及 `rc2-pipeline-20261027/REPORT.md`。
- [x] 确认 62 题分布为 Loc 11、Edit 15、Testgen 13、Repro 13、Review 10；均为人工设计、已经开发过的小型 Python 工作流。
- [x] 确认候选 task／grader `2.0.0-rc.2`，harness `2.0.0-rc.1`；根 `VERSION` 和原 manifest 仍属于受保护 RC1 来源。
- [x] 现有 RC2 容器证据只覆盖固定五题 oracle/nop 共 10 槽，5 pass／5 fail 均符合预期；离线回归 232 passed、1 skipped。
- [x] 没有把 RC1 `full124`、旧 v1.x 榜单、mc4 或 sm8 的工程结果改称本轮正式成绩。
- [x] 根目录有 `LICENSE` 和 `CITATION.cff`；已检查公开引用链接与 Harbor 依赖声明，没有读取 `.env`、私钥或凭据内容。
- [x] 中英文 README、`STANDARD-v2.md`、发布说明和 `CITATION.cff` 已更新为独立 RC2 发布入口与分组件版本；旧榜全部保留并标明历史范围，根 `VERSION`／旧题库／旧锁未改。
- [x] 新镜像初始化和 release CLI 参数已按实际 argparse 源码核对；文档记录用户已同意 8×62×1、最多 496 个任务尝试、US$40，而不是 496 个 HTTP 请求。
- [x] 新克隆的公开复现选项已写明：先按固定 Harbor 来源／补丁安装依赖，在复现者机器运行现有五题初始化入口生成本机 profile／原始证据，再 build images → prepare。已明确本轮正式运行不重复该初始化，也不把脱敏摘要当 validator 原始输入。

## 发布文字、版本和结果

- [ ] 冻结独立发布标识、release manifest 路径和来源 commit；列出 benchmark／task／harness／grader 的实际版本及哈希。
- [x] 中英文首页明确默认新题根与新入口；旧榜单和旧命令进入清楚标注的历史范围，不让读者把原 `tasks` 当成本轮默认题库。
- [x] 本次软件引用元数据已改为 `2.0.0-rc.2`，同时标明 harness `2.0.0-rc.1`、RC2 五题容器证据与全库覆盖限制；未虚构论文或 DOI。
- [x] 实际新 release CLI 的准备／冻结／运行／分析命令已补入发布说明；新运行的独立授权和初始 STOP 与命令调用分开说明。
- [ ] 新模型分数从本轮版本一致的原始证据重算。正式结果尚未产生时保留“待本轮运行”，不用旧数据或空表造新榜。
- [ ] 报告 Artifact／Clean、五技能 macro／62 题 micro、重复次数、缺失、infra、grader error、结束原因和预算口径。Review 的候选数不扩充任务样本量。
- [ ] 若完整矩阵仍缺路由或槽位，公开明确标注的部分结果及缺失原因，保持 `formal_ranking_eligible=false`，不把不可用模型记零，不声称完成全模型榜单。
- [ ] 若本轮未取得新的 RC2 全库容器门，原有全库验收状态仍如实为 false；源码发布说明可以披露这个限制，不能借用 RC1 门或将五题诊断改名为全库通过。

## 许可证、引用和依赖

- [x] 根 `LICENSE` 已补齐官方完整 Apache-2.0 条款；`NOTICE` 保留 `Copyright 2026 junjun cao` 及外部依赖说明。
- [x] 软件作者、来源仓库和引用信息已保留；`vendor/harbor-patches/HARBOR-LICENSE` 携带上游许可证，补丁 README 与根 NOTICE 说明来源和修改。没有把本项目许可证表述为模型权重或供应商服务的统一授权。
- [x] Harbor 固定来源已写明为 `https://github.com/harbor-framework/harbor`，base `f03db62fd2ed2ed1f79aefe024cfcbc68a0d759e`（0.21.0、Python >=3.12）；runtime patch 为 `vendor/harbor-patches/0001-smallowbench-runtime.patch`，检查时 SHA-256 为 `4821be411bea9c6c0511b6bcab99471b0c3882a1cddbc7cc08a89faddbd81b63`。最终包清单仍须逐文件复核哈希。
- [x] 提供了可获取的固定 upstream base（含完整 `pyproject.toml`／未修改的 `uv.lock`）、可分发补丁与 `uv sync --locked` 安装说明。RC2 runtime 继续记录实际源树摘要、依赖文件哈希及已安装分发包版本，新安装生成本机身份记录，不假装与原主机字节一致。
- [ ] 记录已执行任务的 agent／grader 实际镜像 ID、构建输入、Python／pytest 版本。浮动 Ubuntu tag、apt 源和本机镜像缓存不能当作不可变依赖锁。
- [ ] 不分发 `.venv`、Docker 导出镜像或宿主缓存来代替依赖声明。源码发布包应保持体积可审查。

## 发布包 allowlist 草案

这是路径选择规则，不是“打包整个仓库”的命令。生成最终包前将每一项展开为普通文件清单，写入相对路径、字节数和 SHA-256；拒绝 symlink／junction／reparse 路径。下面尚未冻结的新文件按最终实际存在的名称列入，不使用通配符暗中扩大范围。

| 允许内容 | 范围与理由 |
|---|---|
| 公共入口文档 | `README.md`、`README_EN.md`、修正后的 `CITATION.cff`、完整 `LICENSE`、需要的 NOTICE、`.gitattributes` |
| Harbor 固定依赖材料 | `vendor/harbor-patches/README.md`、`HARBOR-LICENSE`、`0001-smallowbench-runtime.patch`；上游完整源码与锁文件通过所指定 base 获取，不复制本机 `.venv` |
| 本次发布元数据 | 本目录的最终发布说明、清单、去标识的 release manifest、包内文件哈希与安全的依赖／补丁声明 |
| 新题库 | `task-banks/rc2/VERSION`、`task-banks/rc2/task-bank-v2.manifest.json`，以及 manifest 精确列出的 62 个 `task-banks/rc2/tasks/<id>/` 普通文件 |
| 候选来源依赖 | 受保护的原 `VERSION`、`task-bank-v2.manifest.json`、原 62 个 `tasks/<id>/` 及候选 `protected_source_hashes` 指定的源码；当前 `validate_candidate` 必须核对这些文件，不能只发 RC2 子目录 |
| 执行、分析与交付工具 | 最终新 release CLI、其传递依赖闭包、`agents` 中所依赖模块，以及对应必要回归测试；逐文件列明，不盲纳入整个 `scripts/` 或临时脚本 |
| 技术规范 | 本次说明明确引用且已检查版本范围的 `STANDARD-v2.md`、任务／接口说明；不靠改写历史标准冒充新协议 |
| 可公开验证摘要 | 单独生成并审查的证据摘要：验收范围、统计、组件／文件摘要、匿名化 trial 标识、去标识镜像绑定；原始本机报告默认不在包内 |

题目中的 `solution`、隐藏 `tests` 和 baseline 是可公开的基准维护材料，但应保留原始层级，Agent 运行只接收公开 environment 和题面。不得为减少包内容而误删新执行器必需的隐藏 grader，也不得把这些文件注入 Agent 工作区。

如果发布形式是 GitHub 源码仓库而不是独立 zip，同样必须对**实际将提交或推送的文件列表**进行检查；`.gitignore` 不是秘密检测器，之前已经跟踪的文件也不会因此自动移除。本草案没有生成压缩包。

本次保留已有公开历史材料；其中 14 份旧 `jobs` JSON 在新提交中采用去标识历史投影，只将 Windows 用户 home 前缀换为 `<HISTORICAL_USER_HOME>/`，其余字段与数值保留。投影不能代替原始配置或旧原件哈希；原始版本见 [历史提交 `fa5a1d5527d945f64053dd75c48bd9553febffc4`](https://github.com/caojiajun777/small-ow-agent-bench/tree/fa5a1d5527d945f64053dd75c48bd9553febffc4)，该版本含历史宿主目录。旧公开分数与 `results` 保留，操作仅针对独立发布 Git index 的公开 blob，本机原件与日常 index 不改。

## 默认排除的本地材料

| 排除对象 | 处理方式 |
|---|---|
| `.env`、`.env.*`、API key、Bearer／Authorization、cookie、私钥、凭据配置 | 不读取和复制；如需提供配置样例，由已知 schema 重新写只有占位符的公开样例，不复制现有环境文件 |
| 环境变量快照、解析后含凭据的模型配置、密钥路径 | 不进入代码提交、Release 附件、数据集或日志；脱敏检查不能只搜文件名 |
| 原始逐轮请求／响应、HTTP headers、供应商 receipt、命令完整输出、trace | 默认保留本地；只有经过内容审查且单独去标识的派生摘要可发布，不覆盖原件 |
| Docker inspect 原始输出、主机库存／信息、全部镜像／容器列表、挂载点、context、socket／宿主探针收据 | 默认不公开；摘要仅保留复现所需的镜像内容摘要、角色、版本和验收事实 |
| 绝对用户目录、Windows 用户名、设备名、主机名、IP、TEMP、磁盘／挂载路径 | 发布投影改用仓库相对路径或稳定占位符；原始证据不原地替换，分别记录原件哈希与投影哈希 |
| `experiments/`、`jobs/`、`trials/`、`artifacts/`、`archives/`、`results/` 中的本地运行产物 | 不整目录加入；确有必要的公开历史材料和安全摘要另按精确白名单选取，并注明版本 |
| `.venv/`、其他虚拟环境、wheel/cache、`node_modules/`、大镜像／镜像 tar、模型权重 | 排除；使用固定依赖和获取方式，不打包宿主运行时 |
| `.git/`、pytest／Ruff／Python 缓存、dot scratch 目录、临时测试副本、安装与恢复日志 | 排除；发布源码包不携带本地历史数据库和可重建临时文件 |
| 旧运行授权、STOP、预算账本、未结算费用与 hold 原件 | 保留本地且不改写，不将它们复制成读者的启动授权；需要披露时提供数值与状态摘要 |

发布投影不能声称与原件逐字相同。保留原始证据的哈希及其受限本地位置索引，公开投影另算哈希；发布数据缺少原件时应说明其可复核范围，不把摘要包装成完整原始轨迹。

## 最后一次静态发布检查

- [ ] 检查实际新增／修改文件列表、包清单与附件清单，没有 `.env`、密钥、绝对用户路径、原始请求日志、Docker 主机库存或超大文件。
- [ ] 检查链接目标与每个命令的参数来自实际新接口；文档缺省值与冻结配置一致。
- [ ] 检查包内候选 manifest、来源依赖和新源码哈希相符；打包没有换行改写或遗漏必要文件。这个静态一致性检查不追加 smoke、校准或模型请求。
- [ ] 记录包／安全附件的 SHA-256 与发布来源 commit，发布 notes、引用元数据、结果页和模型缺失说明一致。
- [ ] 将最终待发布文件和远端目标交给统一发布者处理；本清单作者没有执行远端发布，不能把本地草案状态写成已上线。
