# GrantBridge progress log

Kept for Sam while work runs autonomously. The newest entries are at the bottom of each phase. Every result here comes from a real run; nothing is estimated or invented.

## The five phases (the order the work follows)

1. **Stability and evidence:** tests, a scripted end-to-end browser run, real screenshots, the evidence manifest, and a fresh-clone test.
2. **Interface polish:** visual system, navigation, empty, error, and loading states, plain language, accessibility, and phone layout.
3. **Features, one at a time:** Proposal Quality Reviewer, then Budget & Narrative, then the Application Timeline (deadline and workback planner).
4. **Signature feature:** the Grant Pursuit Advisor ("Should we pursue this grant?").
5. **Deliverables:** README, competitor matrix and user-test kit, `report.html`, `slides.html`, `submission_audit.md`, and the GitHub and Canvas checklist.

## Phase 1: Stability and evidence

- [x] Baseline browser run on the pre-redesign app: no crashes, exceptions, or console errors. One bug found: a used draft was still offered as a suggestion. Fixed.
- [x] Scripted end-to-end run, `scripts/e2e_scenario.py`: **PASS, 21 of 21 steps** (2026-10-21 UTC), with live AI and live Grants.gov. It covers sign-up, the dashboard, sample and live search, saving a live grant, an AI explanation, the advisor with tools, the trace and cost, facts, draft, review, the checklist, usage, phone width, and the malicious grant. Log: `docs/evidence/e2e-run-2026-10-21.md`.
  - **Problems the run found and fixed:**
    - My first selector clicked the wrong "Search" button (a script fix).
    - The segmented-control option was not a "button" (a script fix).
    - Some step notes claimed things the script never checked. Every note now reports only what was measured, such as page width on the phone.
    - OneDrive briefly locked new screenshots. The script now retries.
- [x] `evidence_manifest.md`: every screenshot with what it proves and its status. None is simulated.
- [x] **Fresh-clone test with `.env` one folder above the repo: PASS** (2026-10-21 UTC). Details: `docs/evidence/fresh-clone-test-2026-10-21.md`.
  - From an empty clone to a running app took **55.3 s**: 2.8 s venv, 51.4 s pip install with no cache, 0.9 s start.
  - The key check found the key in the **parent-folder .env**, and **445 tests passed** inside the clone.
  - The snapshot has no `.env` or `.db` files, 135 files, and is 9.6 MB.
  - **Attempt 1 failed:** the Windows 260-character path limit, while pip unpacked pyarrow. The README now tells Windows graders to clone into a short folder.
  - **Attempt 2 proved less than it seemed:** it passed, but the key came from this computer's own `PORTKEY_API_KEY` environment variable, not the parent `.env`. Attempt 3 removed both keys from the shell first. My first version of that change had a line that would have printed a key's value if one had been set. I caught it before the run, and it never ran; the fixed line prints only "set" or "unset".

## Phase 2: Interface polish

- [x] Theme in `.streamlit/config.toml`: navy sidebar, teal actions, warm off-white page, white cards, high-contrast badge colors. Minimal CSS for visible keyboard focus and card backgrounds.
- [x] Navigation: Dashboard, Find Grants, Saved Grants, Applications, AI Grant Advisor, Organization Profile, Account.
- [x] **New Dashboard:**
  - Three compact onboarding steps (Done / Next step / Later, in words and icons) with one primary action.
  - Profile completeness, plus saved grants and applications in progress.
  - Deadlines from Grants.gov or the user only, never sample dates.
- [x] **New Saved Grants page,** with an empty state and "Start application".
- [x] **Grant cards** show the name, Funder / Award / Deadline, a plain fit verdict, and requirements to check yourself. Actions: Start application (primary), Save, Explain fit (AI). The details are in expanders.
- [x] **Saving and the advisor:** live Grants.gov grants can be saved as dated copies, and "Ask the AI Grant Advisor about this grant" appears on cards and in the workspace.
- [x] **Applications workspace:**
  - A header card with source and provenance.
  - A "Needs your attention" box.
  - The answer beside the AI help panel.
  - Review and verification below.
  - Used drafts are labeled.
- [x] **Advisor:** a welcoming intro and starter questions. Answers are split into the AI answer, "From your records" (with sources), and "Still to verify". Agent steps, tokens, and cost are in a collapsed "Technical details" section.
- [x] **Sign-in:** a branded card, and an honest "Forgot your password?" note that never asks for or checks an email.
- [x] Before and after screenshots are saved (`docs/screenshots/before-*.png`, `after-*.png`).
- [x] **Tests: 443 passed** after the polish. New tests cover first-run onboarding, deadline sources, Saved Grants, live saves, used drafts, and forgot-password.

## Phase 3: Features (one at a time)

- [x] **Proposal Quality Reviewer ("Review my proposal")**, a new **Review proposal** tab in each application (`grantbridge/proposal_review.py`):
  - **What it does:**
    - An advisory scorecard rates clarity, specificity, alignment, evidence of impact, and completeness from 1 to 5. Each rating has its explanation and a basis: a quoted funder requirement, or best practice.
    - It lists unanswered questions, missing information, and unsupported statements, and gives up to six prioritized recommendations.
    - **Revise question N with AI** creates a suggestion only, shown before and after. A second review shows the change (`drafting.revise_section`).
  - **Code rules over the AI's output:**
    - Completeness is capped at 2 while a question is unanswered, and at 3 while markers remain. Evidence is capped at 3 while unsupported figures remain.
    - A requirement the funder never stated is relabeled best practice, and a quote not in the answers is dropped.
    - An invented figure is replaced with "[a figure you can document]", and a funding prediction is removed.
  - **Tests:** 35 new tests (`tests/test_proposal_review.py`), 4 new page tests, and 2 new isolation cases. They cover:
    - missing data
    - the caps
    - an invented requirement, statistics, or quote
    - prediction removal
    - injected text in the grant and in an answer
    - contact-detail redaction
    - model failures
    - the trace and its cost
    - the comparison
    - revisions, and access from another account
  - **Full suite: 484 passed** (2026-10-21).
  - **Live checks** (gpt-6-luna; details in `docs/evidence/proposal-review-before-after-2026-10-21.md`):
    - **Strict schema:** Azure accepted it. One review used about 2,000–2,700 input and 1,200–1,750 output tokens, $0.00093–0.00119, in 9–13 s.
    - **Before and after (one run, sample data):** figures or names not in the records went from 2 to 0, and quoted unsupported statements from 2 to 0. `[NEEDS]` placeholders went from 1 to 4: the AI asked for facts instead of inventing them. The full loop took 7 calls, $0.00356, and 44 s.
    - **No guard had to intervene:** no caps, relabels, or replaced figures. The guards are exercised by the adversarial tests.
  - **Browser:** the `--features-only` E2E run passed 5 of 5 steps, with real screenshots `e2e-F1` to `e2e-F4`.
  - **Fixed along the way:**
    - The practice-mode toggle moved to the application header, so one switch covers facts, drafts, reviews, and revisions.
    - Answers shown as markdown in the Version history and the Export preview could have loaded a remote image if an answer held pasted image markdown. A new page test caught this, and both now use the external-text sanitizer.
- [x] **Budget & Narrative**, a new **Budget & narrative** tab (`grantbridge/budget.py`):
  - **Lines:** each line has a category, description, quantity × unit cost, who pays (this grant, or a cash or in-kind match or other funding, each committed or pending), who provides it, and a justification. Lines can be added, edited, and removed.
  - **Arithmetic:** exact, in whole cents with decimal quantities, done in Python.
  - **Checks:**
    - the amount requested, with the exact difference
    - the grant's listed range and the profile's annual budget
    - missing justifications and match money with no named source
    - pending money, $0 lines, and possible duplicates
    - the indirect share (stated as a fact to check, not a rule)
  - **The narrative** is written from code-formatted figures only. Code marks any other figure `[VERIFY]`, removes sentences that call pending money committed or claim committed money the budget does not have, lists lines it never mentions, and marks it out of date when the budget changes. *Use as a suggestion* puts it on the Write answers tab as a draft.
  - **The budget is the organization's own evidence:** drafts, revisions, and the proposal review see a `<budget>` block, and the `[VERIFY]` checks accept its figures.
  - **The advisor has a sixth tool, `get_budget`.** Practice mode recognizes budget questions too.
  - **Tests:** 51 new tests (`tests/test_budget.py`), 4 new page tests, and 6 new isolation cases. They cover:
    - exact rounding, validation (15 kinds of bad input), editing, and the line limit
    - every check
    - invented costs, matches, and commitments; pending money kept as pending
    - injected funder text; predictions
    - model failures, staleness, and the trace (no budget text in it)
    - the budget as evidence, the draft suggestion, and the advisor tool, including access from another account
  - **Also new:** a test that fails if any `*INSTRUCTIONS` prompt is missing from the prompt-leak guard. The budget prompt had not been registered until I added it.
  - **Full suite: 545 passed**, then 546 with that guard test (2026-10-21).
  - **Live (gpt-6-luna):** one narrative from 5 lines used 1,483 in / 728 out tokens, $0.00055, 8.9 s. It copied every figure exactly, kept pending money pending, left `[NEEDS]` for the line without a justification, and code flagged nothing.
  - **Browser run:** `e2e-F5` to `e2e-F7` passed; F7 shows the advisor calling `get_budget`.
  - **Fixed along the way:**
    - Identical budget lines would have crashed the page (duplicate widget IDs). Form widgets now have keys, and a page test covers it.
    - The metric labels were truncated; they are now "Committed match & other" and "Pending match & other".
    - The F5 step's note claimed a check it did not make; it now checks.
- [x] **Application Timeline** (deadline and workback planner), a new **Timeline** tab (`grantbridge/timeline.py`):
  - **The deadline's source is always shown:** From Grants.gov (with its copy date), a SAMPLE example date (not a real deadline, practice plans only), or Entered by you. A corrected date shows the Grants.gov date beside it. With no deadline there is no plan, and a passed deadline is refused.
  - **The plan:** seven steps with editable default days. When time is short, the submit-early margin shrinks first, then every step in proportion.
  - **Flags:** overdue, out of order, after the deadline, a changed deadline, squeezed below half the default, and no submit-early margin.
  - **Editing and sharing:**
    - Steps can be marked done and re-dated; rebuilds keep done steps.
    - `.ics` export: all-day events, no alarms, folded and escaped per RFC 5545.
    - Dashboard **Next steps**, and the advisor's `get_application_state` includes the next step.
    - The page says plainly that GrantBridge sends no reminders.
  - **Fixed along the way:**
    - The due-date note and the dashboard's deadline reminders called any date on a Grants.gov application "the close date Grants.gov listed", even after the user changed it. Both now use one provenance function. Practice applications never appear as reminders.
  - **Tests:** 22 new tests (`tests/test_timeline.py`), 3 new page tests with a pinned clock, and 5 new isolation cases. They cover:
    - provenance in every case; scheduling with ample, partial, short, zero, and passed time
    - assumption validation; the trace (code steps, no tokens, no titles or dates)
    - done and edited steps; every flag
    - the calendar file; the dashboard; the advisor; deletion
  - **Full suite: 576 passed** (2026-10-21), with no warnings.
  - **Browser:** the `--features-only` run passed 10 of 10 steps (`e2e-F8`, `e2e-F9`). The run checked that the downloaded `.ics` file has 7 events and no alarms. The plan took 0.6 s from click to saved plan, 16.5 ms of it in code.

## Phase 4: Grant Pursuit Advisor

- [x] **"Should We Pursue?"**: a new page in the navigation, also reached from every grant card, Saved Grants, and the application header (`grantbridge/pursuit.py`, `app_pages/pursue.py`).
  - **Six dimensions:** eligibility (met, failed, unknown, or not checkable, with user confirmations), strategic fit, readiness (verified requirements apart from best practice), time and capacity (editable hours and staff hours a week), budget feasibility, and proposal quality.
  - **Explicit rules:** four outcomes from rules listed on the page. Code decides; the AI writes only fit evidence, as quotes verified on both sides.
  - **Safeguards in the rules:** never "Strong" with an unknown or unconfirmed eligibility item; missing information is never treated as ineligibility; a failed check cannot be confirmed away.
  - **Live grants:** Grants.gov receives only the opportunity id. Its own funding categories are compared, and a changed close date is pointed out.
  - **Cost:** fit evidence is reused when nothing it reads changed.
  - **Tests:** 24 engine tests (`tests/test_pursuit.py`), 6 page tests (`tests/test_pursue_page.py`), and 2 isolation cases. They cover:
    - the demo scenarios
    - missing profile data, unknown requirements, unconfirmable failures
    - passed deadlines and capacity (no time, tight time)
    - a rolling deadline; a missing budget or draft
    - contradictory amounts and an over-budget request
    - the live path (only the id is sent); Grants.gov down; a changed close date
    - an injected listing; AI quote checks, predictions, and invented figures
    - fit reuse, model failures, the trace, another account, an own application, and the history limit
  - **Found by tests:** the new prompt had not been registered with the prompt-leak guard; the guard test failed until it was.
  - **Demo scenarios** (sample Harbor Lantern profile):
    - sample-01 **Promising, but verify first**, then **Strong candidate** once the user confirms its two listing rules;
    - sample-05 **Promising, but verify first**;
    - sample-08 **Proceed with caution** (the request is above the maximum award);
    - sample-07 **Do not pursue** (Texas, Oklahoma, Louisiana, and New Mexico only).
  - **Live (gpt-6-luna):** sample-01 had 4 fit points, all quotes verified, $0.00028, 6.6 s; sample-07 had 3 gaps, $0.00020, 3.4 s.
  - **Browser:** `e2e-F10` to `e2e-F12` passed; F12 reused the fit evidence.
  - **Limitation noted:** the fit indicator is a word-level signal. For sample-07 it says "Good" (a shared Education focus) while the AI evidence points out the adults-versus-students mismatch. The card now says it is word-level, and the Mission Drift Detector (Phase 4b) compares populations and activities properly.

## Phase 4b: Grant Portfolio Strategist (requested 2026-10-21): done

A new **Portfolio Strategist** page (`grantbridge/portfolio.py`, `grantbridge/mission_drift.py`, `app_pages/portfolio.py`). It reuses the profile, saved grants, Should We Pursue? (eligibility, confirmations, fit, effort, and deadline provenance), budgets, timelines, and the AI Grant Advisor.

- [x] **Nonprofit Capacity Optimizer:**
  - **Inputs:** your staff hours a week; hours per application, estimated from editable assumptions (shared with Should We Pursue?) or entered by you; and commitments (applications marked Drafting, plus work you enter).
  - **The schedule:** earliest-deadline-first, day by day on weekdays, in Python. It is the schedule that meets every deadline whenever any can.
  - **The weekly view:** a chart with alt text and an accessible table: available hours, scheduled hours, use, deadlines, and status (OK, Full, or Conflict with the hours short). User-provided figures and estimates are labeled apart.
- [x] **Grant Portfolio Optimizer:**
  - **Candidates:** saved grants and grants still being researched.
  - **Excluded:** not interested, a failed required check, a passed deadline, or (optionally) a high drift concern.
  - **Score:** five components weighted by your sliders: fit, eligibility certainty, potential request, low effort, and mission alignment.
  - **Selection:** a transparent rule. "Must pursue" first, then by score; each grant is kept only if every deadline still fits the weekly hours. Otherwise it is deferred with the exact reason: hours short before which date, or which planned work it would push late.
  - **Interactive:** sliders, hours, and decisions recompute at once.
  - **No probabilities:** "Potential requests" is labeled as requests, not expected or guaranteed awards.
- [x] **Mission Drift Detector:**
  - **What code checks:** geography (eligible states), focus mismatch, and the listing's own obligation rules.
  - **What the AI adds:** concerns in five areas (activities, population, geography, resources, obligations), each rated low, moderate, high, or unknown, with a grant quote, a profile quote, and an uncertainty note.
  - **Rules over the AI:** a rated concern needs a verbatim grant quote of at least 8 characters, or it is dropped. Profile quotes that are short or JSON fragments are removed. A code-checked geography fact overrides the AI. Predictions and invented figures are scrubbed. The overall level is computed by code.
  - **Reuse:** results are reused when nothing they read has changed.
- [x] **The advisor's seventh tool, `get_portfolio`,** reports the code's recommendation and never invents another. Practice mode recognizes "which grants should we prioritize?". **Should We Pursue?** now defaults to your portfolio capacity.
- **Tests:**
  - 21 portfolio tests, including the EDF case where a priority order would miss a deadline.
  - 11 drift tests.
  - 6 page tests.
  - 7 new isolation cases.
- **Full suite: 653 passed** (2026-10-21).
- **Live (gpt-6-luna) mission-drift checks:**
  - sample-01: **Low**, $0.00054
  - sample-07: **High** (activities, population, geography), $0.00049
  - sample-04 STEM: **Moderate** (a STEM-time requirement; grades 6 to 12 against 3 to 8), $0.00064
- **Browser:** the feature run passed F0 to F16 (17 of 17), including F13 to F16 for the strategist.
- **Found and fixed:**
  - A code-checked geography fact did not override the AI when the AI's quote was also invalid; the override now comes first.
  - A selectbox in the E2E script needed keyboard selection.
  - Quotes like `"staff_fte": 3` slipped through as profile evidence; they are now dropped.

## Phase 4c: About GrantBridge and the public landing page (requested 2026-10-21): done

- [x] A public About page (`app_pages/about.py`, no sign-in): hero, mission, what makes GrantBridge different, the eight features (every one works today), six linked steps, and responsible AI. Its trust claims are only ones the code supports, such as Argon2id password hashes, per-account checks on every read and write, and contact details removed before text reaches the model.
- [x] Signed-out visitors land on it, with **Get started**, **Create an account**, and **Sign in**. Signed out, the router registers only About and Sign in, so no private page can even be opened. Signed in, About GrantBridge is first in the sidebar.
- [x] A sample Should We Pursue? example (`pursuit.example()`): the real rules on the sample demo profile and a SAMPLE grant, computed in memory with no account, no stored data, and no AI call. It shows *Promising, but verify first*, and what confirming the two open rules would change.
- [x] **Tests:** 20 About-page tests. They cover:
  - the page loads signed out;
  - each button opens the right sign-in tab;
  - signing in lands on the Dashboard;
  - no private page is registered for visitors (one case per page);
  - every private page checks the session itself;
  - the page reads no account data;
  - signed-in users find it with working links.
- **Full suite: 673 passed** (2026-10-21, `docs/evidence/test-run-2026-10-21.md`).
- **Found and fixed:**
  - Logging out landed on About, so the "logged out" message never showed. Sign in is now the default page while a message is waiting.
  - A test meant to check `require_user()` matched a comment. It now checks the call itself.

## Phase 5: Deliverables: done (2026-10-21)

- [x] **README:** prerequisites, install, start, and test commands, the parent-folder `.env`, what to do if the staff key fails, a 10-minute demo flow, the architecture, every feature, and the project layout.
- [x] **`docs/COMPETITORS.md`:** seven products' own pages, read on 2026-10-21, every statement labeled a vendor claim. **`docs/USER_TEST.md`:** a 10 to 15 minute test kit. No test has been run.
- [x] **New cost measurement** of the newer AI features (`scripts/measure_new_features.py`): 15 live calls, none from a cache. With them, the model cost is $0.058 per account per month, or $575 at 10,000 accounts (`docs/TOKENOMICS.md`, section 6b).
- [x] **`report.html` and `slides.html`,** built by `python -m scripts.build_deliverables` from the evidence files, so every figure comes from a file in the repository.
  - The report has the eight required sections and prints at 13 letter pages.
  - The deck has 10 slides, with keyboard navigation.
  - Both open offline, with 0 network requests (measured in a browser), and the report fits a 390 px phone screen.
  - The build stops if a quoted figure is no longer in its source file.
- [x] **Final browser run: PASS, 40 of 40 steps** (2026-10-21 16:45 UTC, live AI and live Grants.gov, two fresh servers).
  - **It found one app bug.** When the AI reviser rightly changed nothing (it kept a `[NEEDS]` placeholder it had no facts for), the page still announced a suggestion "ready below", and nothing appeared. Now nothing is saved, and the page says the reviser suggested no changes, with its note. Two regression tests cover it.
  - **It also found five test-script problems,** all fixed:
    - checks that counted before Streamlit had finished drawing the page;
    - a wait that matched an earlier answer;
    - a row count that could not work on a lazily drawn table;
    - an icon name in a note;
    - a check of the wrong advisor answer.
- [x] **Full suite on the final code: 675 passed** (2026-10-21, 17:07–17:12 UTC), with no warnings.
- [x] **Fresh-clone test on the final code: PASS.** 41.5 s from an empty clone to a running app, the key found in the parent-folder `.env`, and 675 tests passed inside the clone (`docs/evidence/fresh-clone-test-2026-10-21.md`).
- [x] **`submission_audit.md`:** the rubric crosswalk, a scan of what a first commit would contain, the GitHub commands (not run), and the Canvas checklist.
- **Earlier four-feature request:** it was merged into the three-feature specification.
  - Grant Readiness Assessment → the readiness dimension of Should We Pursue?
  - Application Requirements Checklist → the Requirements & source tab, the "Needs human verification" checklist, and Should We Pursue?'s "What we still need to know".
  - Proposal Quality Review → Review proposal.
  - Budget Narrative Assistant → Budget & narrative.

## Phase 6: Can We Afford to Win?, the editorial redesign, and the final deliverables (requested 2026-10-21): done

- [x] **Can We Afford to Win? (Grant Award Feasibility Analyzer)**, the second tab of Should We Pursue?, also opened from an application's Budget & narrative tab.
  - The AI lists the award's conditions with quotes. Code keeps a condition only if its quote is word for word in the listing or the pasted notice and its numbers are inside the quote, and it never takes a term from a sentence aimed at an AI. Everything else stays unknown.
  - Code does all the arithmetic: the match, a day-by-day cash simulation against the organization's reserves, the verdict (affordable, tight, a burden only from known terms), what-if scenarios, unrecovered overhead, report hours, and staff share.
  - It feeds Should We Pursue? (a caution rule) and, if switched on, the Portfolio Strategist, which then defers grants that would strain cash. It never excludes a grant on an unknown term.
  - Notices are pasted, never uploaded: the existing no-uploads security rule stays.
  - **Live evaluation** (`docs/evidence/award-feasibility-eval-2026-10-21.md`): 5 sample notices with expected terms written first, 3 runs each. 63 terms correct, 87 correctly unknown, 0 missed, 0 wrong, 0 invented. $0.00027 per notice read, $0.00032 per explanation.
- [x] **About page redesign:** an editorial look (ivory, navy, teal, sand, sage; serif headings), a licensed Unsplash photo saved locally with its license record (`assets/photos/ATTRIBUTION.md`), a real product screen (`assets/previews/`, re-created by `scripts/capture_preview.py`), and a second live sample example, *Can we afford to win it?*. Checked at 1440 and 390 px: no sideways scrolling, the photo loads with its alt text.
- [x] **Bugs the browser runs found, all fixed with tests:**
  - Installments paid only the advance until after the final report, so "half in advance" looked worse than reimbursement while the summary said it helped. Installments now follow the payment schedule, payment dates follow the calendar (no one-day period at the end), and the summary states the assumption.
  - The leak guard cut a sentence the explainer is told to write ("this is financial feasibility only…"), leaving "[removed: internal instructions]". The sentence is now registered as instructed wording, and a real prompt dump is still cut.
  - A negative amount showed as "$-28,411", a demo caption's dollar signs rendered as math, and the closing band's Sign in button was navy on navy.
- [x] **Report and slides:** the report covers the analyzer in sections 2 to 8 (the cash-flow problem with sourced figures, the differentiation table, the architecture, measured cost, safety, the evaluation, limits). The slides moved to reveal.js 5.1.0, inlined (no CDN), in the course's order. `report.pdf` and `slides.pdf` are printed by `scripts/print_pdfs.py`.
- [x] **Differentiation review** (`docs/COMPETITORS.md`): the seven products' pages were read again for award terms and cash flow, and every quote was checked in the page's own HTML. None describes simulating one grant's cash needs against reserves. The closest are GrantStation's organization-wide readiness self-assessment, Instrumentl's post-award tracking, and Grantsights' free match-gap calculator. No "first" or "only" claim is made.
- [x] **Demo video:** `scripts/record_demo.py` records a captioned tour of the running app with sample data and live AI (2 min 56 s at 1280 x 720, `demo-video/grantbridge-demo-2026-10-21.webm`). It is an automated recording with captions and no narration, submitted on its own (`demo-video/` is not committed).
- [x] **Full suite: 724 passed** in 7 min 58 s (19:02 to 19:10 UTC), with no warnings.
- [x] **Final browser run: PASS, 48 of 48 steps (19:11 UTC)** (two fresh servers, live AI and live Grants.gov), including the public *Can we afford to win it?* example and seven new steps, A1 to A7.
- [x] **Fresh-clone test: PASS.** 59.3 s from an empty clone to a running app, the key found in the parent-folder `.env`, and 724 tests passed inside the clone (`docs/evidence/fresh-clone-test-2026-10-21.md`).

## Phase 6b: the live example did not look live (found by Sam, 2026-10-21): done

Sam opened the app, could not find the sliders, and said the controls did not look interactive: "it's a picture not an interactive slider". He had in fact reached the right screen. Two causes, both fixed:

- **Streamlit's tabs render as plain words** with a hairline under the active one. Nothing marked them as controls, on the landing page or signed in. They now sit on a tinted track, with a resting shape and a filled active tab (`[role="tablist"]` in `grantbridge/ui.py`; Streamlit 1.66 draws tabs with react-aria, not baseweb, so the first selectors I wrote matched nothing).
- **The live example followed a full-width screenshot** of the app, which taught the reader that this part of the page is a picture. The example now comes *before* that screenshot, inside a teal-outlined card, under a banner that says "This part is live, not a picture", with "Pick a question:", "Move this switch:", and "Drag these, and watch the numbers below change:" above the controls.

Checked at 1440 px and 390 px: no sideways scrolling, and the example fits the phone screen. 724 tests pass.

**Worth remembering:** this is the first time someone other than me used the interface, and the first thing they tried failed. It is the clearest argument in the repository for running the real user test.

## Phase 7: the public website, the application's look, and reading the funder's own documents (2026-10-22 to 23): done

Sam asked for a real multi-page public site, a usability pass, one shared design system, a Getting Started page,
and then two features: creating an application from the funder's own solicitation, and reviewing a draft against
the requirements that came out of it.

- [x] **Five public pages, each at its own URL**, with a real horizontal top bar: Home, About Us, Try Features,
  How It Works, and Trust & Responsible AI, plus Sign in (`st.navigation(position="top")`). They stay registered
  after signing in, so no link dead-ends. `tests/test_public_site.py` (51 tests) replaced `test_about_page.py`.
- [x] **One design system** across the public site and the application: ivory, navy, teal, sand and sage, set in
  `.streamlit/config.toml` where Streamlit allows it and in `grantbridge/ui.py` for the rest, on an 8px spacing
  scale. Every palette pair was checked for WCAG AA contrast. Running prose is held to about 70 characters.
- [x] **Guided setup** (`app_pages/setup.py`) and a permanent, revisitable **Getting Started** walkthrough
  (`app_pages/getting_started.py`) that reads the same progress.
- [x] **Solicitation import.** `grantbridge/documents.py` reads real PDF, DOCX and TXT uploads: the type comes
  from the file's first bytes, not its name; 8 MB, 80 pages and 3 documents per import; the bytes are read in
  memory and never written to disk or executed; a scanned PDF with no text layer is refused with an explanation.
  `grantbridge/solicitation.py` extracts questions, deadlines, award ranges, matches, eligibility rules and
  attachments, and **code keeps only what the document states**: an item survives only if its excerpt is in the
  document word for word and every number in it appears inside that excerpt. Nothing is written until the user
  confirms it on the review screen, and an import never overwrites a title, funder, due date, question or
  requirement already there.
  - This was a deliberate, narrow exception to what had been a blanket no-uploads rule, authorised by Sam. The
    test that used to fail the build if `st.file_uploader` appeared anywhere was **rewritten, not deleted**, into
    tests of the new restrictions, and `docs/SECURITY.md` now documents them.
  - Measured on a real one-page PDF with live AI: every field and all three questions correct, nothing dropped,
    nothing invented, 7.2 s, $0.0007.
- [x] **Requirement-by-requirement proposal review.** The review now reports each requirement the funder set as
  addressed, partly addressed, needing verification, or not found. A row may say addressed **only** when the
  review quotes a sentence from the user's own answer; without that quote the row falls back to "not found in
  your answers" and the page says how many were moved. A quote from an answer that still carries a `[NEEDS]` or
  `[VERIFY]` marker becomes "needs verification". Practice mode uses a stated word-overlap formula with a floor,
  so a two-word requirement cannot match on one shared word.
- [x] **Log out** is now on the Account page as well as the sidebar, beside the separate "Log out everywhere".
- [x] **"Fictional" is gone from the product and the deliverables**, at Sam's request: the demo organization is
  "Harbor Lantern Tutoring Collective (sample)", and sample data is called sample or illustrative throughout.
  Dated evidence files from earlier runs keep their original wording, because they are records of what happened.
- [x] **Full suite: 831 passed** in 6 min 34 s, with no warnings (`docs/evidence/test-run-2026-10-23.md`).
- [x] **Final browser run: PASS, 51 of 51 steps** (2026-10-23 06:20 UTC, two fresh servers, live AI and live
  Grants.gov), including three new steps that upload a real PDF solicitation, confirm the review screen, and
  check the answers against the imported requirements (`docs/evidence/e2e-run-2026-10-23.md`).
- [x] **Demo video re-recorded** for the new site: 3 min 15 s at 1280 x 720,
  `demo-video/grantbridge-demo-2026-10-23.webm`.
- [x] **Report, slides and evidence rebuilt** from the new runs. `report.html` is 15 letter pages.

**Problems this phase found and fixed (all mine):**

- `repo.update_application` writes only status, due date, amount and notes, so the import's title and funder were
  silently dropped. Added `repo.fill_blank_application_fields`, which writes those two **only** where they are
  blank, rather than widening the shared update.
- The compliance check looked up `[VERIFY]` markers by question *text*, but `code_checks` numbers its questions,
  so no answer ever counted as unfinished. Caught by reading a real run's output, not by a test.
- `scripts/e2e_scenario.py` and `scripts/record_demo.py` still assumed the old single-page site: the hero button
  they clicked to sign up now opens How It Works, the demonstration moved to Try Features, each top-bar link
  renders its icon name before its label, and the sidebar hides later pages behind "View N more". All fixed, and
  the hero-photo check now waits for the image instead of sampling once.
- I deleted a running server's database between runs, and the next page load failed with "no such table: grants".
  The server has to be restarted after the file is removed.

**Not done, and deliberately left:** the imported requirements are not yet wired into Should We Pursue?, Can We
Afford to Win?, the budget narrative or the workback planner. Sam asked for that only if it did not risk the
deadline, and the proposal review was the piece he specified.

## Needs Sam's decision or action

- **GitHub:** I have not created a repository or pushed anything, and I won't without your approval. The exact commands will be in `submission_audit.md`. Before the first push: if the repository is private, add `zlisto` as a collaborator.
- **Real user test: done on 2026-10-24.** A director at a small nonprofit working with at-risk adolescents and young men spent 20 to 30 minutes setting up a profile, searching Grants.gov and outlining a real opportunity, and finished every task unaided. Seven observations, all acted on; two were defects that sample data could not have exposed (a stale forecast reported as upcoming, and an opportunity returned twice because nothing deduplicated the results). Record, including what was not captured: `docs/evidence/user-test-2026-10-24.md`.
- **Demo video:** an automated, captioned recording of the running app is in `demo-video/` (`python -m scripts.record_demo`). It has no narration. Watch it and decide whether to submit it as it is or record your own.
- **Reprint the PDFs.** `report.pdf` and `slides.pdf` were open in Adobe Acrobat while the new ones were built, so Windows would not let them be replaced; the two in the repository are still from 2026-10-21. Close Acrobat and run `python -m scripts.print_pdfs --browser chromium`. The HTML they print from is already current.
