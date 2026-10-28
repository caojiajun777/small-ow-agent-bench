# An unreferenced corrected adapter does not fix production

The project is at `/app/repo`. It is a synthetic application, not a real upstream issue.

A synthetic service repository contains an experimental replacement that appears to solve the listener bug, but the production application never imports it. The live adapter still ignores the selected interface. Fix the production implementation in place rather than switching callers to a leftover alternative.

serve.bind(config=None) is the supported production API. It uses the selected host and port or file defaults; app.main and the deployment-plan endpoint must use it. The unreferenced unused_fix module is experimental and must remain outside the production import graph. Worker count and local health checks are independent configuration fields.

Inspect the live import/configuration/call chain and the public regressions (`python3 -m pytest tests -q`). You may use `python3 client.py < examples/request.json` to exercise the application. Identify the smallest complete set of **defective owning files** that need changes while preserving the published module/API responsibilities. Do not list every caller, test, or a correct but unused alternative. More than one owning file may be necessary.

Write paths relative to `/app/repo`, with forward slashes, one per line, to `/app/answer.txt`. Order does not matter. Do not modify repository files. A correct answer must identify all defects described above, not merely suppress one example symptom.
