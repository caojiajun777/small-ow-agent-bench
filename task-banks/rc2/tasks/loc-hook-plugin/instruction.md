# The selected retry plugin exhausts jobs too early

The project is at `/app/repo`. It is a synthetic application, not a real upstream issue.

This synthetic job worker selects its retry policy through hooks.json and dynamic file imports. The selected plugin allows only two attempts although operations policy requires five. A different similarly named plugin already has five attempts but is not selected; the supported plugin selection is intentional.

Keep the existing hook selection and configuration entry point unchanged, and preserve the loader/worker split. The selected plugin's ATTEMPTS is five, including the first attempt. Each job consumes one scripted outcome per attempt (missing outcomes mean failure), stops at first success, and reports both final status and attempts used. Inputs and separate jobs must remain independent.

Inspect the live import/configuration/call chain and the public regressions (`python3 -m pytest tests -q`). You may use `python3 client.py < examples/request.json` to exercise the application. Identify the smallest complete set of **defective owning files** that need changes while preserving the published module/API responsibilities. Do not list every caller, test, or a correct but unused alternative. More than one owning file may be necessary.

Write paths relative to `/app/repo`, with forward slashes, one per line, to `/app/answer.txt`. Order does not matter. Do not modify repository files. A correct answer must identify all defects described above, not merely suppress one example symptom.
