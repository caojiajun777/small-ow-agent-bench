In `/app/repo`, `export_rows()` should return the full table every time it is called in a process. A second export currently comes back empty.

Write a minimal Python script to `/app/repro.py` that reproduces this failure: it must exit with a non-zero status on the current repository, and exit 0 after the defect is fixed. Do not modify `/app/repo`. You have 180 seconds.
