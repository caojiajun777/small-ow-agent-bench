# edit-prefix-sums: application repair

This is an authored synthetic benchmark scenario, not a claimed upstream GitHub issue.

Account statement: posting amounts are signed numbers in arrival order. Return inclusive balances starting from `opening` (default zero) and final `closing`; for no postings closing equals opening. Do not mutate postings or primitive input.

Repair both the existing primitive API `scan.prefix_sums` and the application API `workflow.process(request)`. The JSON CLI is `python3 /app/repo/client.py`: one request on stdin, one JSON response on stdout. The primitive's original contract is retained below.

In `/app/repo/scan.py`, implement `prefix_sums(nums)`.

Return a new list where index `i` is the sum of `nums[0]` through `nums[i]` inclusive. An empty input yields an empty list. Do not modify `nums`.

Example request: `{"opening":100,"postings":[{"amount":5},{"amount":-20},{"amount":0}]}`
Expected response: `{"balances":[105,85,85],"closing":85}`

Preserve unrelated behavior and public interfaces. Do not edit tests or the CLI adapter; do not hardcode these examples. Public regressions: `python3 -m pytest /app/repo/tests -q`. Repository: `/app/repo`.
