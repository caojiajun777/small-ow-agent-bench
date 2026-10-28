# The selected retry plugin exhausts jobs too early

This is a deliberately small, synthetic application for a localization benchmark; it is not a reconstructed GitHub issue.

This synthetic job worker selects its retry policy through hooks.json and dynamic file imports. The selected plugin allows only two attempts although operations policy requires five. A different similarly named plugin already has five attempts but is not selected; the supported plugin selection is intentional.

## Behavior contract

Keep the existing hook selection and configuration entry point unchanged, and preserve the loader/worker split. The selected plugin's ATTEMPTS is five, including the first attempt. Each job consumes one scripted outcome per attempt (missing outcomes mean failure), stops at first success, and reports both final status and attempts used. Inputs and separate jobs must remain independent.

Run `python3 client.py < examples/request.json` from this directory for a JSON request/response, or `python3 -m pytest tests -q` for public contract checks. These tests are expected to reveal the reported defect until the owning implementation is repaired. Public test inputs are examples, not the entire contract. No network or third-party runtime dependencies are required.

The requested deliverable is only a diagnosis. Preserve APIs and configuration boundaries; changing downstream callers to mask an upstream defect is not the maintenance fix being requested.
