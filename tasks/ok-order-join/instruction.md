`/app/inbox/orders.csv` has columns `id`, `status`, `sku`, and `qty`.
`/app/inbox/prices.csv` has columns `sku` and `price`.

1. Write `/app/work/ok.csv` with header `id,sku,qty,price,line_total` and one row for every order whose `status` is `ok`, in the original order. Join each row to `prices.csv` on `sku`. `line_total` is `qty * price` with two decimal places. Keep `price` with two decimal places.
2. Write `/app/work/ids.txt` with those rows' `id` values, one per line, in the same order.
3. Write `/app/summary.txt` with two lines: the number of those ids, then the sum of `line_total` with two decimal places. Each line ends with a newline and nothing else.

Create `/app/work/` if it does not exist.

You have 240 seconds to complete this task.
