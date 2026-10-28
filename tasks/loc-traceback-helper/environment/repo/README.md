# A supported missing reading becomes a chained load error

This is a deliberately small, synthetic application for a localization benchmark; it is not a reconstructed GitHub issue.

This synthetic telemetry importer wraps input errors at the application boundary. A supported legacy producer uses the exact token not-a-number for a missing reading. The included data is valid under that wire contract, but loading it raises RuntimeError('load failed') with a ValueError cause. Follow the traceback into the decoder; do not delete valid records or suppress every parse error.

## Behavior contract

A record is a nonempty ID, a colon, and either a signed base-10 integer or the exact missing-value token not-a-number (surrounding whitespace is allowed). Decoding the missing token yields amount=None; other malformed amounts remain errors. The loader skips blank lines, preserves record order, and the report counts missing readings separately from the sum of present readings. Malformed inputs retain the application exception cause.

Run `python3 client.py < examples/request.json` from this directory for a JSON request/response, or `python3 -m pytest tests -q` for public contract checks. These tests are expected to reveal the reported defect until the owning implementation is repaired. Public test inputs are examples, not the entire contract. No network or third-party runtime dependencies are required.

The requested deliverable is only a diagnosis. Preserve APIs and configuration boundaries; changing downstream callers to mask an upstream defect is not the maintenance fix being requested.
