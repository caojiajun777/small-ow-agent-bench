# count import validation

The pre-change revision is `base`. Four independently applied candidate revisions are listed in `candidates.json`; names do not encode their correctness. Each revision has a service entrypoint plus its implementation modules.

## User contract

`counts` is a list of strings. Strip surrounding whitespace, then accept an optional ASCII `+`/`-` followed by one or more ASCII digits. Return parsed integers as `{"counts": [...]}`. Invalid text raises `ValueError` for the entire request. Zero and negative counts are valid. Underscores, decimal points, blank text and non-ASCII digits are invalid.

## Run without changing source

`printf '%s\n' '{"counts":["3","  -2 ","+0"]}' | python3 client.py --revision cedar`

Each input line is one JSON request. Each output line is its JSON result; a documented invalid value yields `{"error":"ValueError"}`. Other exceptions indicate an execution problem, not evidence of a successful review. Every candidate must satisfy the whole user contract, including compatibility and nonmutation requirements. No network access or installation is needed.

