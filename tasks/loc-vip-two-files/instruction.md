# VIP invoices bypass a misconfigured strategy

The project is at `/app/repo`. It is a synthetic application, not a real upstream issue.

A synthetic shop has separate VIP and legacy promotion strategies. Both direct VIP quoting and final order checkout must honor the published 80%-of-list VIP policy. A legacy campaign deliberately leaves its price unchanged and is not the VIP implementation. The symptom survives fixing only strategy selection or only the VIP rate.

The VIP strategy owns the 0.8 multiplier and checkout owns dispatch to that strategy. Standard customers and the unrelated legacy promotion remain at full list price. Order invoices multiply each priced line by qty and then add shipping once. APIs pricing.vip.vip_price and checkout.charge are public contracts, not replaceable by hardcoded invoice totals.

Inspect the live import/configuration/call chain and the public regressions (`python3 -m pytest tests -q`). You may use `python3 client.py < examples/request.json` to exercise the application. Identify the smallest complete set of **defective owning files** that need changes while preserving the published module/API responsibilities. Do not list every caller, test, or a correct but unused alternative. More than one owning file may be necessary.

Write paths relative to `/app/repo`, with forward slashes, one per line, to `/app/answer.txt`. Order does not matter. Do not modify repository files. A correct answer must identify all defects described above, not merely suppress one example symptom.
