# benchmark-v1.0.1

API Standard 最终结果表。tag 钉在冻结提交上；之后的 README / 目录提交只改呈现。

## Headline

- **Qwen3.5-9B** Artifact 宏平均 **0.786**（148/186）；Clean **0.757**（142/186）
- **Qwen3.8-27B** Artifact **0.863**（162/186）；Clean **0.845**（159/186）
- 12 配置 × 62 题 × 3 = **2,232** 次有效实验；`remaining_dirty` 0
- 做对但没停（Artifact=1，未 Clean）= **105**

12 个配置全部按 Artifact 宏平均进入同一张排名。Qwen3.6-35B-A3B 是约 3B 激活的 MoE，不是 27B dense 的下一档。

## 相对 v1.0 改了什么

`benchmark-v1.0` 是冻结审计快照：Hard-15 当时只跑官方 6 个受试，其余 6 个小型配置缺测记 0；Gemma-4B 含 67 格误记的限流失败。缺测记 0 会低估部分配置，例如 Gemma-3-12B 的 Artifact 微平均从 47/186 变为 60/186，Edit 从 0.47 变为 0.53。

v1.0.1 按 `(配置, 题, attempt)` 唯一键合并，每个键只留一条：

1. 冻结 Base（`locked-core-k3.json` + `locked-upper-base-k3.json`）
2. 官方 Hard-15（`locked-hard-release-k3.json`）
3. Hard 完整性补测（`locked-hard-floor-k3.json`）
4. Gemma-4B 67 格限流替换（`locked-gemma4b-rerun-k3.json`）
5. 另外 13 格平台故障替换（`locked-infra-rerun-k3.json`：429 / 断连 / 上游 401）

冻结锁没有改写。Gemma-4B 最终为 11/186。Headline 9B 从 0.774（146/186）变为 **0.786**（148/186），27B 从 0.858（161/186）变为 **0.863**（162/186）。13 格替换里 5 格 Artifact=1 且 Clean，没有新增「做对但没停」。

平台故障替换在后续时间窗口完成。模型路由、供应商顺序和推理参数保持冻结，但 API 后端的时间漂移无法完全排除。这不改变冻结协议，也不把结果改写成权重控制实验。

## 这张表衡量什么

冻结 compact-shell v0.1.1 + 钉死的 API 供应商 + Novita 沙箱下的端到端**系统**可靠性。不是脱离接口的 coding IQ，也不是已控制权重的 Local Reference。

## Links

- GitHub: https://github.com/caojiajun777/small-ow-agent-bench
- Hugging Face catalog: https://huggingface.co/datasets/junjun77/small-ow-agent-bench
- 方法：`项目说明.md`
- 完整数字：`结果报表.md`
- 协议：`STANDARD.md`
