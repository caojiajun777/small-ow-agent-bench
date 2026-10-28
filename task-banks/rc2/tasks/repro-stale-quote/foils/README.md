# Foils (verifier must score 0)

- `read-once`: never calls set_price after the first quote
- `clear-cache-private`: calls quote.cache_clear instead of the public setter path
