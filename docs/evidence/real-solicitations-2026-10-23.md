# Reading three real federal notices, 2026-10-23

The solicitation import was run against three live federal funding notices, taken from the agencies
that published them. They were chosen because each one judges applicants in a different way, which is
the part that a summary of a document does not capture.

Nothing on this page is recalled. Each outline is the payload the import produced on the day, committed
under `data/fixtures/real_notices/`, and every figure below is produced by re-running the check over
those files: `python -m scripts.check_real_solicitations`. It needs no API key and no network.

## The notices

| Agency | Program | Opportunity number | Text read |
| --- | --- | --- | --- |
| U.S. Fish and Wildlife Service | Highlands Conservation Act Grant Program | `F25AS00379` | 17,932 characters |
| Federal Highway Administration | Pathways to Preventing Pedestrian Fatalities | `PPPP-26-001` | 12,292 characters |
| NOAA Climate Program Office | Earth's Systems and Sustainability Science Program | `NOAA-OAR-CPO-2026-33326` | 12,250 characters |

## What the import found in each

| Notice | Sections | Required elements under them | Scoring criteria | Objectives under them | Things to file | Registrations | Format rules |
| --- | --- | --- | --- | --- | --- | --- | --- |
| FWS | 11 | 41 | 3 | 6 | 10 | 4 | 4 |
| FHWA | 1 | 11 | 7 | 30 | 7 | 2 | 4 |
| NOAA | 8 | 31 | 5 | 11 | 9 | 3 | 7 |

**85 items in total**, before counting the required elements and objectives nested under them.
Each one was kept only because it carried a sentence from the notice.

## The check that matters: every quotation is really in the document

An item survives the import only when the sentence given for it appears in the notice word for word,
ignoring whitespace, and never when that sentence is wording aimed at an AI. Re-applying that rule now,
to every quotation in all three saved outlines:

- **240 quotations re-checked**
- **0 not found** in the notice they claim to come from
- **0 carrying wording aimed at an AI**

Nothing was invented.

### What a real document did to the injection detector

Reading these notices turned up something a made-up sample never would. The Fish and Wildlife notice
trips the prompt-injection patterns twice, and **neither hit is an attack**: it names a contact called
**Dan**, which matches the `DAN` jailbreak name, and it tells applicants to **send an e-mail to the
help desk**, which matches the pattern for sending data somewhere. The other two notices trip nothing.

That matters because a flagged phrase is used to throw an excerpt away. The phrase `Dan` is three
characters, and it had been compared as a bare substring, so any requirement containing *abundant*,
*guidance* or *redundant* would have been discarded as an injection, with nothing shown to the user.
Silently dropping a requirement is the exact failure this product exists to prevent. A flagged phrase
is now matched on word boundaries instead, which keeps the defense and drops the coincidence:
wording genuinely aimed at the model is still discarded, and a sentence that merely contains the same
letters is kept. `tests/test_real_solicitations.py` holds both halves of that.

No requirement was actually lost in these three runs: none of the kept excerpts contained the letters
in question. The bug was reachable, not triggered.

## Three ways of judging an application, each kept as the funder wrote it

No two of these notices score the same way, and none of them is a simple points total. The import
keeps each funder's own shape rather than flattening all three into one.

### U.S. Fish and Wildlife Service — 3 criteria, 6 objectives under them

Named ratings in place of a score:

- **Project Narrative clearly demonstrates the project has high conservation value / Project Narrative does not demonstrate that the project has high conservation value** — used for 1 criterion

Pass-or-fail gates, which the import keeps as thresholds rather than turning into scores:

- **Minimum Criterion 1: Eligible Project Location** — Project is either in the Highlands Region as defined in the NY-NJ Highlands Regional Study: 2002 Update and the Highlands Regional Study: Connecticut and Pennsylvania 2010 Update, or in a Municipality within the Highlands Expansion Opportunity Area that has been submitted by the Lead State Agency with Municipal concurrence and approved by the Service.
- **Minimum Criterion 2: 1:1 Cost Share** — 1:1 cost share.
- **Additional Criterion 3: High Conservation Value and Presidential and Department of Interior Priorities** — Projects that meet Criteria 1 and 2 and score 35 points or higher in Criteria 3 as determined by the Merit Review Panel will be eligible for funding.

### Federal Highway Administration — 7 criteria, 30 objectives under them

Named ratings in place of a score:

- **Highly Responsive / Responsive / Non-Responsive** — used for 4 criteria
- **Certain (3) / Somewhat Certain (2) / Unknown or Uncertain (1)** — used for 1 criterion
- **Complete (3) / Partially Complete (2) / Incomplete (1)** — used for 1 criterion

Pass-or-fail gates, which the import keeps as thresholds rather than turning into scores:

- **Statutory required uses of PPPP grants** — Applications that do not address all the statutorily required uses are ineligible for funding.

### NOAA Climate Program Office — 5 criteria, 11 objectives under them

Percentage weights, read from the notice, summing to **100%**:

| Criterion | Weight | Max points |
| --- | --- | --- |
| Importance/relevance and applicability of proposed projects to the program goals | 25% | 5 |
| Technical/scientific merit | 20% | 5 |
| Overall qualifications of applicants | 30% | 5 |
| Project costs | 15% | 5 |
| Engagement and Education | 10% | 5 |
| **Total** | **100%** | |

## Limits

- Three notices, read once each, on 2026-10-23. Nothing here is a rate, an average or an accuracy figure.
- This check proves every kept item is quoted from its notice. It does **not** prove the import found
  everything a notice requires. Nobody has yet compared one of these outlines against a funder's
  requirements line by line, and the outline is not a substitute for reading the notice.
- The text was extracted from each agency's PDF before the model saw it. A scanned notice with no text
  layer cannot be read this way, and GrantBridge says so rather than guessing.

