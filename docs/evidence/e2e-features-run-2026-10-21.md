# GrantBridge end-to-end run

- Run: 2026-10-21 12:00 UTC · browser: msedge (headless) · app: http://localhost:8600
- Result: PASS (17 of 17 steps)
- Screenshots are of the real running app (account email masked). AI steps are live when the server has an API key; a MOCK label on screen means no AI was called.

| Step | What | Result | Seconds | Screenshot | Note |
|---|---|---|---|---|---|
| F0 | Set up: account, demo data, and two typed answers | PASS | 9.8 | — | new account, fictional demo data, answers typed for questions 1 and 3 |
| F1 | Review proposal: an advisory scorecard for the whole application | PASS | 21.5 | `docs/screenshots/e2e-F1-proposal-scorecard.png` | AI (live) review; checked: 5 rated dimensions; Average rating (advisory) 2 / 5 |
| F2 | Review proposal: what to improve first, and what is missing or unsupported | PASS | 0.0 | `docs/screenshots/e2e-F2-proposal-recommendations.png` | checked: 5 prioritized recommendation(s), each labeled funder requirement or best practice |
| F3 | Revise with AI: the suggestion before and after | PASS | 3.6 | `docs/screenshots/e2e-F3-revision-before-after.png` | checked: a revision suggestion shown beside the saved answer, labeled suggestion only |
| F4 | Use the revision and review again: the before-and-after comparison | PASS | 18.6 | `docs/screenshots/e2e-F4-review-comparison.png` | checked: the second review shows the before-and-after comparison |
| F5 | Budget & narrative: lines typed in, exact totals, and the checks | PASS | 7.3 | `docs/screenshots/e2e-F5-budget-lines.png` | checked: 3 lines typed in; code totals $23,000 with $21,000 requested; the mismatch is flagged |
| F6 | Budget narrative written from the lines only, checked by code | PASS | 8.2 | `docs/screenshots/e2e-F6-budget-narrative.png` | AI (live) narrative; checked: labeled, and marked as matching the current budget |
| F7 | AI Grant Advisor answers a budget question with the get_budget tool | PASS | 11.7 | `docs/screenshots/e2e-F7-advisor-budget.png` | AI (live) answer; checked: the trace shows the get_budget tool call |
| F8 | Timeline: a workback plan from the deadline, with its source labeled | PASS | 4.2 | `docs/screenshots/e2e-F8-timeline-plan.png` | checked: 7 steps shown; 0.6 s from the click to the saved plan in the browser, 22.0 ms of it in GrantBridge's code |
| F9 | Mark a step done, download the calendar, and see the next steps on the Dashboard | PASS | 3.6 | `docs/screenshots/e2e-F9-dashboard-next-steps.png` | checked: 1 of 7 steps done; the .ics file has 7 events (6 open steps and the deadline) and no alarms; the dashboard lists Document collection next |
| F10 | Should we pursue? A grant that fails a required rule | PASS | 9.7 | `docs/screenshots/e2e-F10-pursue-do-not-pursue.png` | checked: outcome Do not pursue, from the failed state rule; AI fit evidence |
| F11 | Should we pursue? Promising, with rules still to confirm | PASS | 8.6 | `docs/screenshots/e2e-F11-pursue-verify-first.png` | checked: outcome Promising, but verify first; 2 rules to confirm are listed; AI fit evidence |
| F12 | Confirm the listing's rules: the outcome becomes Strong candidate | PASS | 0.4 | `docs/screenshots/e2e-F12-pursue-strong.png` | checked: after the user confirmed both rules the outcome is Strong candidate, and they are listed as confirmed by the user; the AI fit evidence was reused (no new AI call) |
| F13 | Portfolio Strategist: recommended, deferred, and excluded grants, each with its reason | PASS | 11.6 | `docs/screenshots/e2e-F13-portfolio-recommended.png` | checked: recommended 3, deferred 1, excluded 1 (one marked not interested); Potential requests $75,000 |
| F14 | Lower the staff hours: the recommendation changes immediately | PASS | 3.0 | `docs/screenshots/e2e-F14-portfolio-less-capacity.png` | checked: at 3 hours a week the recommended grants went from 3 to 2, recomputed at once |
| F15 | Weekly capacity: scheduled hours against available hours, week by week | PASS | 0.1 | `docs/screenshots/e2e-F15-portfolio-weekly-capacity.png` | checked: the weekly chart and table are shown (0 week row(s) in the table) |
| F16 | Mission drift: concerns grounded in quotes from the grant and the profile | PASS | 13.8 | `docs/screenshots/e2e-F16-mission-drift.png` | checked: Mission drift for STEM Futures Mentoring Award: Moderate. AI use: gpt-6-luna · 1,273 input tokens (0 cached) + 1,039 output (413 reasoning) · estimated cost $0. |
