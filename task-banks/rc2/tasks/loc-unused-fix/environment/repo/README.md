# An unreferenced corrected adapter does not fix production

This is a deliberately small, synthetic application for a localization benchmark; it is not a reconstructed GitHub issue.

A synthetic service repository contains an experimental replacement that appears to solve the listener bug, but the production application never imports it. The live adapter still ignores the selected interface. Fix the production implementation in place rather than switching callers to a leftover alternative.

## Behavior contract

serve.bind(config=None) is the supported production API. It uses the selected host and port or file defaults; app.main and the deployment-plan endpoint must use it. The unreferenced unused_fix module is experimental and must remain outside the production import graph. Worker count and local health checks are independent configuration fields.

Run `python3 client.py < examples/request.json` from this directory for a JSON request/response, or `python3 -m pytest tests -q` for public contract checks. These tests are expected to reveal the reported defect until the owning implementation is repaired. Public test inputs are examples, not the entire contract. No network or third-party runtime dependencies are required.

The requested deliverable is only a diagnosis. Preserve APIs and configuration boundaries; changing downstream callers to mask an upstream defect is not the maintenance fix being requested.
