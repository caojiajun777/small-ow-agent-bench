`/app/repo/order.py` implements `line_total(qty, price)`.

`qty` is an int or `None`. Quantity must be a non-negative integer when present.
Missing quantity is an error. Line total is quantity times unit price.
Details are on `line_total`.

Write unit tests in `/app/repo/tests/test_order.py`. Do not change `order.py`. You have 180 seconds.
