Review the four candidate patches for **member checkout with post-discount store credit** in `/app/repo`.

The user contract and runnable JSON CLI are documented in `README.md`. `base/` is the pre-change workspace. Each subdirectory in `candidates/` is the result of applying a different proposed patch independently. The actual API entrypoint is `service.handle`; inspect the call chain, not only an attractive helper. Do not edit the repository.

Contract:
`lines` contains nonnegative integer `unit_cents`/`quantity`; `member` is boolean. Optional nonnegative integer `credit_cents` defaults to zero. Sum the cart, apply the 10% member discount exactly once (nearest cent, half up), then subtract credit and floor the result at zero. Nonmembers get no discount. Return `{"total_cents": integer}`. Store credit is money and must not itself be discounted.

Write `/app/review.json` with this exact structure:
```json
{"schema_version":2,"reviews":[{"candidate":"cedar","decision":"accept","location":null,"behavior":null,"cases":[{"input":{},"expected":{}},{"input":{},"expected":{}}]}]}
```
The example shows structure only, not a verdict or valid test input. Include exactly one entry for every name in `candidates.json`, with no extras.

- `decision`: `accept` only when the candidate satisfies the entire contract; otherwise `reject`.
- For acceptance, `location` and `behavior` must be null: do not manufacture a finding. Provide 2–8 distinct compatibility cases, with exact contractual expected JSON outputs.
- For rejection, provide a nonempty description of the violated behavior and `location` as `{"path":"candidates/<name>/<module>.py","line":N}`. That line must be executed by at least one supplied failing case. Supply 2–8 distinct cases, including at least one input where the candidate's actual public result differs from the contractual `expected` output. Documented `ValueError` outcomes use `{"error":"ValueError"}`.

The verifier runs the same cases on clean copies of both base and candidate, validates expected outputs against a private contract, and independently checks candidate correctness using hidden regression cases. An import/collection/infrastructure failure is not a behavioral counterexample. Reason wording is not matched to a golden phrase and no LLM judge is used. Only the final review file is graded.
