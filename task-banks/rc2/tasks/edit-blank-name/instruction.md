# edit-blank-name: application repair

This is an authored synthetic benchmark scenario, not a claimed upstream GitHub issue.

Profile API: missing name means guest; present values (including empty string and null) are retained exactly, without stripping or truthiness fallback. Return every user as `{id,display}` in request order, including intentionally blank profiles. Neither function may mutate input.

Repair both the existing primitive API `profile.display_name` and the application API `workflow.process(request)`. The JSON CLI is `python3 /app/repo/client.py`: one request on stdin, one JSON response on stdout. The primitive's original contract is retained below.

In `/app/repo/profile.py`, implement `display_name(user)`.

If the user has no name field, return `guest`. If they set a name, return that
name even when it is an empty string.

Example request: `{"users":[{"id":1},{"id":2,"name":""},{"id":3,"name":"Ada"},{"id":4,"name":null}]}`
Expected response: `[{"id":1,"display":"guest"},{"id":2,"display":""},{"id":3,"display":"Ada"},{"id":4,"display":null}]`

Preserve unrelated behavior and public interfaces. Do not edit tests or the CLI adapter; do not hardcode these examples. Public regressions: `python3 -m pytest /app/repo/tests -q`. Repository: `/app/repo`.
