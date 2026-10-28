# edit-int-list: application repair

This is an authored synthetic benchmark scenario, not a claimed upstream GitHub issue.

CSV export selection: parse comma-separated signed integer IDs, retain requested order and repetitions, skip blank tokens and IDs not present in `rows`, and return matching record copies. Input data must not change. Nonempty malformed integer tokens must raise ValueError (do not silently drop them).

Repair both the existing primitive API `parse.parse_int_list` and the application API `workflow.process(request)`. The JSON CLI is `python3 /app/repo/client.py`: one request on stdin, one JSON response on stdout. The primitive's original contract is retained below.

In `/app/repo/parse.py`, implement `parse_int_list(text)` so it splits on commas, ignores surrounding whitespace, skips empty items, and returns integers.

Example request: `{"ids":"3,1,,3,9","rows":[{"id":1,"name":"Ada"},{"id":3,"name":"Lin"}]}`
Expected response: `[{"id":3,"name":"Lin"},{"id":1,"name":"Ada"},{"id":3,"name":"Lin"}]`

Preserve unrelated behavior and public interfaces. Do not edit tests or the CLI adapter; do not hardcode these examples. Public regressions: `python3 -m pytest /app/repo/tests -q`. Repository: `/app/repo`.
