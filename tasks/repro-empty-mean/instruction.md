In `/app/repo`, `stats.mean(nums)` returns the arithmetic mean of a non-empty list. `mean([])` currently returns `0` instead of raising `ValueError`.

Write a minimal Python script to `/app/repro.py` that reproduces this failure: it must exit with a non-zero status on the current repository, and exit 0 after the defect is fixed. Do not modify `/app/repo`. You have 180 seconds.
