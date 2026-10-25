# GrantBridge user test kit (10 to 15 minutes)

**Status on 2026-10-24: one test has been run.** A director at a small nonprofit working with at-risk young people used GrantBridge for 20 to 30 minutes, completed every task unaided, and gave seven observations that were all acted on; the record is in [`docs/evidence/user-test-2026-10-24.md`](evidence/user-test-2026-10-24.md). It was unmoderated, so the templates below were not used and no timings or quotations were captured — use them if you run another. Everything else in this repository is still a system timing, not a user result.

**Participant:** someone who works at or with a small nonprofit (grants, programs, or the executive director), or a knowledgeable proxy, such as a nonprofit-management student or someone who has written a grant before. Write down which one you had.

**Setup (before the participant arrives, 2 minutes):**

1. Start GrantBridge and open the public **About GrantBridge** page.
2. Have a stopwatch or phone timer ready, and this sheet printed or open.
3. Use **sample data only**. The participant uses the one-click sample demo organization (Harbor Lantern Tutoring Collective) and never enters real information.
4. Turn on **Practice mode** on the AI pages if you want the session to cost nothing. AI results will then be labeled MOCK; say so in your notes.

## 1. Consent (read aloud, about 1 minute)

> Thank you for helping. This session tests the software, not you; there are no wrong answers. It takes about 12 minutes. You will use a made-up nonprofit, so please do not type any real organization's or person's information. You can skip any task or stop at any time, for any reason. I will time each task and take notes. With your permission, I may quote you in a class report, without your name or organization. Is that all right?

- [ ] The participant agreed to take part.
- [ ] The participant agreed to be quoted, without their name. (If not, record no quotes.)
- [ ] Screen recording: **not used** / used with explicit permission.

Collect no name, email, or organization. Record the role only, such as "grants manager, small nonprofit" or "proxy: MPA student".

## 2. Task script (about 10 minutes)

Read each task as written. Do not demonstrate. Start the timer when you finish reading and stop it when the participant says they are done. Note where they hesitate.

| # | Task (read aloud) | Done when | Time limit |
|---|---|---|---|
| T1 | "You run a small tutoring nonprofit. Get set up with the demo organization, then find one grant that looks like a fit and save it." | A grant is saved | 3 min |
| T2 | "Decide whether this organization should pursue the Connecticut After-School Learning Grant. What would you still check before applying?" | They state a decision and at least one thing to verify | 3 min |
| T3 | "Your team has about 4 hours a week for grants. Which grants should you focus on, and why?" | They name the recommended grants and one reason | 2 min |
| T4 | "Start the application for that grant, get help writing one answer, then check what still needs verifying." | A reviewed answer with a visible checklist | 3 min |
| T5 | "Make a plan to finish this application on time." | A workback plan exists | 1 min |
| T6 (optional, if time allows) | "The New England Youth Opportunity Fund looks like a fit. Here are its award terms [the sample terms]. The organization has $30,000 of reserves and $10,000 of match money committed. Can it afford to win a $55,000 award? What would you ask the funder?" | They say whether it is affordable, with the reason, and name one question for the funder | 3 min |

## 3. Timing template: before and after

**Before (the participant's usual way, without GrantBridge).** Ask: "Using only the listing and your usual process, decide whether to pursue this grant. Think aloud." Give them the SAMPLE grant's listing text as a printout or a plain text file. Time it the same way. For T6, give them the sample award terms (`data/fixtures/award_notice_demo.json`, the `notice` text) and the same three numbers, and ask how much of the organization's own cash winning would tie up, and when.

| Task | Before: usual way (min:sec) | After: GrantBridge (min:sec) | Completed? (yes / partly / no) | Notes: hesitations, errors, workarounds |
|---|---|---|---|---|
| Decide whether to pursue (T2) | | | | |
| Choose what to focus on with limited hours (T3) | | | | |
| Draft and check one answer (T4) | | | | |
| Make a timeline (T5) | | | | |
| Decide whether winning is affordable (T6, optional) | | | | |

Report only what you measured, with **n** (the number of participants). With n = 1, write "one participant", not a percentage or an average.

## 4. Feedback form (about 2 minutes, after the tasks)

Rate each statement from 1 (strongly disagree) to 5 (strongly agree).

| Statement | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| I understood why GrantBridge recommended what it did. | | | | | |
| I could tell which information was verified and which was the AI's analysis. | | | | | |
| The "unknown" and "still to confirm" items were helpful, not confusing. | | | | | |
| I would trust a recommendation more because the rules are shown. | | | | | |
| The capacity view matches how my team actually plans grant work. | | | | | |
| I would use GrantBridge before deciding to apply for a grant. | | | | | |
| The cash-flow check (Can we afford to win?) showed me something I would have missed. | | | | | |

**Open questions** (write down the answers word for word only if quoting was allowed):

1. What was the most useful thing you saw today?
2. Where did you get stuck or feel unsure?
3. Was anything confusing, missing, or wrong for a real nonprofit?
4. What would make you trust the recommendations more, or less?
5. If you could change one thing, what would it be?

## 5. Measured self-test numbers (system timings, not user results)

These come from GrantBridge's own scripted browser runs and live checks on 2026-10-21, with sample data. They measure **software speed and cost**. They are **not** how long a person takes to do the tasks above.

| What | Measured | Source |
|---|---|---|
| Fresh clone to a running app | 59.3 s (final code; 41.5 s and 55.3 s on earlier code) | `docs/evidence/fresh-clone-test-2026-10-21.md` |
| One whole-proposal review (live AI) | 12.3 s, $0.00119 | `docs/evidence/proposal-review-before-after-2026-10-21.md` |
| Draft, review, three revisions, review again (live AI) | 7 calls, 44.2 s, $0.00356 | same |
| One workback plan (code only) | 0.8 s from click to saved plan; 27.3 ms in code | `docs/evidence/e2e-run-2026-10-21.md`, step F8 |
| Reading one award notice (live AI), then the cash result | 7.5 s and $0.00060 for the terms; the simulation, verdict, and what-if scenarios are code and cost nothing | `docs/evidence/e2e-run-2026-10-21.md`, steps A1 to A3 |
| Explaining those numbers in plain words (live AI) | 5.6 s, $0.00032, about 217 words | `docs/evidence/e2e-run-2026-10-21.md`, step A4 |
| One Should We Pursue? assessment (live AI evidence) | 3.4 s to 6.6 s, $0.00020 to $0.00028 | PROGRESS.md, Phase 4 |
| One mission-drift check (live AI) | 8 s to 12 s, $0.0005 to $0.0007 | PROGRESS.md, Phase 4b |

**Limitation to state in the report:** until a real participant is tested, GrantBridge has no evidence of user time saved, comprehension, or trust. The numbers above show only that the software runs fast and cheaply on sample data.
