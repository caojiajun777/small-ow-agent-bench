# Cancellation audit amendment

During the independent PrimeIntellect BF16 reassessment, 49 tasks completed
before a request-audit defect held execution at `testgen-anagram`.

The task's raw result records `AgentTimeoutError`; its trace records cancellation,
its final artifact capture is complete, and the isolated grader reports
`fail`, `artifact_correct=0`, `invalid_submission`. Sixteen completed API
responses identify PrimeIntellect and preserve the frozen request parameters.
The seventeenth API call was cancelled at the task deadline. Its saved request
parameters are also unchanged, but it has no completed JSON response. The new
request audit incorrectly required such a response even for this pending call,
and consequently labelled the task as a configuration infrastructure failure.

The original task observation is a time-limit failure with score zero. A
supplementary, hash-bound correction admits that same execution without issuing
another model request. The original manifest, execution lock, authorization,
source files, ledger, visit exports and initial closure/report remain unchanged.
The erroneous infrastructure label stays available beside its correction.

The corrected request audit still checks the saved parameters of cancelled
requests and every completed response's provider. Only a pending call with
positive raw timeout/cancellation evidence is exempt from producing a completed
response. Missing or changed request parameters and a wrong completed provider
remain faults. Other artifact, verdict, capture, checksum, isolation and
authorization checks remain required.

The execution amendment continues only the twelve tasks that have never been
started, using the same p3 manifest, task bank, images, model, route, prompts,
output/turn/time limits and grading semantics. A separate continuation ledger
preserves the original ledger bytes. Additional source and amendment bindings
cover the continuation. The corrected timeout task and previously scored tasks
are never rerun. Ordinary model timeouts, protocol failures and wrong answers
remain final observations; the existing bounded transient-infrastructure retry
policy is unchanged.

Final acceptance still requires all 62 unique observations for the new provider
configuration, followed by fresh validation of the seven complete parent
profiles and the full new configuration. The old Parasail 29-task partial
configuration remains excluded from that independently accepted roster.
