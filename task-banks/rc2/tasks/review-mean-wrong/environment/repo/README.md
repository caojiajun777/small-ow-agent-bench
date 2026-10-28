# summary statistics API

The pre-change revision is `base`. Four independently applied candidate revisions are listed in `candidates.json`; names do not encode their correctness. Each revision has a service entrypoint plus its implementation modules.

## User contract

`batches` is a list of lists. Every nonempty inner batch must contain at most 1000 integers, each with absolute value at most 1,000,000; booleans are not integers for this API. Return `{"means": [...]}` containing each arithmetic mean without truncation or rounding. An empty inner batch, float, boolean, out-of-range integer, or oversized inner batch raises `ValueError` for the whole request. An empty outer batch is valid. Numerically equal integer/float results are equivalent; no tolerance is applied.

## Run without changing source

`printf '%s\n' '{"batches":[[1,2,3],[1,2]]}' | python3 client.py --revision cedar`

Each input line is one JSON request. Each output line is its JSON result; a documented invalid value yields `{"error":"ValueError"}`. Other exceptions indicate an execution problem, not evidence of a successful review. Every candidate must satisfy the whole user contract, including compatibility and nonmutation requirements. No network access or installation is needed.

