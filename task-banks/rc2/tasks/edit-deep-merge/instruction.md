# edit-deep-merge: application repair

This is an authored synthetic benchmark scenario, not a claimed upstream GitHub issue.

Deployment configuration: apply ordered dictionary `layers` from low to high precedence, recursively merging dictionaries and replacing all other values (including lists, false, null and zero). Return `{config,layers_applied}`. Inputs AND nested output must be independent: modifying returned data cannot change either input.

Repair both the existing primitive API `merge.deep_merge` and the application API `workflow.process(request)`. The JSON CLI is `python3 /app/repo/client.py`: one request on stdin, one JSON response on stdout. The primitive's original contract is retained below.

In `/app/repo/merge.py`, implement `deep_merge(left, right)`.

Return a new mapping. Nested dictionaries merge recursively. For any key whose value is not a dictionary on either side, the value from `right` replaces the value from `left` (lists are replaced, not concatenated). Do not modify `left` or `right`.

Example request: `{"layers":[{"db":{"host":"local","port":10},"tags":["a"]},{"db":{"port":20}},{"tags":[],"enabled":false}]}`
Expected response: `{"config":{"db":{"host":"local","port":20},"tags":[],"enabled":false},"layers_applied":3}`

Preserve unrelated behavior and public interfaces. Do not edit tests or the CLI adapter; do not hardcode these examples. Public regressions: `python3 -m pytest /app/repo/tests -q`. Repository: `/app/repo`.
