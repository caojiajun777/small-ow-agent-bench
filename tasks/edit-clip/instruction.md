# edit-clip: application repair

This is an authored synthetic benchmark scenario, not a claimed upstream GitHub issue.

Sensor calibration: first apply `raw*scale+offset` (defaults 1 and 0), then clip to that channel's `[lo,hi]`. Bounds satisfy lo<=hi. Return ordered `{id,value}` rows; preserve input. Primitive clip handles lower/upper boundaries, negative ranges and fractional values.

Repair both the existing primitive API `clip.clip` and the application API `workflow.process(request)`. The JSON CLI is `python3 /app/repo/client.py`: one request on stdin, one JSON response on stdout. The primitive's original contract is retained below.

In `/app/repo/clip.py`, implement `clip(value, lo, hi)`.

Return `lo` if `value` is below `lo`, `hi` if it is above `hi`, otherwise `value`.

Example request: `{"limits":{"temp":[0,10]},"readings":[{"id":1,"channel":"temp","value":8,"scale":2},{"id":2,"channel":"temp","value":-1,"offset":5}]}`
Expected response: `[{"id":1,"value":10},{"id":2,"value":4}]`

Preserve unrelated behavior and public interfaces. Do not edit tests or the CLI adapter; do not hardcode these examples. Public regressions: `python3 -m pytest /app/repo/tests -q`. Repository: `/app/repo`.
