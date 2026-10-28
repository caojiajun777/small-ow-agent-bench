# edit-pad-left: application repair

This is an authored synthetic benchmark scenario, not a claimed upstream GitHub issue.

Invoice text export: ordered column specs define key, integer width and optional one-character fill. Convert field values with str(), left-pad without truncating, join columns with separator (default ` | `), join rows with newline and no trailing newline. Negative widths leave text unchanged.

Repair both the existing primitive API `text.pad_left` and the application API `workflow.process(request)`. The JSON CLI is `python3 /app/repo/client.py`: one request on stdin, one JSON response on stdout. The primitive's original contract is retained below.

In `/app/repo/text.py`, implement `pad_left(text, width, fill=" ")`.

Return `text` left-padded with `fill` until its length is `width`. If `text` is already at least `width` characters, return it unchanged. `fill` is a single character.

Example request: `{"columns":[{"key":"id","width":3,"fill":"0"},{"key":"name","width":4}],"rows":[{"id":7,"name":"Ada"},{"id":1234,"name":"X"}]}`
Expected response: `"007 |  Ada\n1234 |    X"`

Preserve unrelated behavior and public interfaces. Do not edit tests or the CLI adapter; do not hardcode these examples. Public regressions: `python3 -m pytest /app/repo/tests -q`. Repository: `/app/repo`.
