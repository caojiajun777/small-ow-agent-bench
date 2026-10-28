# edit-hhmmss: application repair

This is an authored synthetic benchmark scenario, not a claimed upstream GitHub issue.

Job timing: each row has integer `start`, `end` seconds and optional nonnegative `paused`. Active duration is max(0,end-start-paused); format each and their sum as H:MM:SS, hours unrestricted. Preserve row order and IDs; do not alter rows.

Repair both the existing primitive API `timefmt.format_hms` and the application API `workflow.process(request)`. The JSON CLI is `python3 /app/repo/client.py`: one request on stdin, one JSON response on stdout. The primitive's original contract is retained below.

In `/app/repo/timefmt.py`, implement `format_hms(seconds)` for a non-negative integer number of seconds.

Return `H:MM:SS` where `MM` and `SS` are two digits. Hours may be larger than 24.

Example request: `{"jobs":[{"id":"a","start":10,"end":80,"paused":5},{"id":"b","start":0,"end":3600}]}`
Expected response: `{"jobs":[{"id":"a","duration":"0:01:05"},{"id":"b","duration":"1:00:00"}],"total":"1:01:05"}`

Preserve unrelated behavior and public interfaces. Do not edit tests or the CLI adapter; do not hardcode these examples. Public regressions: `python3 -m pytest /app/repo/tests -q`. Repository: `/app/repo`.
