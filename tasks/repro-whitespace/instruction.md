In `/app/repo`, `nums.parse_ints(text)` splits on commas and returns integers. `parse_ints(" 1, 2")` is supposed to be `[1, 2]` but currently is not.

Write a minimal Python script to `/app/repro.py` that reproduces this failure: it must exit with a non-zero status on the current repository, and exit 0 after the defect is fixed. Do not modify `/app/repo`. You have 180 seconds.
