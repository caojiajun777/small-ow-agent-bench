Review the four candidate patches for **summary statistics API** in `/app/repo`.

The user contract and runnable JSON CLI are documented in `README.md`. `base/` is the pre-change workspace. Each subdirectory in `candidates/` is the result of applying a different proposed patch independently. The actual API entrypoint is `service.handle`; inspect the call chain, not only an attractive helper. Do not edit the repository.

Contract:
`batches` is a list of lists. Every nonempty inner batch must contain at most 1000 integers, each with absolute value at most 1,000,000; booleans are not integers for this API. Return `{"means": [...]}` containing each arithmetic mean without truncation or rounding. An empty inner batch, float, boolean, out-of-range integer, or oversized inner batch raises `ValueError` for the whole request. An empty outer batch is valid. Numerically equal integer/float results are equivalent; no tolerance is applied.

Write `/app/review.json` with this exact structure:
```json
{"schema_version":2,"reviews":[{"candidate":"cedar","decision":"accept","location":null,"behavior":null,"cases":[{"input":{},"expected":{}},{"input":{},"expected":{}}]}]}
```
The example shows structure only, not a verdict or valid test input. Include exactly one entry for every name in `candidates.json`, with no extras.

- `decision`: `accept` only when the candidate satisfies the entire contract; otherwise `reject`.
- For acceptance, `location` and `behavior` must be null: do not manufacture a finding. Provide 2–8 distinct compatibility cases, with exact contractual expected JSON outputs.
- For rejection, provide a nonempty description of the violated behavior and `location` as `{"path":"candidates/<name>/<module>.py","line":N}`. That line must be executed by at least one supplied failing case. Supply 2–8 distinct cases, including at least one input where the candidate's actual public result differs from the contractual `expected` output. Documented `ValueError` outcomes use `{"error":"ValueError"}`.

The verifier runs the same cases on clean copies of both base and candidate, validates expected outputs against a private contract, and independently checks candidate correctness using hidden regression cases. An import/collection/infrastructure failure is not a behavioral counterexample. Reason wording is not matched to a golden phrase and no LLM judge is used. Only the final review file is graded.
