# edit-retry-discount: application repair

This is an authored synthetic benchmark scenario, not a claimed upstream GitHub issue.

Payment retry settlement: attempts is a positive integer. Repeatedly charge each cart, always discounting immutable list_price by 10%, not stale/running total; charge writes total but preserves list_price and other fields. Workflow returns receipts with shipping added exactly once, without changing caller carts.

Repair both the existing primitive API `checkout.charge` and the application API `workflow.process(request)`. The JSON CLI is `python3 /app/repo/client.py`: one request on stdin, one JSON response on stdout. The primitive's original contract is retained below.

In `/app/repo/checkout.py`, implement `charge(cart)`.

Member checkout is 10% off the list price. Charging the same cart again must
still be 10% off that original list, not a smaller amount.

Example request: `{"attempts":3,"carts":[{"id":"a","list_price":100,"total":100,"shipping":5},{"id":"b","list_price":50,"total":1}]}`
Expected response: `[{"id":"a","total":95},{"id":"b","total":45}]`

Preserve unrelated behavior and public interfaces. Do not edit tests or the CLI adapter; do not hardcode these examples. Public regressions: `python3 -m pytest /app/repo/tests -q`. Repository: `/app/repo`.
