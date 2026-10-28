# 2026-10-29 execution amendment: no monetary admission cap

The ongoing SmallOWBench 2.0 RC2 release run resumed on 2026-10-29 at
00:22:34 (UTC+08:00), following the user's explicit instruction to remove model
spending budgets from execution decisions. Fees are recorded, including unknown
fees, but their dollar amounts no longer stop task admissions.

The initial phase had 120 scored tasks when conservative unknown-cost
reservations triggered the original monetary admission gate. Those attempts and
their raw artifacts are retained. The continuation runs the remaining 376 slots
of the **same eight OpenRouter configurations × 62 tasks × one attempt**.
Already scored tasks are not retried. The total limit remains 496 task attempts,
one per slot, with four workers and model-local serialization.

## What changes

The additive continuation executor passes `budget_usd=None` to the transactional
claim store. It requires a separate, user-approved `fee-waiver.json` binding the
original manifest, execution lock and authorization; the exact three
continuation implementation files; and the original 120 scored visit-file
hashes. It rechecks this amendment at startup, before admission and before
launch. The original US$40 configuration remains an intact record of the
initial phase and is superseded only for monetary admission decisions.

No task, grader, prompt, provider pin, model precision, scoring rule, token
limit, turn limit, task timeout or model retry policy changes. Infrastructure
and account failures retain their existing handling. The old US$4 experiments,
their STOP files and unknown fee records are untouched. Unknown charges are not
rewritten as zero.

## Implementation and reporting

- `scripts/resume_release_v2.py` is the explicit continuation entry point.
- `scripts/release_v2_fee_waiver_executor.py` implements the amended admission.
- `scripts/analyze_release_v2_fee_waiver.py` wraps the frozen scorer, verifies
  initial and continuation provenance, and adds `actual_execution_policy` and
  phase counts to the report. It cannot make an incomplete run eligible for a
  full ranking.
- Thirty offline contracts passed, including provenance on pre-launch aborts,
  unchanged attempt caps, and rejection of unbound continuation evidence. No
  model calibration or reference/empty-submission run was added.

Amendment file SHA-256:
`3fd74d4b5c79f0291c3e4c07feb6e245131804967471ddc116bf5d984decdd7e`.
The authorization and complete initial-phase snapshot stay local; this public
note is not a replacement execution authorization.

Final scores are still pending completion and raw-artifact acceptance. A final
report must disclose this operational amendment and the pause rather than
describe the entire run as having an active US$40 cap. The existing RC2 tag and
source archive identify the initial source release; this dated amendment is an
additive update on the repository's main branch.
