In `/app/repo`, `search.index_of(items, needle)` should return the first index of `needle`. `index_of(["a", "b", "a"], "a")` is supposed to be `0` but currently is not.

Write a minimal Python script to `/app/repro.py` that reproduces this failure: it must exit with a non-zero status on the current repository, and exit 0 after the defect is fixed. Do not modify `/app/repo`. You have 180 seconds.
