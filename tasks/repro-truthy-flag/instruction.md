In `/app/repo`, `flags.enabled(cfg)` returns whether the feature is on. If `on` is omitted, the result is True. If `on` is present, return its boolean value (`0` is False). `enabled({})` currently errors.

Write a minimal Python script to `/app/repro.py` that reproduces this failure: it must exit with a non-zero status on the current repository, and exit 0 after the defect is fixed. Do not modify `/app/repo`. You have 180 seconds.
