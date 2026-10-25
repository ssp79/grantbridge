# Can We Afford to Win?: term-extraction evaluation, 2026-10-21

- **When:** 2026-10-21 18:59 UTC
- **Mode:** live: real model calls, fresh answers only; practice patterns as a baseline
- **Model:** gpt-6-luna (served as `gpt-6-luna-2026-09-22`)
- **Notices:** 5 fictional notices with expected terms written before any run (`data/fixtures/award_terms_eval.json`), 3 repetition(s) each
- **How to repeat:** `python -m scripts.measure_award_feasibility`

Each expected field is scored: **correct**, **missed** (stated but returned as unknown), **wrong** (a different value), **invented** (a value where the text states none), or **correctly unknown**. These are fictional notices written for this test, so the results show how the extraction behaves on clear, ambiguous, silent, and adversarial text, not how often it is right on real funders' notices.

## AI (gpt-6-luna), checked by code

| Outcome | Fields | Share |
|---|---|---|
| Correct | 63 | 42% |
| Missed | 0 | 0% |
| Wrong | 0 | 0% |
| Invented | 0 | 0% |
| Correct unknown | 87 | 58% |

| Notice | Correct | Missed | Wrong | Invented | Correctly unknown |
|---|---|---|---|---|---|
| A-reimbursement | 27 | 0 | 0 | 0 | 3 |
| B-advance-no-match | 15 | 0 | 0 | 0 | 15 |
| C-ambiguous | 6 | 0 | 0 | 0 | 24 |
| D-silent | 0 | 0 | 0 | 0 | 30 |
| E-injection | 15 | 0 | 0 | 0 | 15 |

## Fixed text patterns (practice mode, no AI)

These patterns were written by the same person who wrote the notices, with the notices in view. Their score is a baseline for comparison, not independent evidence that they work on other text.

| Outcome | Fields | Share |
|---|---|---|
| Correct | 21 | 42% |
| Missed | 0 | 0% |
| Wrong | 0 | 0% |
| Invented | 0 | 0% |
| Correct unknown | 29 | 58% |

| Notice | Correct | Missed | Wrong | Invented | Correctly unknown |
|---|---|---|---|---|---|
| A-reimbursement | 9 | 0 | 0 | 0 | 1 |
| B-advance-no-match | 5 | 0 | 0 | 0 | 5 |
| C-ambiguous | 2 | 0 | 0 | 0 | 8 |
| D-silent | 0 | 0 | 0 | 0 | 10 |
| E-injection | 5 | 0 | 0 | 0 | 5 |

## What code removed from the AI's answers

- Conditions whose quote was not in the notice: 0
- Numbers not found in their own quote: 0
- Conditions quoted from a sentence aimed at an AI: 0

## Cost per term extraction (live)

| Runs | Input tokens | Output tokens | Time | Cost per run (min to max) |
|---|---|---|---|---|
| 15 | 740 | 396 | 4.2 s | $0.00027 ($0.00010 to $0.00043) |

## The explanation step (live, on the fictional demonstration)

| Runs | Words | Figures replaced by code | Output tokens | Time | Cost per run |
|---|---|---|---|---|---|
| 3 | 109 | 1 | 253 | 5.8 s | $0.00032 |

Calls that fell back to practice mode (not counted as AI results): 0.
Token counts are the provider's own usage report; costs are estimates at the rates in `data/pricing.json`.
