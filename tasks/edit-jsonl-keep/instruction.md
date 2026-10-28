# edit-jsonl-keep: application repair

This is an authored synthetic benchmark scenario, not a claimed upstream GitHub issue.

Audit ingestion: skip blank/invalid JSON and valid non-object JSON; accept only exact string status `ok`, preserving full objects and order. Group accepted objects by optional string `tenant` (missing means `unknown`) and count every object; duplicates are not deduplicated. Return `{accepted,counts}`.

Repair both the existing primitive API `filter_jsonl.keep_ok` and the application API `workflow.process(request)`. The JSON CLI is `python3 /app/repo/client.py`: one request on stdin, one JSON response on stdout. The primitive's original contract is retained below.

In `/app/repo/filter_jsonl.py`, implement `keep_ok(lines)`: `lines` is a list of JSON object strings. Return the objects whose `status` field is exactly `ok`, in the original order. Skip blank lines. Invalid JSON lines must be skipped, not crash.

Example request: `{"lines":["{\"status\":\"ok\",\"tenant\":\"x\",\"id\":1}","bad","{\"status\":\"ok\",\"tenant\":\"x\",\"id\":2}","null","{\"status\":\"ok\"}"]}`
Expected response: `{"accepted":[{"status":"ok","tenant":"x","id":1},{"status":"ok","tenant":"x","id":2},{"status":"ok"}],"counts":{"x":2,"unknown":1}}`

Preserve unrelated behavior and public interfaces. Do not edit tests or the CLI adapter; do not hardcode these examples. Public regressions: `python3 -m pytest /app/repo/tests -q`. Repository: `/app/repo`.
