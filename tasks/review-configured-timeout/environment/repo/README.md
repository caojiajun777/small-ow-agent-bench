# layered request timeout configuration

The pre-change revision is `base`. Four independently applied candidate revisions are listed in `candidates.json`; names do not encode their correctness. Each revision has a service entrypoint plus its implementation modules.

## User contract

`config` is the stored configuration; optional `override` is a request-level dict. An explicitly present `override.timeout` wins, otherwise a present `config.timeout` wins, otherwise use `30`. Preserve present JSON values unchanged, including `0`, `false`, `null`, and `""`; they are not omissions. Return `{"timeout": value}`. Ignore unrelated config keys.

## Run without changing source

`printf '%s\n' '{"config":{}}' | python3 client.py --revision cedar`

Each input line is one JSON request. Each output line is its JSON result; a documented invalid value yields `{"error":"ValueError"}`. Other exceptions indicate an execution problem, not evidence of a successful review. Every candidate must satisfy the whole user contract, including compatibility and nonmutation requirements. No network access or installation is needed.

