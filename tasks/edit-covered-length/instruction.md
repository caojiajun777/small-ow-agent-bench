# edit-covered-length: application repair

This is an authored synthetic benchmark scenario, not a claimed upstream GitHub issue.

Monitoring uptime: group segments by device, clip each segment to request `window=[start,end]`, then return union duration for each seen device. Reversed/empty segments contribute zero. Overlap is counted once; input rows must not change.

Repair both the existing primitive API `span.covered` and the application API `workflow.process(request)`. The JSON CLI is `python3 /app/repo/client.py`: one request on stdin, one JSON response on stdout. The primitive's original contract is retained below.

In `/app/repo/span.py`, implement `covered(segments)`.

Each segment is a half-open interval `[start, end)` as a pair of numbers. Return the total length of the union of all segments. Empty and reversed segments (`end <= start`) contribute 0. Adjacent segments such as `[0, 1)` and `[1, 2)` cover length 2. Overlaps are counted once.

Example request: `{"window":[0,10],"segments":[{"device":"a","start":-4,"end":4},{"device":"a","start":2,"end":8},{"device":"b","start":20,"end":22}]}`
Expected response: `{"a":8,"b":0}`

Preserve unrelated behavior and public interfaces. Do not edit tests or the CLI adapter; do not hardcode these examples. Public regressions: `python3 -m pytest /app/repo/tests -q`. Repository: `/app/repo`.
