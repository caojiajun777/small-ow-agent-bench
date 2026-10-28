# edit-unique-keep: application repair

This is an authored synthetic benchmark scenario, not a claimed upstream GitHub issue.

Idempotent event ingestion: return the first full event for each string key, in first-seen order. Later duplicate payloads must never overwrite the first event. Primitive unique preserves first occurrences by Python equality (including JSON lists/dicts), accepts empty input, and never mutates input.

Repair both the existing primitive API `unique.unique` and the application API `workflow.process(request)`. The JSON CLI is `python3 /app/repo/client.py`: one request on stdin, one JSON response on stdout. The primitive's original contract is retained below.

In `/app/repo/unique.py`, implement `unique(items)`.

Return a new list of first occurrences, in original order. Do not modify `items`.

Example request: `{"events":[{"key":"b","payload":1},{"key":"a","payload":2},{"key":"b","payload":9}]}`
Expected response: `[{"key":"b","payload":1},{"key":"a","payload":2}]`

Preserve unrelated behavior and public interfaces. Do not edit tests or the CLI adapter; do not hardcode these examples. Public regressions: `python3 -m pytest /app/repo/tests -q`. Repository: `/app/repo`.
