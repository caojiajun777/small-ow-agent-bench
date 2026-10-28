# The public package alias exports a stale bind implementation

This is a deliberately small, synthetic application for a localization benchmark; it is not a reconstructed GitHub issue.

A synthetic gateway is launched through a package-level public API. Its re-export is wired correctly, yet the implementation behind that alias discards configured endpoints. The package API must continue exposing the same implementation; adding an unrelated implementation in the export module only hides the defect.

## Behavior contract

pkg.bind is a direct re-export of pkg.core.bind. Both accept an optional config object and return its (host,port), defaulting to settings.load. The gateway advertises an http/https URL according to tls; the diagnostic endpoint intentionally remains localhost. Config overrides must not be mutated.

Run `python3 client.py < examples/request.json` from this directory for a JSON request/response, or `python3 -m pytest tests -q` for public contract checks. These tests are expected to reveal the reported defect until the owning implementation is repaired. Public test inputs are examples, not the entire contract. No network or third-party runtime dependencies are required.

The requested deliverable is only a diagnosis. Preserve APIs and configuration boundaries; changing downstream callers to mask an upstream defect is not the maintenance fix being requested.
