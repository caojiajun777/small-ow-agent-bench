# edit-slugify: application repair

This is an authored synthetic benchmark scenario, not a claimed upstream GitHub issue.

Content publishing: turn titles into unique routes in input order. Empty slugs use `untitled`; collisions append `-2`, `-3`, ... until globally unused (including collisions with literal suffixed titles). Keep IDs and prefix; never mutate posts. Letters/digits use Python Unicode `isalnum`; all Unicode whitespace separates words.

Repair both the existing primitive API `slug.slugify` and the application API `workflow.process(request)`. The JSON CLI is `python3 /app/repo/client.py`: one request on stdin, one JSON response on stdout. The primitive's original contract is retained below.

In `/app/repo/slug.py`, implement `slugify(text)`.

Rules: lowercase; replace spaces with hyphens; drop characters that are not letters, digits, or hyphens; collapse repeated hyphens; strip leading and trailing hyphens.

Example request: `{"posts":[{"id":1,"title":"Hi"},{"id":2,"title":"Hi"},{"id":3,"title":"Hi-2"},{"id":4,"title":"Hi"}]}`
Expected response: `[{"id":1,"path":"/posts/hi"},{"id":2,"path":"/posts/hi-2"},{"id":3,"path":"/posts/hi-2-2"},{"id":4,"path":"/posts/hi-3"}]`

Preserve unrelated behavior and public interfaces. Do not edit tests or the CLI adapter; do not hardcode these examples. Public regressions: `python3 -m pytest /app/repo/tests -q`. Repository: `/app/repo`.
