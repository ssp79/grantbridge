# Newer AI features: measured cost per run, 2026-10-21

- **When:** 2026-10-21 12:19 UTC
- **Mode:** live: real model calls, fresh answers only
- **Model:** gpt-6-luna (served as `gpt-6-luna-2026-09-22`)
- **Repetitions:** 3 per workflow, each on a new fictional account in a throwaway database
- **How to repeat:** `python -m scripts.measure_new_features`

| Workflow | Runs | Model calls | Input tokens | of which cached | written to cache | Output tokens | of which reasoning | Time | Cost per run (min to max) |
|---|---|---|---|---|---|---|---|---|---|
| Proposal review | 3 | 1.0 | 2,066 | 0 | 2,063 | 1,161 | 85 | 10.1 s | $0.00084 ($0.00076 to $0.00096) |
| Revise one answer | 3 | 1.0 | 1,016 | 0 | 0 | 224 | 99 | 3.7 s | $0.00021 ($0.00019 to $0.00022) |
| Budget narrative | 3 | 1.0 | 1,244 | 0 | 1,241 | 498 | 223 | 7.2 s | $0.00040 ($0.00039 to $0.00043) |
| Pursuit assessment | 3 | 1.0 | 1,136 | 0 | 1,133 | 300 | 0 | 3.8 s | $0.00029 ($0.00027 to $0.00032) |
| Mission drift | 3 | 1.0 | 1,218 | 0 | 1,215 | 770 | 238 | 11.2 s | $0.00054 ($0.00050 to $0.00056) |

Calls that fell back to practice mode (not measured): 0.
Each figure is the provider's own usage report; the cost is an estimate at the rates in `data/pricing.json`.
