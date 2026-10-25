# What it costs to read a solicitation into an outline, 2026-10-25

Each reading below used a new sample account in a throwaway database, so none of it came from a saved
copy. Times are wall clock around the import; token counts and costs are the provider's, read from the
run log. Regenerate with `python -m scripts.measure_outline_import`.

| Notice | Characters | Seconds | Items kept | Input tokens | Output tokens | Estimated cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| FWS Highlands F25AS00379 | 17,932 | 26.8 | 36 | 4,731 | 6,687 | $0.0039 |
| FHWA PPPP-26-001 | 12,292 | 21.3 | 27 | 3,664 | 5,175 | $0.0030 |
| NOAA-OAR-CPO-2026-33326 | 12,250 | 19.8 | 31 | 3,630 | 4,667 | $0.0028 |

**Median cost of one reading: $0.0030.** Median time: 21.3 s.

## Limits

- 3 reading(s), on one machine, on one day. Times include the network, so they vary.
- The item counts are what survived verification, not what the model proposed.

