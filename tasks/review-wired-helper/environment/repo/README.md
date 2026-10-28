# member checkout with post-discount store credit

The pre-change revision is `base`. Four independently applied candidate revisions are listed in `candidates.json`; names do not encode their correctness. Each revision has a service entrypoint plus its implementation modules.

## User contract

`lines` contains nonnegative integer `unit_cents`/`quantity`; `member` is boolean. Optional nonnegative integer `credit_cents` defaults to zero. Sum the cart, apply the 10% member discount exactly once (nearest cent, half up), then subtract credit and floor the result at zero. Nonmembers get no discount. Return `{"total_cents": integer}`. Store credit is money and must not itself be discounted.

## Run without changing source

`printf '%s\n' '{"lines":[{"unit_cents":10000,"quantity":1}],"member":true,"credit_cents":1000}' | python3 client.py --revision cedar`

Each input line is one JSON request. Each output line is its JSON result; a documented invalid value yields `{"error":"ValueError"}`. Other exceptions indicate an execution problem, not evidence of a successful review. Every candidate must satisfy the whole user contract, including compatibility and nonmutation requirements. No network access or installation is needed.

