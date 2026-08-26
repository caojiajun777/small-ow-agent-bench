In `/app/repo`, attaching the same customer record to two orders must keep the orders independent. Renaming the customer on one order currently changes the other order too.

Write a minimal Python script to `/app/repro.py` that reproduces this failure: it must exit with a non-zero status on the current repository, and exit 0 after the defect is fixed. Do not modify `/app/repo`. You have 180 seconds.
