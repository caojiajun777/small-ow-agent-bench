In `/app/repo`, `quote(sku)` should follow `set_price`. After a price change in the same process, quotes still show the old amount.

Write a minimal Python script to `/app/repro.py` that reproduces this failure: it must exit with a non-zero status on the current repository, and exit 0 after the defect is fixed. Do not modify `/app/repo`. You have 180 seconds.
