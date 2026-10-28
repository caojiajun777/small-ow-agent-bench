# URL slugs in a publishing batch

The pre-change revision is `base`. Four independently applied candidate revisions are listed in `candidates.json`; names do not encode their correctness. Each revision has a service entrypoint plus its implementation modules.

## User contract

`texts` is a list of strings. Return `{"slugs": [...]}` in input order. Slugification lowercases Unicode text, retains Unicode alphanumeric characters, converts whitespace or existing hyphens into separators, drops other punctuation, collapses adjacent separators, and strips edge separators. Empty/punctuation-only titles produce an empty slug.

## Run without changing source

`printf '%s\n' '{"texts":["Hello,  World!!","  ABC  "]}' | python3 client.py --revision cedar`

Each input line is one JSON request. Each output line is its JSON result; a documented invalid value yields `{"error":"ValueError"}`. Other exceptions indicate an execution problem, not evidence of a successful review. Every candidate must satisfy the whole user contract, including compatibility and nonmutation requirements. No network access or installation is needed.

