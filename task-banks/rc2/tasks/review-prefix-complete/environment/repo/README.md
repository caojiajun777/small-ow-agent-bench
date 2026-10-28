# running totals with an opening balance

The pre-change revision is `base`. Four independently applied candidate revisions are listed in `candidates.json`; names do not encode their correctness. Each revision has a service entrypoint plus its implementation modules.

## User contract

`nums` is a finite-number list and optional finite `start` defaults to zero. Return `{"prefix": [...], "original": [...]}`: inclusive prefix totals starting from the opening balance, with the input list unchanged. An empty list returns no totals, regardless of `start`.

## Run without changing source

`printf '%s\n' '{"nums":[1,2,3]}' | python3 client.py --revision cedar`

Each input line is one JSON request. Each output line is its JSON result; a documented invalid value yields `{"error":"ValueError"}`. Other exceptions indicate an execution problem, not evidence of a successful review. Every candidate must satisfy the whole user contract, including compatibility and nonmutation requirements. No network access or installation is needed.

