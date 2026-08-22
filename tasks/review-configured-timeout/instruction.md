Issue:
`get_timeout(cfg)` reads a timeout from a dict. If the `timeout` key is omitted, the result must be `30`. `get_timeout({})` must be `30`. Any value that is present in the dict must be returned unchanged.

The candidate change is already applied in `/app/repo`. Decide whether this repository fully addresses the issue.

Write a single character to `/app/answer.txt`: `1` if it fully addresses the issue, `0` otherwise. You may inspect and run code. Do not change the repository. You have 300 seconds.
