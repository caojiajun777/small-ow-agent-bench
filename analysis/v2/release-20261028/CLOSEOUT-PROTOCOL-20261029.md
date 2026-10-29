# 2026-10-29 release-result closeout protocol

**Status after the continuation attempt:** its first unvisited task received a
new Parasail shared-upstream-pool HTTP429 after 12 completed API responses. The
frozen executor held the configuration again. There are now seven complete
62-task configurations, 29 valid Qwen3.5-9B observations, two retained infra
attempts and 31 unvisited slots. The separately approved original retry has not
executed because its closure prerequisites are unmet. The automatic supervisor
stopped without an extra request. See the [completed-configuration results](RESULTS-PARTIAL-20261029.md);
this is not a complete eight-configuration leaderboard.

The first execution ended with 463 scored attempts, one HTTP-429 infrastructure
attempt and 32 unvisited slots. The original analyzer admitted 461 observations
and rejected two Llama3.2-3B capture errors. This note records the bounded
closeout before claiming a complete official result set.

## Preserve and audit the two original negative observations

`testgen-booking-touch` and `testgen-anagram` were originally graded
`invalid_submission / 0`: XML files were written outside the permitted tests
scope. Their Agent captures remain `error` with `FileNotFoundError`; they are
not rewritten as successful or complete captures.

The independent grader transfer retains exactly 12 and 23 observed files.
`scripts/audit_v2_capture_supplement.py` verifies their complete observation
sets, roles, sizes and SHA-256, the scope-violation witness, original
trace/verdict/worker agreement, execution configuration, task checksums,
separate pinned images and dual network-none proofs. It admits only these two
named original fail/zero observations. It cannot admit a successful submission,
an unrelated capture error, or establish a complete final Agent capture.

`scripts/analyze_release_v2_supplement.py` rebuilds this audit from original
evidence. It resolves only the exact two capture-rejection issues and recomputes
coverage and scores with the original scoring functions. All other missing,
duplicate, unresolved or invalid observations continue to block a complete
ranking. Original reports, grades, visit records and failed captures remain.

## Continue only the 32 unvisited slots

The same `qwen3.5-9b` configuration uses `openrouter/qwen/qwen3.5-9b` pinned to
`parasail/bf16`, without fallback. The reviewed original 429 hold is archived
with a release receipt. The frozen fee-waiver executor resumes worker1: its
claim store skips every existing scored/infra slot and admits only the 32
previously unvisited tasks. There is no probe, calibration, model substitution
or answer-based retry. A new provider failure creates a new hold.

## Exactly one separately approved infrastructure retry

The user explicitly approved one additional attempt of
`qwen3.5-9b/repro-float-cents/r1`, whose original attempt encountered HTTP429.
The original counted infra record is preserved. `scripts/retry_v2_single_infra.py`
requires separate approval binding the proposal, exact implementation and
original run/lock/auth/fee-waiver hashes.

It may execute only after the 32 unvisited slots have closed: all other 495 slots
must be scored, with no active claims, STOP or provider hold. Only this slot may
have a second visit; the actual total-attempt limit becomes **497**, while the
unique scored task-slot target remains **496 at k=1**. The runner cannot retry an
already scored task, change the provider, or purchase a third visit. A repeated
429 is preserved and held rather than silently retried.

Final analysis verifies the additional visit's independent provenance and
reports this exception explicitly. It cannot infer authorization merely from a
second visit's self-reported marker. Source metadata, the original model, task,
prompt, token/turn/time limits, grading and canonical legal-observation rule
remain unchanged. Monetary admission limits remain waived.

## Acceptance and release

Seventy combined offline contracts and independent code reviews cover the
negative-evidence audit, exact-slot reporting and the single-retry controller.
No new model calibration or reference/empty-submission evaluation was added.

A complete leaderboard requires 496 unique accepted observations and no open
validation issues, duplicates or unresolved claims. The final result must
disclose all allowed attempts (at most 497), the retained infra record, the two limited
negative-evidence supplements and k=1. Until those conditions hold, results
remain partial. Raw request logs, local authorizations and host receipts are
not part of a public result projection.
