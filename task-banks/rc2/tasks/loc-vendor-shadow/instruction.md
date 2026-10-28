# Vendored billing policy shadows the identically named local package

The project is at `/app/repo`. It is a synthetic application, not a real upstream issue.

This synthetic upload service puts a pinned vendor directory first on sys.path. Documentation uses the package namespace billing.limits, but there are two physical copies. Production rejects valid attachments larger than 5 MB although the policy is 25 MB per file. Trace the actually loaded module, not just a matching filename.

The production import order intentionally uses the vendored billing package; do not bypass or unvendor it. Its configured maximum upload is 25 MB per file, inclusive. The upload service also rejects negative sizes, unsupported suffixes, and batches above 100 MB; these independent guards remain intact. Zero-byte attachments are valid.

Inspect the live import/configuration/call chain and the public regressions (`python3 -m pytest tests -q`). You may use `python3 client.py < examples/request.json` to exercise the application. Identify the smallest complete set of **defective owning files** that need changes while preserving the published module/API responsibilities. Do not list every caller, test, or a correct but unused alternative. More than one owning file may be necessary.

Write paths relative to `/app/repo`, with forward slashes, one per line, to `/app/answer.txt`. Order does not matter. Do not modify repository files. A correct answer must identify all defects described above, not merely suppress one example symptom.
