# Imported contact names retain interior whitespace

The project is at `/app/repo`. It is a synthetic application, not a real upstream issue.

A synthetic contact-import CLI builds display labels and case-normalized email lookup keys. The active display-name cleaner leaves repeated spaces, tabs, and line breaks inside names. A similarly named legacy implementation and an unrelated lowercase key helper coexist; only the imported cleaner owns display whitespace normalization.

Display names collapse every run of Unicode whitespace into one ASCII space and trim their edges, preserving letter case and punctuation. Email keys are stripped then lowercased, not whitespace-collapsed by the display cleaner. Import order and IDs are preserved; an all-whitespace display name becomes the empty string.

Inspect the live import/configuration/call chain and the public regressions (`python3 -m pytest tests -q`). You may use `python3 client.py < examples/request.json` to exercise the application. Identify the smallest complete set of **defective owning files** that need changes while preserving the published module/API responsibilities. Do not list every caller, test, or a correct but unused alternative. More than one owning file may be necessary.

Write paths relative to `/app/repo`, with forward slashes, one per line, to `/app/answer.txt`. Order does not matter. Do not modify repository files. A correct answer must identify all defects described above, not merely suppress one example symptom.
