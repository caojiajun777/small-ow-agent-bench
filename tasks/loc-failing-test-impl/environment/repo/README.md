# The invoice's published tax contract fails

This is a deliberately small, synthetic application for a localization benchmark; it is not a reconstructed GitHub issue.

A synthetic invoice service expands basket quantities, applies an order discount, and adds tax to merchandise while keeping shipping exempt. A failing public test is legitimate: the shared tax implementation returns net unchanged. The test and invoice delegation are not the defect.

## Behavior contract

tax.with_tax adds 10% to any numeric net amount, including zero and negative credit notes. invoice_total remains its public delegate. The order endpoint taxes sum(price*qty)*(1-discount), then adds shipping without taxing it; input lines are unchanged.

Run `python3 client.py < examples/request.json` from this directory for a JSON request/response, or `python3 -m pytest tests -q` for public contract checks. These tests are expected to reveal the reported defect until the owning implementation is repaired. Public test inputs are examples, not the entire contract. No network or third-party runtime dependencies are required.

The requested deliverable is only a diagnosis. Preserve APIs and configuration boundaries; changing downstream callers to mask an upstream defect is not the maintenance fix being requested.
