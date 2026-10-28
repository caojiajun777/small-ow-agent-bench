# edit-timeout-zero: application repair

This is an authored synthetic benchmark scenario, not a claimed upstream GitHub issue.

Job scheduling: per-job config overrides defaults by key presence, including timeout=0. Zero means unlimited (`deadline:null`); other nonnegative numeric timeouts give now+timeout. Missing everywhere means 30. Return timeout too, retain IDs/order, no input mutation. Primitive get_timeout returns any explicitly present value, even null.

Repair both the existing primitive API `limits.get_timeout` and the application API `workflow.process(request)`. The JSON CLI is `python3 /app/repo/client.py`: one request on stdin, one JSON response on stdout. The primitive's original contract is retained below.

In `/app/repo/limits.py`, implement `get_timeout(cfg)`.

If `timeout` is present, return that value (including `0`). If it is omitted, return `30`.

Example request: `{"now":100,"defaults":{"timeout":8},"jobs":[{"id":"a","config":{"timeout":0}},{"id":"b"},{"id":"c","config":{"timeout":2}}]}`
Expected response: `[{"id":"a","timeout":0,"deadline":null},{"id":"b","timeout":8,"deadline":108},{"id":"c","timeout":2,"deadline":102}]`

Preserve unrelated behavior and public interfaces. Do not edit tests or the CLI adapter; do not hardcode these examples. Public regressions: `python3 -m pytest /app/repo/tests -q`. Repository: `/app/repo`.
