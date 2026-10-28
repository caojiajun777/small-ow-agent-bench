# wiring member pricing into the public checkout

The pre-change revision is `base`. Four independently applied candidate revisions are listed in `candidates.json`; names do not encode their correctness. Each revision has a service entrypoint plus its implementation modules.

## User contract

`lines` contains objects with nonnegative integer `unit_cents` and `quantity`; `member` is boolean. Compute the full subtotal. Members pay 90% of that subtotal, rounded to the nearest cent with exact halves rounded up; others pay the subtotal. Apply the discount exactly once. Return `{"total_cents": integer}`. Judge the actual service entrypoint, not the mere existence of a helper.

## Run without changing source

`printf '%s\n' '{"lines":[{"unit_cents":10000,"quantity":1}],"member":true}' | python3 client.py --revision cedar`

Each input line is one JSON request. Each output line is its JSON result; a documented invalid value yields `{"error":"ValueError"}`. Other exceptions indicate an execution problem, not evidence of a successful review. Every candidate must satisfy the whole user contract, including compatibility and nonmutation requirements. No network access or installation is needed.

