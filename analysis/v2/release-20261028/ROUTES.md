# 2026-10-28 正式发布候选：8 配置公共目录核对

结论：`analysis/v2/models.route-ready.json` 的 **8/8 原配置目前均有精确匹配的目录端点**，`status=0`，已配置的已知精度及必需参数没有目录级冲突。**这不是额外探活、模型校准或服务稳定性认证。** 本次仅执行 8 次未携带 API key 的公开 GET，0 次生成 POST、0 次付费模型调用、0 次自动重试；未读取 `.env` 或密钥，未更换模型、供应商、精度或修改旧配置。

取数时间：2026-10-28 13:17:16 UTC（北京时间 21:17:16）。源配置 SHA256：`f77f510c4991f5033f3d9587d508554d414acbb3fff92715f8e6d9a23f5e0969`。

## 精确原路由与当前目录价

价格单位为 **USD / 100 万 token**。上下文与最大输出为该精确供应商端点的声明值，不采用所有供应商中最大的数值。

| 模型 | 原 route tag（保持不变） | 声明精度 | 输入价 | 输出价 | 缓存读取价 | 上下文 | 最大输出 |
|---|---|---|---:|---:|---:|---:|---:|
| Llama-3.2-3B-Instruct | `parasail/bf16` | bf16 | 0.05 | 0.33 | 未声明 | 131,072 | 117,964 |
| Ministral-3B-2512 | `mistral` | unknown | 0.10 | 0.10 | 0.01 | 131,072 | 104,857 |
| Ministral-8B-2512 | `mistral` | unknown | 0.15 | 0.15 | 0.015 | 262,144 | 209,715 |
| Qwen3.5-9B | `parasail/bf16` | bf16 | 0.10 | 0.25 | 未声明 | 262,144 | 235,929 |
| Gemma-3-12B-IT | `deepinfra/bf16` | bf16 | 0.05 | 0.15 | 未声明 | 131,072 | 16,384 |
| Ministral-14B-2512 | `mistral` | unknown | 0.20 | 0.20 | 0.02 | 262,144 | 209,715 |
| Qwen3.8-27B | `deepinfra/bf16` | bf16 | 0.15 | 1.875 | 0.0375 | 262,144 | 235,929 |
| Qwen3.6-35B-A3B | `venice/fp8` | fp8 | 0.10 | 1.00 | 未声明 | 256,000 | 65,536 |

所有端点都声明支持 `temperature`、`top_p`、`max_tokens`；三个 Qwen 端点另声明支持 `reasoning`。全部声明最大输出不低于当前配置的 8,192。`max_prompt_tokens` 均未单独声明，不能填成 0 或当作无限制；完整请求仍须满足各端点上下文总上限。

三个 Mistral 托管端点依旧保留在原供应商，目录精度为 `unknown`；**不能将其写成 BF16，也没有为它们添加 BF16 过滤器**。其他五个配置分别与原 `bf16`／`fp8` 过滤器匹配。原 `order`、`only` 和 `allow_fallbacks=false` 配置保持不变。

Qwen3.8-27B 的返回价中带有 `discount=0.25`，表内直接换算返回的 `prompt`／`completion` 单价，不再次乘折扣。缓存读取价缺失的项目写作“未声明”，不是免费。

## 证据与边界

- [route-catalog.json](route-catalog.json) 保存完整解析后的 GET JSON、接收时间、HTTP 状态、原响应字节 SHA256，以及精确端点核对结果。JSON 在此重新序列化，原响应字节 SHA256 不应拿来与重新序列化文本直接比较。
- 官方端点接口：[List all endpoints for a model](https://openrouter.ai/docs/api/api-reference/endpoints/list-endpoints)。实际公开 GET 地址按各模型填写在 JSON 的 `catalog_get.url` 中。
- 参数被目录列出，不等于供应商已验证遵守该参数；尤其不能将 `reasoning` 支持等同于 `reasoning.enabled=false` 已生效。配置中的 `enable_thinking` 扩展语义没有重新探测。
- 本次没有收集任何新模型输出、成绩或长期容量证据；没有将目录可用性写成模型能力通过，也没有给缺失结果填零。
- 此文件不是预算授权、正式实验锁或发布批准。用户要求不再额外探活／校准，本次只做公开元数据读取；正式运行由主执行流程独立授权和验收。

## 每模型官方证据地址

- [Llama-3.2-3B-Instruct](https://openrouter.ai/api/v1/models/meta-llama/llama-3.2-3b-instruct/endpoints)
- [Ministral-3B-2512](https://openrouter.ai/api/v1/models/mistralai/ministral-3b-2512/endpoints)
- [Ministral-8B-2512](https://openrouter.ai/api/v1/models/mistralai/ministral-8b-2512/endpoints)
- [Qwen3.5-9B](https://openrouter.ai/api/v1/models/qwen/qwen3.5-9b/endpoints)
- [Gemma-3-12B-IT](https://openrouter.ai/api/v1/models/google/gemma-3-12b-it/endpoints)
- [Ministral-14B-2512](https://openrouter.ai/api/v1/models/mistralai/ministral-14b-2512/endpoints)
- [Qwen3.8-27B](https://openrouter.ai/api/v1/models/qwen/qwen3.8-27b/endpoints)
- [Qwen3.6-35B-A3B](https://openrouter.ai/api/v1/models/qwen/qwen3.6-35b-a3b/endpoints)
