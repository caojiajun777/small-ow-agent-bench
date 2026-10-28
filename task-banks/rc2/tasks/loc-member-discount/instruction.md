# Membership invoices lose their discount

The project is at `/app/repo`. It is a synthetic application, not a real upstream issue.

A synthetic order service loads a local product catalog, resolves quantities, applies membership pricing, and adds shipping. Member invoices currently contain full-price lines. Membership pricing owns the 10% line discount; catalog lookup, quantity expansion, invoice assembly, and shipping behavior must remain unchanged.

The pricing API returns 90% of each item's list price for a member and full list price otherwise, including zero-priced items. The order API accepts {lines:[{sku,qty}],member,shipping}; shipping is added once after discounted item totals. Quantities are non-negative integers. Existing checkout.totals and app.run remain supported.

Inspect the live import/configuration/call chain and the public regressions (`python3 -m pytest tests -q`). You may use `python3 client.py < examples/request.json` to exercise the application. Identify the smallest complete set of **defective owning files** that need changes while preserving the published module/API responsibilities. Do not list every caller, test, or a correct but unused alternative. More than one owning file may be necessary.

Write paths relative to `/app/repo`, with forward slashes, one per line, to `/app/answer.txt`. Order does not matter. Do not modify repository files. A correct answer must identify all defects described above, not merely suppress one example symptom.
