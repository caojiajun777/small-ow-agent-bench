# VIP invoices bypass a misconfigured strategy

This is a deliberately small, synthetic application for a localization benchmark; it is not a reconstructed GitHub issue.

A synthetic shop has separate VIP and legacy promotion strategies. Both direct VIP quoting and final order checkout must honor the published 80%-of-list VIP policy. A legacy campaign deliberately leaves its price unchanged and is not the VIP implementation. The symptom survives fixing only strategy selection or only the VIP rate.

## Behavior contract

The VIP strategy owns the 0.8 multiplier and checkout owns dispatch to that strategy. Standard customers and the unrelated legacy promotion remain at full list price. Order invoices multiply each priced line by qty and then add shipping once. APIs pricing.vip.vip_price and checkout.charge are public contracts, not replaceable by hardcoded invoice totals.

Run `python3 client.py < examples/request.json` from this directory for a JSON request/response, or `python3 -m pytest tests -q` for public contract checks. These tests are expected to reveal the reported defect until the owning implementation is repaired. Public test inputs are examples, not the entire contract. No network or third-party runtime dependencies are required.

The requested deliverable is only a diagnosis. Preserve APIs and configuration boundaries; changing downstream callers to mask an upstream defect is not the maintenance fix being requested.
