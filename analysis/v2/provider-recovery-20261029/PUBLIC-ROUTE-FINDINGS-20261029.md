# Public route findings: Qwen3.5-9B (2026-10-29)

Read-only public GET audit; no credentials, inference POST, old experiments or
existing route pins were used or changed.

The preferred same-model/same-precision candidate is `primeintellect/bf16` for
`qwen/qwen3.5-9b`. At the saved snapshot it declared BF16, status 0, 5-minute and
30-minute uptime 100%, context 262144, maximum completion 40960, and support for
`reasoning`, `temperature`, `top_p` and `max_tokens`. Thus 8192 requested output
tokens fit its declared limit. Model catalog metadata says
`reasoning.mandatory=false`. This is declared compatibility, not an inference
capacity test or proof of effective hidden reasoning behavior.

Keep temperature 0, top_p 1, max_tokens 8192, reasoning.enabled false and the
existing task-independent parameters. The endpoint pin is:

```json
{
  "order": ["primeintellect/bf16"],
  "only": ["primeintellect/bf16"],
  "allow_fallbacks": false,
  "require_parameters": true,
  "quantizations": ["bf16"]
}
```

The existing `enable_thinking=false` extra is not independently listed in the
endpoint's supported-parameter array. Preserve the declared original payload
unless an explicitly documented new-configuration adapter changes it; do not
silently drop parameters to make an endpoint appear compatible.

Other endpoints: DeepInfra BF16 is listed but its last-30-minute uptime was 0%
in the saved GET; a near-concurrent web fetch showed status -5 and about9.5%.
Parasail BF16 still advertises 100% uptime despite the user's repeated shared
upstream-pool429 failures. Catalog health is therefore insufficient evidence
for this account's long-session capacity. SiliconFlow FP8, Darkbloom FP4 and
Together unknown precision are not same-precision replacements.

The official routing guide documents full-slug targeting, parameter support
filtering, quantization filtering and disabling fallback. Keep fallback off for
a separately frozen provider configuration instead of mixing providers within
a scored run. The errors guide documents Retry-After and typed rate-limit or
provider-overload errors; respect supplied cooldowns and define any bounded
infrastructure-only recovery before execution. Legal model failures must not be
retried based on outcome.

Sources:

- https://openrouter.ai/api/v1/models/qwen/qwen3.5-9b/endpoints
- https://openrouter.ai/api/v1/models
- https://openrouter.ai/docs/guides/routing/provider-selection
- https://openrouter.ai/docs/guides/best-practices/reasoning-tokens
- https://openrouter.ai/docs/api_reference/errors-and-debugging

Saved evidence index:
`public-route-catalog-audit-20261029T054716Z.json`.
The exact raw endpoint response SHA-256 is
`e5508e402c1d7beb9110d3328dbc1f4a64e0d787a557fdbc63aa3b83c3e2e631`.
The model-selection JSON is explicitly a parsed subset with the original full
catalog response hash; it is not represented as the raw whole-catalog response.
