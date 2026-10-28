# A supported missing reading becomes a chained load error

The project is at `/app/repo`. It is a synthetic application, not a real upstream issue.

This synthetic telemetry importer wraps input errors at the application boundary. A supported legacy producer uses the exact token not-a-number for a missing reading. The included data is valid under that wire contract, but loading it raises RuntimeError('load failed') with a ValueError cause. Follow the traceback into the decoder; do not delete valid records or suppress every parse error.

A record is a nonempty ID, a colon, and either a signed base-10 integer or the exact missing-value token not-a-number (surrounding whitespace is allowed). Decoding the missing token yields amount=None; other malformed amounts remain errors. The loader skips blank lines, preserves record order, and the report counts missing readings separately from the sum of present readings. Malformed inputs retain the application exception cause.

Inspect the live import/configuration/call chain and the public regressions (`python3 -m pytest tests -q`). You may use `python3 client.py < examples/request.json` to exercise the application. Identify the smallest complete set of **defective owning files** that need changes while preserving the published module/API responsibilities. Do not list every caller, test, or a correct but unused alternative. More than one owning file may be necessary.

Write paths relative to `/app/repo`, with forward slashes, one per line, to `/app/answer.txt`. Order does not matter. Do not modify repository files. A correct answer must identify all defects described above, not merely suppress one example symptom.
