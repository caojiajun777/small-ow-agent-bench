# Membership invoices lose their discount

This is a deliberately small, synthetic application for a localization benchmark; it is not a reconstructed GitHub issue.

A synthetic order service loads a local product catalog, resolves quantities, applies membership pricing, and adds shipping. Member invoices currently contain full-price lines. Membership pricing owns the 10% line discount; catalog lookup, quantity expansion, invoice assembly, and shipping behavior must remain unchanged.

## Behavior contract

The pricing API returns 90% of each item's list price for a member and full list price otherwise, including zero-priced items. The order API accepts {lines:[{sku,qty}],member,shipping}; shipping is added once after discounted item totals. Quantities are non-negative integers. Existing checkout.totals and app.run remain supported.

Run `python3 client.py < examples/request.json` from this directory for a JSON request/response, or `python3 -m pytest tests -q` for public contract checks. These tests are expected to reveal the reported defect until the owning implementation is repaired. Public test inputs are examples, not the entire contract. No network or third-party runtime dependencies are required.

The requested deliverable is only a diagnosis. Preserve APIs and configuration boundaries; changing downstream callers to mask an upstream defect is not the maintenance fix being requested.
