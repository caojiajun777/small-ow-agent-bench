# Imported contact names retain interior whitespace

This is a deliberately small, synthetic application for a localization benchmark; it is not a reconstructed GitHub issue.

A synthetic contact-import CLI builds display labels and case-normalized email lookup keys. The active display-name cleaner leaves repeated spaces, tabs, and line breaks inside names. A similarly named legacy implementation and an unrelated lowercase key helper coexist; only the imported cleaner owns display whitespace normalization.

## Behavior contract

Display names collapse every run of Unicode whitespace into one ASCII space and trim their edges, preserving letter case and punctuation. Email keys are stripped then lowercased, not whitespace-collapsed by the display cleaner. Import order and IDs are preserved; an all-whitespace display name becomes the empty string.

Run `python3 client.py < examples/request.json` from this directory for a JSON request/response, or `python3 -m pytest tests -q` for public contract checks. These tests are expected to reveal the reported defect until the owning implementation is repaired. Public test inputs are examples, not the entire contract. No network or third-party runtime dependencies are required.

The requested deliverable is only a diagnosis. Preserve APIs and configuration boundaries; changing downstream callers to mask an upstream defect is not the maintenance fix being requested.
