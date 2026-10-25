# Review My Proposal: a measured before-and-after example, 2026-10-21

- **When:** 2026-10-21 03:23 UTC
- **Mode:** live: real model calls through the course Portkey gateway, fresh answers only
- **Model:** gpt-6-luna (served as `gpt-6-luna-2026-09-22`)
- **Data:** the fictional Harbor Lantern demo organization and the SAMPLE grant's four questions, in a throwaway database. Questions 1 and 3 start from a rough draft written for this demo (see `scripts/measure_proposal_review.py`); questions 2 and 4 start blank.
- **How to repeat:** `python -m scripts.measure_proposal_review`

## The steps

| Step | Mode | Model calls | Input tokens (cached) | Output tokens (reasoning) | Estimated cost | Time |
|---|---|---|---|---|---|---|
| Draft question 2 | live | 1 | 936 (0) | 462 (0) | $0.00032 | 5.7 s |
| Draft question 4 | live | 1 | 928 (0) | 322 (0) | $0.00025 | 4.1 s |
| Review 1 (before) | live | 1 | 2,522 (0) | 1,741 (314) | $0.00119 | 12.3 s |
| Revise question 3 | live | 1 | 1,052 (0) | 318 (212) | $0.00029 | 5.0 s |
| Revise question 1 | live | 1 | 1,041 (0) | 279 (68) | $0.00027 | 3.8 s |
| Revise question 4 | live | 1 | 1,160 (0) | 311 (44) | $0.00030 | 3.9 s |
| Review 2 (after) | live | 1 | 2,678 (0) | 1,196 (236) | $0.00093 | 9.2 s |
| **Total** | | 7 | 10,317 | 4,629 | $0.00356 | 44.2 s |

Time is wall-clock time for the whole step, including GrantBridge's code checks.

## Code checks before and after (deterministic, no AI)

| Check | Review 1 (before) | Review 2 (after) |
|---|---|---|
| Unanswered questions | 0 | 0 |
| [NEEDS] placeholders | 1 | 4 |
| [VERIFY] markers | 0 | 0 |
| Answers over their word limit | 0 | 0 |
| Figures or names not in your records | 2 | 0 |

## The reviewer's ratings before and after (AI, advisory)

The same model reviewed the proposal and wrote the revisions, so a higher rating is not independent evidence that the writing improved. Ratings are not a prediction of funding.

| Dimension | Before | After | Capped by code (before / after) |
|---|---|---|---|
| Clarity | 3 | 4 | no / no |
| Specificity | 3 | 4 | no / no |
| Alignment | 3 | 4 | no / no |
| Evidence of impact | 3 | 4 | no / no |
| Completeness | 2 | 2 | no / no |
| **Average** | **2.8** | **3.6** | |

Statements the review could not support (quoted from the answers): 2 before, 0 after.

## The revisions

Each revision followed one recommendation from review 1 and was used as written.

| Question | Priority | Basis | Words before → after | Sentences changed | [VERIFY] markers added by code |
|---|---|---|---|---|---|
| 3 | high | funder requirement | 32 → 43 | 6 | none |
| 1 | high | funder requirement | 47 → 110 | 9 | none |
| 4 | medium | funder requirement | 133 → 173 | 3 | none |

## Limits of this example

- One run on one fictional application. It shows the workflow and its costs; it is not a study.
- The revisions were used without a person editing them. In the app, every revision is a suggestion that a person reads, edits, or discards.
- No user test has been run. Nothing here measures how real nonprofit staff would use the feature.
