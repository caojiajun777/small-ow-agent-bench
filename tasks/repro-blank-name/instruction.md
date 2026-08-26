In `/app/repo`, a profile with no name should show `guest`. People who set an empty display name are currently shown as `guest` as well; they should stay unnamed.

Write a minimal Python script to `/app/repro.py` that reproduces this failure: it must exit with a non-zero status on the current repository, and exit 0 after the defect is fixed. Do not modify `/app/repo`. You have 180 seconds.
