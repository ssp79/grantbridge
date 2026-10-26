# GrantBridge

**Less time chasing funding. More time changing lives.** GrantBridge is an AI-powered grant strategy partner for small, resource-constrained U.S. nonprofits. It helps them:

- discover funding;
- **decide which grants are worth pursuing**, given their eligibility, mission, staff hours, and deadlines;
- **see whether they can afford to win one**: the match, the wait for reimbursement, overhead limits, reporting, and staffing, worked out against their own reserves;
- write stronger, evidence-checked applications;
- plan the work back from each deadline.

> **Most grant-writing tools help you apply. GrantBridge helps you decide what is worth applying for.**

- **Course demo.** Every organization, profile, and test account is a sample, and it is not production-grade security (see the end of this file).
- **Public website.** Visitors get five pages without signing in — Home, About Us, Try Features, How It Works, and Trust & Responsible AI — with a licensed photograph, real product screens, and demonstrations computed live by the real code: *Should we pursue it?*, *Can we afford to win it?* and *How long will it take?*
- **Deliverables:**
  - `report.html` and `report.pdf` (the project report; the PDF is printed from the HTML by `python -m scripts.print_pdfs`)
  - `slides.html` and `slides.pdf` (the presentation, built with reveal.js 5.1.0, which is inlined into the file so it opens offline; see `vendor/reveal.js-5.1.0/`)
  - the demo video, `demo-video/grantbridge-demo-<date>.webm`: an automated, captioned recording of the running app made by `python -m scripts.record_demo`. It is submitted on its own and not committed.
  - `submission_audit.md` (the rubric crosswalk and submission checklist)
  - `evidence_manifest.md` (every screenshot, and what it proves)
  - `PROGRESS.md` (the work log)
  - Both HTML files are self-contained, and `python -m scripts.build_deliverables` rebuilds them from the evidence in `docs/`.

## Quick start (about 5 minutes; measured at 54.7 seconds from a GitHub clone)

*Measured on 2026-10-25: an anonymous `git clone` of this repository, then the steps below, timed until the page answered in a browser, with the API key read from a `.env` one folder above the clone. See `docs/evidence/fresh-clone-test-2026-10-25b.md`. Most of that time is `pip install` downloading dependencies, so it varies with your network: the same test measured 88.8 s and 47.7 s on other runs.*

### Prerequisites

- **Python 3.10 or newer** (tested with 3.12.10) and `pip`. No database server or other services: data lives in one SQLite file.
- **Internet** for `pip install`, for the AI features, and for the live Grants.gov search (the Grants.gov API needs no key). Sample grants and practice mode work offline.
- **Windows:** clone into a **short folder** such as `C:\gb`. Windows limits paths to 260 characters by default, and in a deeply nested folder pip can fail while unpacking a dependency (pyarrow). That happened in our first fresh-clone test: `docs/evidence/fresh-clone-test-2026-10-21.md`.

### 1. Put the API key where the app can find it

The app reads a `.env` file from **this repository's folder first**, then from **the folder above it**. A key already set in your shell environment is used first.

```
submissions/
├── .env              <- PORTKEY_API_KEY=...   (one folder above the repo: works)
└── grantbridge/
    ├── .env          <- ...or here (this one wins if both exist)
    └── README.md
```

| Key | Needed? | Notes |
|---|---|---|
| `PORTKEY_API_KEY` | Yes (or the next one) | The course key. The app always uses **`gpt-6-luna`** with it, through the course's Portkey gateway. |
| `OPENAI_API_KEY` | Optional | Used only if there is no Portkey key, with your own compatible model. |

`.env.example` lists both names with empty values. Never commit a real `.env`: `.gitignore` excludes it, and our fresh-clone check confirmed that no `.env` is tracked.

### 2. Install and run

Windows (PowerShell):

```powershell
cd grantbridge
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m streamlit run streamlit_app.py
```

macOS and Linux:

```bash
cd grantbridge
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run streamlit_app.py
```

Open http://localhost:8501. You land on the public **Home** page. Press **Try GrantBridge** (or **Create an account**), then on the Dashboard press **Try it with sample demo data**. **Account → AI model** shows whether the key was found. To check the key and gateway with one tiny live call (about 26 tokens):

```powershell
.venv\Scripts\python -m scripts.check_model     # macOS / Linux: .venv/bin/python -m scripts.check_model
```

It prints where the key came from (for example "found (parent-folder .env)"), never the key itself.

### 3. Run the tests

```bash
.venv/Scripts/python -m pytest      # Windows
.venv/bin/python -m pytest          # macOS / Linux
```

The suite makes no network or AI calls, needs no key, and uses a temporary database for every test. It takes about 4 minutes. The current count is in `PROGRESS.md`. Browser runs: `python -m scripts.e2e_scenario` (see its docstring; it needs `pip install -r requirements-dev.txt`).

### If the staff key does not work

Everything still runs. **Practice mode** (the toggle on each AI page, or `GRANTBRIDGE_ADVISOR_MODE=mock` for the whole app) gives clearly labeled MOCK results with no AI calls. Practice mode turns on by itself when no key is found.

Many features are code, not AI, and so are identical in practice mode:

- the eligibility checks and Should We Pursue? decisions;
- the Portfolio Strategist and its weekly capacity;
- budget arithmetic and the workback plans;
- sample-grant search.

Set `GRANTBRIDGE_LIVE_SEARCH=off` on a machine without internet. If you want graders to see live AI without their own key, a hosted deployment with the key stored as a secret is the alternative. That is Sam's decision: nothing has been deployed.

### Optional: a demo account from the command line

```bash
.venv/Scripts/python -m scripts.create_demo_account --email you@example.org   # prints a random password once
```

Use `--prompt-password` to type your own, or `--reset` to recreate it. Nothing is saved to disk, and there are no shared default logins.

## Design system

One palette carries the public pages and the application: **ivory `#F7F4EE`, navy `#173341`, teal `#287F78`, sand `#D9C6AA`, sage `#66756D`**, with small text in the darkened teal `#1F6A64` and sage `#56645D` so every combination keeps at least 4.5:1 contrast.

- **Set once, in two places.** `.streamlit/config.toml` carries everything Streamlit can theme itself (page and sidebar colours, radii, semantic colours, dataframe chrome), so the components theme themselves instead of being overridden. `grantbridge/ui.py` holds one stylesheet for the rest, built on CSS custom properties (`--navy`, `--teal`, `--line`, an 8px spacing scale `--s1`…`--s6`, radii and shadows). No rule hard-codes a colour.
- **The application shell** is a light warm rail with navy type; teal marks only the selected page and primary actions. Navigation is grouped by what you are doing: *Workspace*, *Decide and plan*, *Your organization*. Every page stays registered, so deep links and `st.switch_page` keep working from anywhere.
- **One page header.** Every page calls `components.header(title, icon, intro)`, which renders the title, a single line of orientation, and a hairline, all in the same place.

## A 10-minute demo flow

1. **The public website** (no sign-in): Home for the positioning, **Try Features** for the demonstrations computed live by the real code. On *Can we afford to win it?*, move the match slider and watch the cash it ties up change.
2. **Create an account.** A new account is offered a three-step **Set up** flow (name and state, mission and programs, the size of grant you look for). Each step saves as you finish it, every step can be skipped, and the Dashboard offers to finish later.
   - **Getting Started** (next to Dashboard) is the same six steps as a permanent walkthrough you can revisit. It marks a step done only when it can see it in your own records, and says why underneath.
   - **Try it with sample demo data** loads Harbor Lantern Tutoring Collective, a sample Connecticut tutoring nonprofit, with two saved grants and one application. GrantBridge records exactly what the demo added and keeps a copy of the profile it replaced, so **Remove the demo data** (on Set up, Getting Started, or Organization Profile) takes it back out and leaves anything you wrote yourself untouched.
3. **Find Grants:**
   - SAMPLE results, each with its checks;
   - **Explain fit (AI)** on the Connecticut After-School Learning Grant;
   - switch to **Grants.gov (live federal search)** for real listings with their retrieval time.
4. **Should We Pursue?** on the Connecticut grant: *Promising, but verify first*. Tick the two rules you confirmed and assess again: *Strong candidate*, with the AI evidence reused and no new call.
5. **Can we afford to win?** (the second tab), on the New England Youth Opportunity Fund:
   - press **Use the sample award terms**, or paste them into the notice box;
   - open **Terms found**: every condition is quoted, with its source;
   - on **Your numbers**, enter an award of 55,000, reserves of 30,000, and 10,000 of committed match: *Winning would strain your cash*;
   - on **What if**, switch to installments;
   - back on the first tab, **Assess again**: *Proceed with caution*.
6. **Portfolio Strategist:**
   - recommended, deferred, and excluded grants, each with its reason;
   - set the staff hours to 3 and watch the portfolio shrink;
   - **Weekly capacity**: the schedule against your hours;
   - **Mission drift**: check the STEM grant;
   - switch on **Defer grants that would strain our cash** and watch the New England grant move to deferred.
7. **Applications**, one tab at a time:
   - **Write answers:** facts, then a draft, then use it, then review it, with the verification checklist;
   - **Review proposal:** the scorecard and **Revise with AI**;
   - **Budget & narrative;**
   - **Timeline:** a workback plan and an `.ics` file.
8. **AI Grant Advisor:** ask "Which grants should we prioritize?" and open **Technical details** to see its tool calls, tokens, and cost.
9. **Account:** AI usage and the estimated cost per run.

## Architecture

```
Browser ──▶ Streamlit (streamlit_app.py: public router for visitors, full router after sign-in)
              │
              ├── app_pages/*.py           one file per page; every private page calls session.require_user()
              │
              ├── grantbridge/ (Python)    code decides: checks, rules, arithmetic, schedules, guards
              │     ├── repo.py ──────────▶ SQLite (data/grantbridge.db), every query scoped to the account
              │     ├── grants_gov.py ────▶ Grants.gov API (search2, fetchOpportunity; no key)
              │     └── llm.py ───────────▶ OpenAI SDK → Portkey gateway → Azure OpenAI gpt-6-luna
              │                              (Responses API, strict JSON schemas, store=false)
              └── trace.py                 privacy-safe record of every step: tool, model, tokens, cost
```

The AI is used where language helps:

- explaining fit;
- the advisor;
- drafting, reviewing, and revising;
- the budget narrative;
- pursuit fit evidence;
- mission drift;
- reading a grant's award terms (each with a quote) and explaining the cash numbers in plain words.

Every AI output then passes through code: quote checks, figure checks, removal of predictions and eligibility claims, sanitizing, and rules the model cannot override. Grant and pasted text always reaches the model as escaped data.

## The public website

Visitors who are not signed in get a five-page public site with a real horizontal top bar, each page at its own
URL, plus **Sign in**:

| Page | File | What is on it |
| --- | --- | --- |
| **Home** | `app_pages/about.py` | The hero with a licensed documentary photograph, the positioning, cards into the rest of the site, and the trust line |
| **About Us** | `app_pages/about_us.py` | The mission, the problem, who it is for, what makes it different, and where GrantBridge honestly is today |
| **Try Features** | `app_pages/try_features.py` | The interactive demonstrations a visitor can change, with no account |
| **How It Works** | `app_pages/how_it_works.py` | The workflow as an editorial timeline, from discovery to submission |
| **Trust & Responsible AI** | `app_pages/trust.py` | What is checked by code, what the AI may and may not do, what is stored, and what is not claimed |

The **demonstrations on Try Features** are computed live by the real code: *Should we pursue it?* by the real rules
(`pursuit.example()`), and *Can we afford to win it?* by the real cash simulation (`award_feasibility.demo()`),
whose sliders rerun the arithmetic. Both use the sample demo profile and the sample New England Youth Opportunity
Fund, in memory: no account, no database writes, no AI call.

**Design and images.** The site uses GrantBridge's editorial palette (ivory `#F7F4EE`, navy `#173341`, teal
`#287F78`, sand `#D9C6AA`, sage `#66756D`, with small text darkened to pass WCAG AA contrast), set in
`.streamlit/config.toml` wherever Streamlit allows it and in `grantbridge/ui.py` for the rest, on an 8px spacing
scale. The photograph is from Unsplash under the Unsplash License, saved in `assets/photos/` at 1200 and 720
pixels wide as WebP, with its source, license terms, and changes recorded in `assets/photos/ATTRIBUTION.md`. The
people in it are not affiliated with GrantBridge. The product screens in `assets/previews/` are GrantBridge's own,
with sample data; `python -m scripts.capture_site_previews` re-creates them. All images carry descriptive alt text.

**What stays private:** signed out, the router registers only the five public pages and Sign in. No private page
can even be opened, and the tests prove it for every page in `app_pages/`. Every private page also calls
`session.require_user()` itself, and the public pages read no account data (also tested, in
`tests/test_public_site.py`).

**Navigation:**

- Signed in, the public pages stay registered under **The public site** in the sidebar, so their links never
  dead-end, and signing in still opens the **Dashboard**.
- After logging out or a timeout, visitors see the **Sign in** page with the reason.

## Starting an application

Starting an application and working on one are the same page. On **Applications**, press **New application** (or land there with none) and you get three routes:

1. **From a grant you saved** — GrantBridge already has its questions, funder and deadline.
2. **From the funder's documents** — upload the solicitation as a PDF, DOCX or TXT file (or paste the text) and
   GrantBridge extracts the questions, deadline, award range, match, eligibility rules and required attachments.
3. **Blank** — a title, and you add the questions yourself.

The upload route is the only place GrantBridge accepts a file, and it is fenced in: the type comes from the file's
first bytes rather than its name, the limits are 8 MB, 80 pages and 3 documents per import, the bytes are read in
memory and never written to disk or executed, and a scanned PDF with no text layer is refused with an explanation
rather than importing nothing silently. See [docs/SECURITY.md](docs/SECURITY.md) for the full set.

What it produces is not a list of questions — real solicitations rarely ask any. It is a **proposal
outline**: the sections the funder named, in their order, with the discrete things each one must contain, its
page or word limit, the criteria it is scored against, the forms and attachments you must file with the
condition that decides whether each applies, and the registrations with their lead times. All of it appears on
the **Proposal outline** tab, and it can be downloaded as a Word document, written in, and uploaded back.

Extraction follows the same rule as the rest of GrantBridge: **the model reads and code decides.** Every item the
model returns must carry a sentence copied word for word from the document; code checks that the sentence really
is in the document and that any number in the item appears inside that sentence, and drops anything that fails or
that came from wording aimed at an AI. Nothing is written to an application until you confirm it on the review
screen, and an import never overwrites a title, funder, due date, question or requirement that is already there.

## Finding grants

**Find Grants** has two sources. Every result shows which one it came from.

| | Sample grants (offline) | Grants.gov (live federal search) |
|---|---|---|
| Data | 10 synthetic grants, labeled **SAMPLE / NOT LIVE** | Real federal opportunities from the public Grants.gov API |
| Works offline | Yes, always | No. Network problems show a clear message instead of results |
| Source link | None (sample) | The opportunity's Grants.gov page |
| Status shown | "SAMPLE: no real deadline" | Grants.gov's own status at retrieval time, e.g. "Posted on Grants.gov: closes Jan 13, 2027", with the timestamp |

How a search works:

1. **Query from the profile (code).** Focus areas map to Grants.gov funding-category codes (Education becomes `ED`). Your self-reported 501(c)(3) status maps to the applicant-type code (`12`). Only these filters and any keyword you type are sent to Grants.gov, never your profile text.
2. **Search tool.** It queries the sample fixtures, or Grants.gov `search2` (statuses posted and forecasted, up to 200 rows).
3. **Filter and rank (code, not AI).** Each grant gets deterministic checks: state, focus area, award range vs. your request, 501(c)(3) status, budget and staff limits, and applicant type. The results are *meets*, *does not meet*, or *unknown*. Anything the code cannot check is listed under "Not checked automatically."
   - Live results whose close date has passed are hidden.
   - Research-type grants (NIH R01s, clinical trials) are hidden by default, with a count and a toggle to show them.
   - The rest are sorted by hard failures, research type, deadline status, checks met, and close date.
4. **Load details (live only).** This calls `fetchOpportunity` for award amounts, eligible applicant types, cost sharing, and the notice's eligibility text.
5. **Explain fit (AI, on request).** gpt-6-luna explains the fit in plain words, with a verdict, a confidence level, reasons, uncertainties, and what to verify. Code then enforces three rules:
   - Sentences that claim a grant is open are removed.
   - A failed hard check caps the verdict at "unlikely fit".
   - Confidence cannot be "high" while some requirements are unchecked.

   Grant text is passed to the model as delimited data, with an instruction to ignore any instructions inside it.

**GrantBridge never says a grant is open.** A live status is always attributed to Grants.gov with its retrieval time and a link to confirm. Statuses are cached for at most 15 minutes, and the cache note says so.

**Grants.gov API usage (verified 2026-10-20).** The [API guide](https://grants.gov/api/api-guide) documents `POST https://api.grants.gov/v1/api/search2` and `fetchOpportunity` with no authentication. The [terms](https://grants.gov/api/terms-conditions) permit searching, displaying, and retrieving grants data. They require this notice, shown on the live search page:

> This product uses the Grants.gov API but is not endorsed or certified by the U.S. Department of Health and Human Services.

No numeric rate limit is published; the [status codes](https://www.grants.gov/api/status-codes) recommend exponential backoff on HTTP 429. To stay polite, GrantBridge:

- sends at most one request per second
- caches identical searches for 15 minutes
- retries timeouts and 5xx errors twice with exponential backoff
- after a 429, sends nothing until a cooldown ends (Retry-After, or 30 s doubling to 5 min)

To turn live search off, for example on a machine with no internet, set `GRANTBRIDGE_LIVE_SEARCH=off`.

## Writing an answer (Applications page)

For each application:

1. **Questions & requirements.** Type the funder's questions, or paste them. GrantBridge splits pasted text line by line:
   - Lines that ask something or give a word limit become questions. Limits like "max 200 words" are normalized.
   - The rest become requirements that every answer is reviewed against.
   - Lines that look like instructions aimed at AI tools ("ignore all previous instructions…") are struck through and left out unless you choose to add them.
2. **Write answers**, one question at a time:
   - **Facts:** *Find missing facts* lists what the answer needs. Facts your profile already has are marked; for missing ones, it asks you in a short chat. Answer, or skip ("I don't know").
   - **Draft:** the AI drafts from **your profile and your facts only**. Gaps become `[NEEDS: …]` placeholders. Any number, date, dollar amount, or name that your facts do not contain is wrapped as `[VERIFY: …]`. The draft is a suggestion: it never replaces your answer until you press *Use this draft*.
   - **Your answer:** edit freely. Every save keeps the previous text in the version history, and any version can be restored. Nothing you write is overwritten.
   - **Review and verify:** checks the saved answer against the question and requirements. AI review quotes are kept only if they really appear in your answer. You get the explicit **Needs human verification** checklist, covering:
     - unsupported figures and names
     - placeholders still to fill
     - requirements not fully met
     - claims and missing evidence
     - injected wording
     - self-reported profile facts
     - the grant's status (sample, or a dated Grants.gov copy)

     Tick items only after checking them yourself.
3. **Status** for every application and question appears at the top of the page:
   - *Not started* or *AI draft waiting*
   - *In progress (not reviewed)*
   - *Needs verification (N open)*
   - *Ready for final read*: reviewed after the last edit, with every item ticked

**Evidence rule.** Only your profile, your own facts, and the amount requested count as evidence about your organization. Funder text (questions, requirements, grant descriptions) is untrusted:

- It reaches the model only as escaped data inside `<funder_text>`.
- It is scanned for instructions aimed at AI tools.
- It can never vouch for a claim about you. A "we served 10,000 students" planted in a grant description is flagged like any other unsupported number.

Measured on 2026-10-21 with gpt-6-luna: one question taken through facts, draft, and review used about 5,300 tokens (3,435 in, 1,874 out), an estimated $0.00134, in 22 seconds. Each step makes one stateless call (`store=False`).

## Reviewing the whole proposal (Applications → Review proposal)

**Review my proposal** reads every saved answer in the application at once and returns an **advisory scorecard**. It is not the funder's scoring and not a prediction of funding.

- **Five ratings, 1 to 5,** each with its own explanation: clarity, specificity, alignment, evidence of impact, and completeness.
- **What it is based on.** Each rating and recommendation shows its basis:
  - a **funder requirement**, quoted with its source: a question, a requirement you entered, or the grant's eligibility list;
  - or **best practice**, meaning general grant-writing advice that this funder did not state.
- **What is missing:** unanswered questions, parts of a question an answer skips, and information the proposal still needs.
- **Statements to check:** figures and names that your profile and facts do not contain (a code check), and statements the AI could not support, quoted exactly from your answers.
- **What to improve first:** up to six prioritized recommendations. Each one tied to a question has **Revise question N with AI**. The revision is a suggestion only, shown **before and after** next to your saved answer. Your answer changes only when you press *Use this revision as my answer*, and the old text stays in the version history.
- **Before and after:** review again after editing to see each rating change ("▲ up 1"), the code-check counts before and after, and the sentences added or removed in each answer.

**What code enforces**, whatever the model writes (`grantbridge/proposal_review.py`):

| Rule | What happens |
|---|---|
| Unanswered questions | Completeness is capped at 2 |
| `[NEEDS]`/`[VERIFY]` markers or over-long answers left | Completeness is capped at 3 |
| Figures or names your records do not support | Evidence of impact is capped at 3 |
| Advice citing a "requirement" the funder never stated | Relabeled best practice |
| A "quote" that is not word for word in your answers | Dropped |
| A figure in the review's own wording that appears nowhere in your records, the funder's text, or your answers | Replaced with "[a figure you can document]" |
| A sentence predicting funding ("likely to be funded") | Removed |

Every cap is shown on the scorecard with its reason. Practice mode rates with fixed formulas, and each explanation states its formula.

**Measured on 2026-10-21** (`docs/evidence/proposal-review-before-after-2026-10-21.md`; sample demo data, one run, the same model reviewing its own revisions):

- **Cost and time:** one review used 2,522 input and 1,741 output tokens, an estimated $0.00119, in 12.3 s. The full loop (draft two answers, review, three revisions, review again) took 7 calls, $0.00356, and 44 s.
- **What changed:** figures or names not in the records went from 2 to 0, and the review's quoted unsupported statements from 2 to 0. `[NEEDS]` placeholders went from 1 to 4: the revisions asked for facts instead of inventing them.

## Budget & narrative (Applications → Budget & narrative)

Enter each cost once. For each line you give:

- the category, a description, and the quantity × unit cost;
- **who pays**: this grant, a cash or in-kind match, or other funding, each marked *committed* or *pending*;
- who provides any match;
- a justification.

Lines can be added, edited, and removed. **Python does all the arithmetic**, exactly (whole cents, decimal quantities): line totals, subtotals by category and by who pays, the total budget, and the share requested.

**Checks, by code:**

- the lines charged to this grant against the **amount requested** (Details tab), with the exact difference;
- the request against the grant's **listed award range** and against the **annual budget** in your profile;
- lines with **no justification**;
- match or other funding with **no named source**;
- **pending** money;
- **$0** lines;
- possible **duplicates**;
- the **indirect-cost share**. This one is shown as a fact to check against the funder's policy, which GrantBridge does not know.

**The narrative** is written only from those lines. Every figure the model sees is already formatted by code, so it never computes one. Code then checks the narrative:

- an amount, count, or percentage not in your budget or profile is marked `[VERIFY: …]`;
- a sentence calling pending money committed, or claiming committed money the budget does not have, is removed;
- lines it never mentions are listed;
- a line without a justification gets a `[NEEDS: …]` placeholder.

Each narrative is saved with the budget it describes. After any edit it shows *Your budget changed since: write it again*. *Use as a suggestion for question N* puts it on the Write answers tab as a draft: your answer never changes by itself.

**The budget is your own fact source.** Drafts, revisions, the proposal review, and the AI Grant Advisor can cite budget figures without them being flagged as unsupported. The advisor has a sixth tool, `get_budget`, for questions such as "does my budget match the amount requested?", and it repeats the code's totals rather than recomputing them.

**Measured on 2026-10-21** (gpt-6-luna, sample data):

| Run | Lines | Tokens in / out | Cost | Time | Code flags |
|---|---|---|---|---|---|
| Direct check | 5 (one pending, one in-kind) | 1,483 / 728 | $0.00055 | 8.9 s | none; the one line without a justification got its `[NEEDS]` placeholder |
| Browser run | 3 | 1,212 / 576 | $0.00044 | 7.7 s | none |

## Application timeline (Applications → Timeline)

A **workback plan** from the deadline, with seven steps: eligibility review, document collection, budget, first draft, internal review, final revisions, and submission. Every date is computed by code; no AI is involved.

**The deadline is never invented.** The tab always says where it came from:

| Label | Meaning |
|---|---|
| **From Grants.gov** | The close date Grants.gov listed when GrantBridge copied the listing, with the copy date. Confirm it on Grants.gov. |
| **SAMPLE example date · not a real deadline** | A sample grant's date. Plans built on it are labeled *practice plans*. |
| **Entered by you** | A date you typed or corrected. If it differs from the Grants.gov date, both are shown, with *Use the Grants.gov date*. |

With no deadline, there is no plan, only a request to enter the date. A passed deadline is refused.

- **How the plan is built.** Default days per step: 3, 7, 5, 10, 5, 3, and 1. Submission is planned 2 days before the deadline. These are GrantBridge's assumptions for a small team, not a funder's rule, and you can change every one. When less time is left, the submit-early margin shrinks first, then every step shrinks in proportion.
- **Flags, by code:**
  - overdue steps, steps out of order, and steps after the deadline
  - a deadline that changed after the plan was built
  - a plan squeezed below half of the default time ("consider whether this deadline is realistic")
  - no time to submit before the deadline day
- **Editing.** Mark steps done and change their dates. Changed dates are labeled. *Rebuild from the deadline* keeps done steps done.
- **Calendar and dashboard.** *Download calendar (.ics)* adds the open steps and the deadline to your own calendar as all-day events, with no alarms. **GrantBridge does not send reminders.** The Dashboard's **Next steps** lists open steps across your applications, and the AI Grant Advisor sees each application's next step.

**Measured on 2026-10-21** (final browser run, step F8): 0.5 s from the click to the saved plan, of which 16.1 ms was GrantBridge's code. An earlier run measured 0.6 s and 16.5 ms.

## Should We Pursue? (the Grant Pursuit Advisor)

A go/no-go check for one grant, opened from **Should we pursue?** on any grant card, from Saved Grants, from an application's header, or from the navigation. It rates six dimensions:

| Dimension | What it looks at |
|---|---|
| **Eligibility** | GrantBridge's automatic checks (met, failed, unknown) and the listing's rules that code cannot check. Missing information is *unknown*, never "ineligible". You can confirm unknown items yourself; they are then listed as *confirmed by you*. A failed check cannot be confirmed away: fix the profile if it is wrong. |
| **Strategic fit** | Shared focus areas and key words (a word-level signal). The AI adds evidence as pairs of exact quotes from your profile and the grant; code keeps a pair only if both quotes appear word for word. |
| **Application readiness** | The funder's own questions and requirements (verified requirements), shown apart from best-practice steps (complete profile, budget, workback plan). |
| **Time and capacity** | Days to the deadline (its source always shown), and staff hours estimated from assumptions you can edit: hours per step, and hours a week you can give. |
| **Budget feasibility** | The request against the award range and your annual budget, and whether the budget lines match the request. |
| **Proposal quality** | The latest *Review my proposal*, or "not yet assessed". |

**The outcome is decided by code**, from rules checked in order; the page lists them and marks those that apply:

1. **Do not pursue under current conditions:** a required check fails; the deadline has passed; or, at your stated capacity, the work needs more weeks than are left.
2. **Proceed with caution:** a fixable check fails (for example the award range), the work needs more than 75% of the time left, the request is larger than your annual budget, or *Can we afford to win?* found that winning would tie up more cash than your reserves, with every term it depends on known.
3. **Promising, but verify first:** an eligibility item is unknown or unconfirmed, or the deadline is unknown or rolling.
4. **Strong candidate:** none of the above.

The AI cannot change an outcome: it writes only fit evidence, which code checks for quotes, predictions ("likely to be funded"), eligibility claims, and invented figures. When nothing it reads has changed, a rerun reuses that evidence instead of calling the AI again. Nothing here predicts an award.

**Data flow.** For a Grants.gov grant, Grants.gov receives only the opportunity id; your profile is never sent there. If Grants.gov cannot be reached, eligibility is *unknown* and the outcome can be no better than *verify first*.

The page also gives:

- **What we verified**, with sources and the Grants.gov link;
- **What we still need to know**, with confirm boxes;
- the **top 3 next actions** and an **effort breakdown**;
- **Start or continue the application** and **Create a workback plan**;
- the run's steps, tokens, and cost.

**Measured on 2026-10-21** (gpt-6-luna, sample demo profile):

| Grant | Outcome | Cost | Time | Notes |
|---|---|---|---|---|
| sample-01 | Promising, but verify first | $0.00028 | 6.6 s | 4 fit points; every quote verified, none dropped |
| sample-07 | Do not pursue | $0.00020 | 3.4 s | 3 grounded "weaker fit" points |

In the browser run, confirming sample-01's two listing rules turned it into a **Strong candidate** in 0.4 s, reusing the AI evidence with no new call.

## Can We Afford to Win? (award feasibility)

The second tab of **Should We Pursue?** answers a different question: if we win, can we carry it? A grant that fits the mission can still need a cash match, pay only months after the money is spent, cap overhead below the organization's real rate, or require staff and reports the team does not have. It is also reachable from an application's **Budget & narrative** tab.

**What it reads.** The grant's listing and, optionally, the funder's notice or award terms, **pasted as text** (to read one from a PDF, DOCX or TXT file instead, start an application on the Applications page). For a Grants.gov grant it also uses Grants.gov's own yes/no cost-sharing field.

**What the AI does, and what code does.**

- **The AI reads:** it lists each condition (award period, payment and reimbursement, match, allowable costs, indirect limit, reporting, staffing) with a quote and the numbers in it. In practice mode, fixed text patterns do this instead, with no AI.
- **Code checks:** a quote must appear word for word in the listing or the notice, each number must appear inside its own quote, and a sentence aimed at an AI is never used. Any area no quote supports stays **unknown**: GrantBridge never assumes a typical term.
- **Code counts:** the match (on the award or the total project cost), then a day-by-day simulation of the grant. Spending goes out evenly; reimbursement claims are paid after the stated delay; an advance arrives on day 0, and the rest in equal installments on the stated schedule. Committed match money is used first. The worst day is the most of the organization's own cash the grant would tie up at once.
- **The verdict is a rule:** *affordable*, *tight* (the worst point uses more than half the reserves), or *a burden* (more than the reserves). It is a burden only when every term it depends on is known; otherwise it is *unknown*, with the projection shown.

**Your numbers.** Each input shows where it came from: you, the terms, your application, your profile, your budget lines, a calculation, or a stated assumption. Reserves and your indirect rate are saved once for the organization.

**What if.** Sliders for the payment delay, award, match, and spending, and a choice of payment type, rerun the arithmetic at once and save nothing.

**Where the result goes.** *Should We Pursue?* gets a caution rule from a known burden. The **Portfolio Strategist** can, if you switch it on, defer grants that would strain your cash; it never defers a grant on an unknown term. The AI can also explain the numbers in plain words: code replaces any figure it states that the numbers do not contain, and removes predictions and eligibility claims.

**The sample demonstration:** the SAMPLE New England Youth Opportunity Fund fits Harbor Lantern's mission, but its sample terms pay only by reimbursement, 90 days after each quarter, and need a cash match of 50% of the total project cost. With $30,000 of reserves and $10,000 of match committed, winning a $55,000 award would tie up about $58,562 of the organization's own cash at the worst point (browser run, step A2).

**Measured (2026-10-21, live, `docs/evidence/award-feasibility-eval-2026-10-21.md`):** on 5 sample notices written with their expected terms before any model saw them, 3 runs each, gpt-6-luna with code checks scored 63 terms correct and 87 correctly unknown, with 0 missed, 0 wrong, and 0 invented. One notice carried an injected instruction. Reading one notice cost $0.00027 on average; explaining the numbers, $0.00032. These are short notices written for the test, not real award agreements.

**Limits:** spending is spread evenly, terms are taken as written, and the model knows nothing of the organization's other grants, a line of credit, or a funder's willingness to advance funds. It is a model of cash timing, not accounting advice.

## Portfolio Strategist (capacity, portfolio, mission drift)

The Portfolio Strategist decides which grants to pursue **with the hours you actually have**. The code makes every recommendation; the AI only explains possible mission drift.

- **Nonprofit Capacity Optimizer.** You give your staff hours a week. GrantBridge then works out:
  - each application's hours, estimated from editable assumptions (or your own number, labeled *yours*);
  - your commitments: applications marked **Drafting**, plus anything you add, such as a report to a funder;
  - a day-by-day schedule on weekdays, earliest deadline first, shown week by week with available hours, scheduled hours, deadlines, and conflicts.

  With pooled staff hours, earliest-deadline-first meets every deadline whenever any schedule can. A shortfall therefore means the hours really are not there.
- **Grant Portfolio Optimizer.** Every saved grant (and every grant you are researching) is a candidate.
  - **Excluded:** you marked it *not interested*, it fails a required eligibility check, its deadline has passed, or (your choice) it has a high mission-drift concern.
  - **Score:** the rest get a 0 to 100 priority score from five components weighted by your sliders: strategic fit, eligibility certainty, potential request, low effort, and mission alignment.
  - **Selection:** *Must pursue* grants go first, then the rest by score. Each is **kept only if every deadline still fits your weekly hours**; otherwise it is **deferred**, with the exact reason.
  - **Live:** change the hours, sliders, or decisions and the result recomputes at once.
  - **No odds:** no award probabilities and no "expected value". Amounts are **potential requests**, not expected or guaranteed awards.
- **Mission Drift Detector.**
  - **Five areas:** activities outside the mission, a different population, geographic expansion, resources diverted from current programs, and obligations that may be hard to sustain.
  - **Ratings:** each concern is rated low, moderate, high, or unknown, with an exact quote from the grant, a quote from your profile when it compares, and what is uncertain.
  - **What code does:** it checks geography (eligible states), focus areas, and the listing's own obligation rules. Those facts take precedence. A rated concern without a verbatim grant quote is dropped.
  - **Reuse:** unchanged inputs reuse the last check.

The AI Grant Advisor's seventh tool, `get_portfolio`, answers "which grants should we prioritize?" from the same recommendation.

**Measured on 2026-10-21** (gpt-6-luna, sample demo profile): live drift checks cost $0.0005–0.0007 and took 8–12 s each.

| Grant | Drift | Why |
|---|---|---|
| sample-01 | Low | |
| sample-07 | High | Adult credential training, adults rather than students, outside the state |
| sample-04 STEM | Moderate | A required STEM share of program time; grades 6 to 12 against your 3 to 8 |

## AI Advisor

One orchestrating agent (gpt-6-luna, Responses API) with seven real tools. No extra "agents" for show.

| Tool | What it does | Writes? |
|---|---|---|
| `get_organization_profile` | The profile, every value labeled self-reported; missing fields listed | No |
| `search_grants` | The same search as Find Grants (sample or Grants.gov), with the deterministic checks | No |
| `inspect_grant_requirements` | One grant's full rules, award range, deadline status, and questions; Grants.gov text is labeled `_untrusted` | No |
| `save_grant` | Adds a grant to your saved list (live grants as a dated snapshot) | Yes, only if your own latest message asks to save (checked in code) |
| `get_application_state` | Your applications: status, due date, questions answered (counts only), and each application's next timeline step | No |
| `get_budget` | One application's budget lines, the totals computed by code, and the budget checks | No |
| `get_portfolio` | The Portfolio Strategist's recommendation (recommended, deferred, or excluded, with reasons) at your saved capacity | No |

**How it answers.** The agent reads your profile and the grant records through these tools. It must cite only what the tools returned. Its final answer is structured: a reply, *known facts* (each with its source), *assumptions and unknowns*, an optional *clarifying question*, and the grant ids it mentions.

Code then checks the answer before it is saved (`guards.py`):

- Sentences claiming a grant is open, or that you are eligible, are removed.
- Dollar amounts, percentages, and dates that do not appear in a retrieved record or your own message are marked **(unverified)**.
- Grants it mentions without looking them up are flagged.

**Limits.** These caps hold even if the model misbehaves:

- At most 5 model calls and 8 tool calls per message, and 3 saves per message.
- A daily budget of 100,000 tokens per account (`GRANTBRIDGE_DAILY_TOKEN_BUDGET`). When it runs out, the advisor switches to mock mode.
- Model calls use `store=False`.

**Technical details (the agent's activity).** For each answer it shows every step (model call, tool, or code) with redacted inputs, status, output summary, time, tokens, and estimated cost, plus the final response. Above the response it totals the model calls, tool calls, model time, and estimated cost. It also breaks down the tokens: input (read from the prompt cache, or written to it) and output (with reasoning). Your message and search keywords appear only as their length.

**History** is saved per account. The last 8 messages are sent with each new question. Clear it any time.

**Mock mode (free, deterministic).** Turn on *Mock mode (no AI calls)* on the AI Advisor page, or set `GRANTBRIDGE_ADVISOR_MODE=mock` to make it the default. A keyword planner picks the same real tools and writes the answer from their results with fixed templates. Every mock answer is labeled **MOCK ANSWER: no AI model was called**.

Mock mode is used automatically when no API key is configured, when the daily budget is used up, or when a model call fails.

Measured on 2026-10-20 with gpt-6-luna:

- "Which sample grants fit us best?" used 6,301 tokens after tuning the instructions, down from 9,804 (36% fewer), with the same top three grants.
- About half the input tokens of later model calls in a turn come from the prompt cache.

**Privacy-safe trace.** Every search, details load, and AI explanation is recorded as a run of steps (code, tool, or AI model). See "How this search ran" on Find Grants.

- **Recorded:** step names, timings, statuses, counts, filter categories, and public grant ids. Each model call also records the model and its token counts as the provider reported them (input, cached, written to the cache, output, reasoning), plus an estimated cost.
- **Never recorded:** your keyword text (only its length), profile text, email, or the AI's prompts and replies. An allowlist with per-key value rules enforces this.

Traces are visible only to their owner. The last 50 runs per user are kept, plus every AI run from the last 24 hours, which the budgets count.

## What it costs (tokenomics)

Every AI run records the following, using the provider's own usage numbers:
- the model
- input tokens, including how many were read from the prompt cache and how many were written to it
- output tokens, including reasoning
- an estimated cost, the time taken, and the number of tool calls

You see them under each AI explanation, draft, and review, in the advisor's **Technical details**, and in **Account → Technical details: your AI usage and estimated cost**.

Prices live in `data/pricing.json` with their source and date: OpenAI API pricing for gpt-6-luna, checked 2026-10-20. That is $0.10 per 1M input tokens, $0.01 cached, $0.125 for cache writes, and $0.50 output. A call without usage gets no cost estimate, never a made-up one.

Measured on 2026-10-21 (three workflows, 3 repetitions each, every run starting with a cold cache):

| Workflow | Cost per run | Time |
|---|---|---|
| Explain fit | $0.00033 | 3.8 s |
| Advisor answer | $0.00059 | 7.6 s |
| Draft one answer (facts, draft, review) | $0.00134 | 21.8 s |

That comes to about **$0.044 per active account per month**, $4.38 for 100 accounts, and $438 for 10,000, under the usage assumptions in the doc. The newer features (proposal review, revisions, budget narratives, pursuit assessments, and mission-drift checks, also measured on 2026-10-21) bring the total to about **$0.058 per account per month**, or $575 for 10,000 accounts. With *Can We Afford to Win?* as well (the terms of 4 grants read and explained a month), it is about **$0.060**, or $599 for 10,000 (section 6c of the doc).

Asking the model for low reasoning effort (`GRANTBRIDGE_REASONING_EFFORT=low`, the default) cut the first figure by 23%. Quality held: 151 of 159 checks passed, against 152 before.

Method, assumptions, quality comparison, and caveats: **[docs/TOKENOMICS.md](docs/TOKENOMICS.md)**. To measure again, run `python -m scripts.measure_costs` (live, about 160,000 tokens), or add `--offline` to test the harness with no AI calls.

## Project layout

```
streamlit_app.py          Entry point: the public top-bar router and the signed-in sidebar router, safe error handling
app_pages/
  about.py                Home: the public landing page (reads no account data)
  about_us.py             About Us: the mission, the problem, and where GrantBridge honestly is
  try_features.py         Try Features: the demonstrations a visitor can change, with no account
  how_it_works.py         How It Works: the six steps, as an editorial timeline
  trust.py                Trust & Responsible AI: what is checked, stored, and not claimed
  sign_in.py              Log in and create account
  dashboard.py            Your funding workspace: what needs attention, the grant pipeline, applications, deadlines
  setup.py                The three-step first run (skippable, resumable, saved step by step)
  getting_started.py      The permanent six-step walkthrough, with progress read from your own records
  find_grants.py          Sample and live Grants.gov search, fit checks, AI fit explanation
  saved_grants.py         Saved sample grants and dated Grants.gov copies
  pursue.py               Should We Pursue? (Grant Pursuit Advisor) and its Can we afford to win? tab
  portfolio.py            Portfolio Strategist: portfolio, weekly capacity, mission drift, commitments
  applications.py         Start one, then the proposal outline, answers, review, budget, timeline, export
  advisor.py              AI Grant Advisor chat with technical details
  profile.py, settings.py Organization Profile and Account
grantbridge/
  config.py               .env lookup (repo, then parent) and model/provider choice
  db.py                   SQLite schema and sample-grant seeding
  auth.py, session.py     Argon2id passwords, lockout, sessions, idle timeout
  repo.py                 All data access; every query is scoped to the signed-in account
  validation.py           Input validation shared by every form (including budget lines)
  grants_gov.py           Grants.gov API client: parsing, retries, rate-limit cooldown, cache
  grant_search.py         Profile-based query, deterministic eligibility checks, deadline status, ranking
  fit_explainer.py        AI fit explanation with code-enforced guards
  advisor.py, advisor_tools.py   The AI Grant Advisor: one agent, seven real tools, bounded loop, guards
  drafting.py             Facts chat, grounded draft, revision, one-answer review, checklist, status
  proposal_review.py      Review My Proposal: advisory scorecard, code caps, the funder's requirements one by one
  documents.py            Uploaded PDF, DOCX and TXT solicitations: content-based validation and text extraction
  solicitation.py         Reading a solicitation into an application: AI extraction, code verification, import
  outline.py              The proposal outline, scoring rubric and filing checklist read from a solicitation
  outline_docx.py         The outline out to Word and back, so a draft can be written off the site
  start_application.py    Starting an application: from a saved grant, the funder's documents, or blank
  budget.py               Budget lines, exact arithmetic, checks, and the budget narrative
  timeline.py             Deadline provenance, workback plan, checks, .ics export
  pursuit.py              Should We Pursue?: six dimensions, explicit decision rules, fit evidence
  award_feasibility.py    Can We Afford to Win?: award terms (quoted, checked), cash simulation, verdict, scenarios
  award_view.py           Can We Afford to Win?: its tab, chart, numbers form, and what-if controls
  portfolio.py            Capacity schedule (earliest deadline first), portfolio selection
  mission_drift.py        Mission Drift Detector: code facts plus quote-checked AI concerns
  guards.py               Deterministic checks on AI text (claims, figures, names, predictions, leaks, injection)
  llm.py, pricing.py      Model client, usage, reasoning effort, budgets, cost estimates
  trace.py                Privacy-safe step trace with tokens and cost
  components.py, ui.py    Shared display helpers and the theme CSS
  demo.py, logsafe.py     Sample demo data; log redaction
scripts/                  check_model, create_demo_account, e2e_scenario (browser run), security_check,
                          measure_costs, measure_new_features, measure_proposal_review, measure_award_feasibility,
                          build_deliverables (rebuilds report.html and slides.html from docs/evidence),
                          print_pdfs (report.pdf, slides.pdf), record_demo (the demo video),
                          capture_preview and capture_site_previews (the public site's product screens)
data/                     pricing.json; fixtures/ (10 SAMPLE grants, the sample demo profile, award notices,
                          a sample solicitation PDF used by the browser run)
assets/                   logo, the licensed photo (photos/, with ATTRIBUTION.md), the product screens (previews/)
vendor/                   reveal.js 5.1.0 (MIT), inlined into slides.html by build_deliverables
tests/                    pytest suite (offline; network and AI calls are blocked)
docs/                     SECURITY.md, TOKENOMICS.md, COMPETITORS.md, USER_TEST.md, evidence/, screenshots/
```

To start over with an empty database, stop the app and delete `data/grantbridge.db`.

## Security: what is built, and what is not

**Full threat model, defenses, test evidence, and known gaps: [docs/SECURITY.md](docs/SECURITY.md).** In short:
- **Isolation:** every query is scoped to the signed-in account. A test enumerates every user-scoped data function and attacks each one across accounts.
- **Untrusted text stays data:** the model never sees secrets. Grant and pasted text (including award notices, which are pasted, never uploaded) arrive only as labeled data. Every AI output is scrubbed of secrets, tracking images, unknown links, HTML, and copied system prompts. Writes need the user's own words.
- **Cost and rate limits:**
  - per request
  - 15 AI requests per minute per account
  - 1 in flight across all server processes
  - 100,000 tokens per account per day
  - 1,000,000 tokens per server per day

  Each one fails gracefully, to a labeled mock answer or a plain message.
- **Red-team check:** `python -m scripts.security_check` (live) or `--offline` (a scripted model that obeys every attack) attacks the app with a malicious sample grant and writes a redacted PASS/FAIL report.

Account security details:

This is a course demo, **not production-grade authentication**. Use sample data only.

Built:

- Passwords are hashed with **Argon2id** (`argon2-cffi`, random salt per password). Plaintext passwords are never stored or logged.
- **Per-user ownership on every query.** Each data function takes the logged-in user's id and filters on it in SQL. The id comes from Streamlit's server-side session, never from the browser. Another user's record looks the same as a missing one.
- Signed-out visitors can reach only the public About page and the sign-in page.
- Login errors are generic ("Email or password is incorrect"). After **5 failed logins, the account is locked for 15 minutes**.
- Sessions end on logout, after 30 idle minutes, on page refresh, or when the account is deleted.
- Every form validates its input with length limits. Error details are hidden from users and logged on the server with a reference id.
- No hard-coded secrets. API keys come only from `.env`, and `.gitignore` excludes it.

Not built (production would need these):

- Email verification and password reset by email
- HTTPS. Streamlit serves plain HTTP; put a TLS reverse proxy in front.
- Per-IP or global rate limiting. Only the per-account lockout exists.
- Persistent sessions or "remember me", CSRF hardening beyond Streamlit's defaults, an audit log, multi-user organizations, encryption at rest, and a privacy review
