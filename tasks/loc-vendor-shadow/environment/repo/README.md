# Vendored billing policy shadows the identically named local package

This is a deliberately small, synthetic application for a localization benchmark; it is not a reconstructed GitHub issue.

This synthetic upload service puts a pinned vendor directory first on sys.path. Documentation uses the package namespace billing.limits, but there are two physical copies. Production rejects valid attachments larger than 5 MB although the policy is 25 MB per file. Trace the actually loaded module, not just a matching filename.

## Behavior contract

The production import order intentionally uses the vendored billing package; do not bypass or unvendor it. Its configured maximum upload is 25 MB per file, inclusive. The upload service also rejects negative sizes, unsupported suffixes, and batches above 100 MB; these independent guards remain intact. Zero-byte attachments are valid.

Run `python3 client.py < examples/request.json` from this directory for a JSON request/response, or `python3 -m pytest tests -q` for public contract checks. These tests are expected to reveal the reported defect until the owning implementation is repaired. Public test inputs are examples, not the entire contract. No network or third-party runtime dependencies are required.

The requested deliverable is only a diagnosis. Preserve APIs and configuration boundaries; changing downstream callers to mask an upstream defect is not the maintenance fix being requested.
