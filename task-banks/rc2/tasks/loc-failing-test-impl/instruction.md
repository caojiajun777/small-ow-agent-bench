# The invoice's published tax contract fails

The project is at `/app/repo`. It is a synthetic application, not a real upstream issue.

A synthetic invoice service expands basket quantities, applies an order discount, and adds tax to merchandise while keeping shipping exempt. A failing public test is legitimate: the shared tax implementation returns net unchanged. The test and invoice delegation are not the defect.

tax.with_tax adds 10% to any numeric net amount, including zero and negative credit notes. invoice_total remains its public delegate. The order endpoint taxes sum(price*qty)*(1-discount), then adds shipping without taxing it; input lines are unchanged.

Inspect the live import/configuration/call chain and the public regressions (`python3 -m pytest tests -q`). You may use `python3 client.py < examples/request.json` to exercise the application. Identify the smallest complete set of **defective owning files** that need changes while preserving the published module/API responsibilities. Do not list every caller, test, or a correct but unused alternative. More than one owning file may be necessary.

Write paths relative to `/app/repo`, with forward slashes, one per line, to `/app/answer.txt`. Order does not matter. Do not modify repository files. A correct answer must identify all defects described above, not merely suppress one example symptom.
