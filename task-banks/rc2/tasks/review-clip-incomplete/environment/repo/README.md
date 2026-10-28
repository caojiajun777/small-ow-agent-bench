# clamping a telemetry batch

The pre-change revision is `base`. Four independently applied candidate revisions are listed in `candidates.json`; names do not encode their correctness. Each revision has a service entrypoint plus its implementation modules.

## User contract

`values` is a list of finite numbers. Clamp each into inclusive `[lo, hi]`; reversed bounds must raise `ValueError`. Return an object with `values` (clamped results) and `original` (unchanged input list). The batch API must preserve the caller's list.

## Run without changing source

`printf '%s\n' '{"values":[-3,2,19],"lo":0,"hi":10}' | python3 client.py --revision cedar`

Each input line is one JSON request. Each output line is its JSON result; a documented invalid value yields `{"error":"ValueError"}`. Other exceptions indicate an execution problem, not evidence of a successful review. Every candidate must satisfy the whole user contract, including compatibility and nonmutation requirements. No network access or installation is needed.

