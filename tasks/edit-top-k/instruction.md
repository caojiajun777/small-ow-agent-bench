# edit-top-k: application repair

This is an authored synthetic benchmark scenario, not a claimed upstream GitHub issue.

Team leaderboard: first sum event scores by `name`, preserving each team's first appearance for tie-breaking; then return top `k` teams descending. `k<=0` means none; oversize k returns all ranked teams. Neither API may reorder or modify inputs.

Repair both the existing primitive API `rank.top_k` and the application API `workflow.process(request)`. The JSON CLI is `python3 /app/repo/client.py`: one request on stdin, one JSON response on stdout. The primitive's original contract is retained below.

In `/app/repo/rank.py`, implement `top_k(rows, k)` where each row is `{"name": str, "score": number}`.

Return the `k` rows with the highest scores. Ties keep the original order. If `k` is larger than the list, return all rows in that order.

Example request: `{"events":[{"name":"a","score":4},{"name":"b","score":7},{"name":"a","score":4}],"k":2}`
Expected response: `[{"name":"a","score":8},{"name":"b","score":7}]`

Preserve unrelated behavior and public interfaces. Do not edit tests or the CLI adapter; do not hardcode these examples. Public regressions: `python3 -m pytest /app/repo/tests -q`. Repository: `/app/repo`.
