# stable publication routes with collision handling

The pre-change revision is `base`. Four independently applied candidate revisions are listed in `candidates.json`; names do not encode their correctness. Each revision has a service entrypoint plus its implementation modules.

## User contract

`titles` is a list of strings. Slugification lowercases Unicode text, retains alphanumeric characters, converts whitespace/existing hyphens to separators, drops other punctuation, collapses separators, and strips edge separators. Empty slugs use `untitled`. Allocate unique routes in input order: start with the slug; while already allocated, try its `-2`, `-3`, ... suffixes. Existing suffixed titles occupy their literal route too. Return `{"routes": [...]}`.

## Run without changing source

`printf '%s\n' '{"titles":["Hello,  World!!","Hello World"]}' | python3 client.py --revision cedar`

Each input line is one JSON request. Each output line is its JSON result; a documented invalid value yields `{"error":"ValueError"}`. Other exceptions indicate an execution problem, not evidence of a successful review. Every candidate must satisfy the whole user contract, including compatibility and nonmutation requirements. No network access or installation is needed.

