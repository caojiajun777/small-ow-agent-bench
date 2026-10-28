# The public package alias exports a stale bind implementation

The project is at `/app/repo`. It is a synthetic application, not a real upstream issue.

A synthetic gateway is launched through a package-level public API. Its re-export is wired correctly, yet the implementation behind that alias discards configured endpoints. The package API must continue exposing the same implementation; adding an unrelated implementation in the export module only hides the defect.

pkg.bind is a direct re-export of pkg.core.bind. Both accept an optional config object and return its (host,port), defaulting to settings.load. The gateway advertises an http/https URL according to tls; the diagnostic endpoint intentionally remains localhost. Config overrides must not be mutated.

Inspect the live import/configuration/call chain and the public regressions (`python3 -m pytest tests -q`). You may use `python3 client.py < examples/request.json` to exercise the application. Identify the smallest complete set of **defective owning files** that need changes while preserving the published module/API responsibilities. Do not list every caller, test, or a correct but unused alternative. More than one owning file may be necessary.

Write paths relative to `/app/repo`, with forward slashes, one per line, to `/app/answer.txt`. Order does not matter. Do not modify repository files. A correct answer must identify all defects described above, not merely suppress one example symptom.
