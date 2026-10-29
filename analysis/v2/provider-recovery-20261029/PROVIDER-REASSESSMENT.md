# Fixed-provider reassessment of Qwen3.5-9B

Selection recorded on 2026-10-29, before the first reassessment inference.

The original OpenRouter `parasail/bf16` configuration encountered two recorded
HTTP 429 infrastructure failures. The provider reported an upstream shared-pool
limit. Its 29 valid task observations remain a partial configuration; no missing
task receives a zero, and the original eight-profile experiment remains
incomplete. Changing the API key is not evidence that this provider pool has
recovered.

The independently named `qwen3.5-9b-primeintellect-bf16` configuration uses
OpenRouter model `qwen/qwen3.5-9b` with `primeintellect/bf16` pinned in both
`provider.order` and `provider.only`. These and the descriptive `route` field
are the only model-configuration changes. Provider fallback stays disabled.
The original temperature, top-p, output limit, disabled-reasoning request,
turn limit, timeout, prompts, task bank, runtime images and grading contract
are retained. The saved public endpoint response declares BF16 and support
for the standardized request parameters; endpoint metadata is not proof of
successful inference or capacity for the complete run.

All 62 tasks are reassessed once, serially, under the new configuration.
Completed model or protocol failures, timeouts, and output/context exhaustion
are final observations. Only evidence-confirmed transient provider or transport
infrastructure failures may retry: at most three attempts per task, with
120-second and 300-second cooldowns, extended by a longer saved Retry-After.
Permanent configuration/authentication faults, exhausted infrastructure retries,
unresolved execution ownership, and invalid scoring evidence hold execution.
There is no automatic provider change. All attempts and unknown charge reserves
remain recorded; monetary admission caps have been waived by the user.

Every actual scored trial must pass the existing configuration, trace, verdict,
capture, isolated-grader and artifact checks before the next task starts. The
new authorization binds this independent configuration without fabricating a
legacy dollar limit. Saved request receipts are checked for parameter changes;
full callback logs remain private because they can contain credentials.

The following source selection is fixed before reassessment results exist:

| Profile | Required source |
| --- | --- |
| `llama-3.2-3b-instruct` | Original experiment, all 62 validated tasks |
| `gemma-3-12b-it` | Original experiment, all 62 validated tasks |
| `ministral-3b-2512` | Original experiment, all 62 validated tasks |
| `ministral-8b-2512` | Original experiment, all 62 validated tasks |
| `ministral-14b-2512` | Original experiment, all 62 validated tasks |
| `qwen3.8-27b` | Original experiment, all 62 validated tasks |
| `qwen3.6-35b-a3b` | Original experiment, all 62 validated tasks |
| `qwen3.5-9b-primeintellect-bf16` | Independent reassessment, all 62 validated tasks |

A superseding eight-profile roster may be accepted only after fresh validation
of all 496 unique observations. It combines seven complete configurations with
one complete new configuration; it does not combine the 29 old-provider scores
with new-provider scores or change the original experiment's acceptance flag.
The earlier partial results remain available as dated artifacts.

This is a single-repetition evaluation of authored Python workflows. Artifact
correctness and successful protocol completion are separate endpoints. It does
not establish real-repository long-horizon performance, score independence from
provider latency, or a hardware-specific local-deployment ranking.

Public selection evidence: [route findings](PUBLIC-ROUTE-FINDINGS-20261029.md),
[configuration decision](models.qwen35-primeintellect-bf16.json), and
[OpenRouter's endpoint catalog](https://openrouter.ai/api/v1/models/qwen/qwen3.5-9b/endpoints).
