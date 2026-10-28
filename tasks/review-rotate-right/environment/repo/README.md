# non-mutating playlist rotation

The pre-change revision is `base`. Four independently applied candidate revisions are listed in `candidates.json`; names do not encode their correctness. Each revision has a service entrypoint plus its implementation modules.

## User contract

`items` is a JSON list and optional integer `k` defaults to one. Return `{"rotated": ..., "original": ...}` after rotating left by `k` positions. Negative `k` rotates right; normalize arbitrary magnitudes. Empty lists stay empty. `original` must remain equal to the supplied list: rotation may not mutate the caller's data.

## Run without changing source

`printf '%s\n' '{"items":[1,2,3]}' | python3 client.py --revision cedar`

Each input line is one JSON request. Each output line is its JSON result; a documented invalid value yields `{"error":"ValueError"}`. Other exceptions indicate an execution problem, not evidence of a successful review. Every candidate must satisfy the whole user contract, including compatibility and nonmutation requirements. No network access or installation is needed.

