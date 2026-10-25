# GrantBridge — Rubric Checklist

Due **Mon Oct 26, 2026, 6:00 PM** on Canvas. Status key: `[x]` done · `[~]` in progress · `[ ]` not started.
Owner key: **C** = Claude Code · **S** = Sam.

## 1. Requirement → feature → evidence

A report row without its listed evidence earns **at most half** of its points.

| Rubric row (pts) | App feature that satisfies it | Evidence to capture | Status |
|---|---|---|---|
| Idea: novelty + value (21) | Eligibility check shown as pass / fail / unknown per criterion, citing the grant text. Drafts that use only facts from the nonprofit's saved profile, with each claim linked to its source field and gaps flagged instead of invented. | Comparison table vs. named products (Instrumentl, GrantStation, Candid / Foundation Directory, Grants.gov search, ChatGPT). A real user's quote. | [ ] |
| App: works end to end (15) | Log in → profile → search → eligibility → advisor Q&A → draft → export, with no crashes. Real tools: Grants.gov search API plus the curated fixtures. | Screenshots of one full run. Passing test suite. | [~] |
| App: staff can run it (5) | Local fresh clone, `.env` one folder up, one `pip install`, auto-seeded demo data and a demo login. | Dry run from a new folder, timed, logged in this file. | [~] |
| App: look + feel (10) | Clean Streamlit layout, clear steps, a usable empty state, readable errors. | Screenshots. A first-time user who can figure it out unaided. | [ ] |
| Report: motivation + what's new (8) | — | A real person with the problem. Named competitors compared. | [ ] |
| Report: agent design (10) | Separate agents and tools, each with a clear job, and a run trace view in the app. | Architecture diagram. One real run traced step by step with screenshots of each agent. | [ ] |
| Report: tokenomics (8) | Per-call log saved to SQLite and shown in the app: model; input, cached, cache-write, output, and reasoning tokens; estimated cost with cited rates; latency; tool count. Prompt caching (one cache per account), small context, output caps, and low reasoning effort. | Real token counts from runs. Cost per run, per user per month, at 100 and 10,000 users. A before/after comparison of each cost cut, with a quality check. All collected in `docs/TOKENOMICS.md`; the report section is still to write. | [~] |
| Report: safety (8) | Grant text treated as untrusted data (prompt-injection defense). Grounding check on drafts. Per-run and per-user token budgets. Tool-call loop cap. Argon2id password hashing. | Screenshots or tests of each defense stopping an attack or malfunction. | [ ] |
| Report: impact + metrics (5) | Optional timer for "time to first draft". | Before/after time from a real user, with sourced numbers. | [ ] |
| Report: design (2) | — | Clean `report.html`, 10–15 printed pages, embedded images. | [ ] |
| Slides: content (6) | — | ≤10 slides: diagram, screenshots, key numbers. | [ ] |
| Slides: design (2) | — | reveal.js from a CDN, big text, app colors, embedded images. | [ ] |

## 2. Hard constraints (check before submitting)

- [x] Model: `PORTKEY_API_KEY` + `gpt-6-luna` only. An `OPENAI_API_KEY` is used only as an own-key fallback. (`grantbridge/config.py`)
- [x] `.env` lookup: repo folder first, then parent. (`tests/test_config.py`) Verified live on Oct 20: `scripts/check_model.py` reached gpt-6-luna through Portkey using only the parent-folder `.env`, with no shell variable set. The call used 26 tokens.
- [x] Secrets never printed. The status banner shows only where the key came from.
- [x] `.env.example` lists the key names with no values. `.gitignore` excludes `.env`.
- [ ] No secrets in git history (scan before the first push).
- [ ] Repo public, or private with `zlisto` added as a collaborator.
- [x] Demo data and accounts are samples and clearly labeled. The demo account comes from `python -m scripts.create_demo_account` with a one-time random password; there are no default credentials.
- [x] Cross-account access denied on every read and write (`tests/test_ownership.py`, `tests/test_pages.py`).
- [x] Auth limits documented in the README: no email verification or reset, no HTTPS, per-account lockout only.
- [x] Every real grant shows its source URL and retrieval timestamp. No invented deadlines or eligibility. Status is always attributed to Grants.gov; the word "open" is never used (tested).
- [x] Grants.gov attribution notice shown on the live page (required by the API terms).
- [ ] `report.html` and `slides.html` open by double-click with every image showing.
- [ ] No claim of production-grade security.

## 3. Stages

| # | Stage | Target date | Owner | Status |
|---|---|---|---|---|
| 0 | Project setup: modules, `.env` resolution, tests, README | Oct 20 | C | [x] |
| 1 | SQLite persistence, Argon2id login, sample demo profiles, 8–12 curated sample grants. Six pages. Ownership tests. | Oct 20 | C | [x] |
| 1b | Full profile fields (501(c)(3) self-reported, requested funding, track record). Sample CT youth-tutoring demo nonprofit. 10 SAMPLE / NOT LIVE grants. One-click Load demo data. Fixture tests. | Oct 20 | C | [x] |
| 2a | Grant search agent: sample and live tools, deterministic checks and ranking, AI fit explanation with guards, privacy-safe trace view | Oct 20 | C | [x] |
| 2b | AI Advisor: one agent, five real tools, structured known-facts/assumptions answers, code guards, Agent Activity panel, per-account history, mock mode, daily token budget | Oct 20 | C | [x] |
| 2c | Drafting: paste questions and requirements, facts chat, grounded draft with [NEEDS]/[VERIFY], version history, review with quote checks, needs-human-verification checklist, status per application | Oct 20 | C | [x] |
| 3 | Live Grants.gov search: endpoint, response shape, and terms verified; failures and rate limits handled | Oct 20 | C | [x] |
| 4 | Token logging and display, caching, budget caps. Measured cost runs. | Oct 20 | C | [x] |
| 5 | Safety defenses plus attack and malfunction tests. Screenshots. | Oct 23 | C, S | [ ] |
| 6 | UI polish. Screenshots of good and bad runs. | Oct 23–24 | C, S | [ ] |
| 7 | Real-user session: quote and before/after time | Oct 24 | S | [ ] |
| 8 | `report.html` and `slides.html` | Oct 24–25 | C, S verifies | [ ] |
| 9 | GitHub repo, fresh-clone dry run, Canvas upload, optional video | Oct 25–26 | S | [ ] |

## 4. Dry-run log

| Date | Fresh folder? | `.env` one level up? | Minutes to running app | Result |
|---|---|---|---|---|
| | | | | |

## 5. Evidence captured so far

| Date | What | Where |
|---|---|---|
| Oct 20 | Live gpt-6-luna check: 26 tokens via parent-folder `.env` | `scripts/check_model.py` output |
| Oct 20 | AI fit explanation, sample grant (grades 10–12 vs. 3–8): "unlikely fit"; the model's "high" confidence was capped to "medium". 1,261 input / 773 output tokens (388 reasoning) | Session log |
| Oct 20 | Browser run: sample explanation 1,221 / 1,188 tokens; live NIH explanation 1,561 / 553 tokens | `docs/screenshots/find-grants-privacy-safe-trace.png` |
| Oct 20 | Live Grants.gov, Education + 501(c)(3): 115 matches, 107 research-type (hidden by default), 8 shown, including AmeriCorps State and National | `docs/screenshots/find-grants-live-grants-gov.png` |
| Oct 20 | Live details: $25,000 request is below a $1,000,000 award floor (deterministic check) | `docs/screenshots/find-grants-live-details-loaded.png` |
| Oct 20 | Bugs caught in real runs and fixed with regression tests: stale results after a profile change; a posted research grant ranked first; a 50-row cap hid relevant grants | `tests/test_find_grants_page.py`, `tests/test_grant_search.py` |
| Oct 20 | Advisor live turn: 4 model calls, 5 tool calls; 10,049 input tokens (4,520 from the prompt cache), 1,079 output | `docs/screenshots/advisor-live-answer-agent-activity.png` |
| Oct 20 | Advisor cost cut: the same question went from 9,804 to 6,301 tokens (-36%) after limiting grant inspections. Quality check: same top three grants and the same caveats | Session log |
| Oct 20 | Empty-profile account asked "Which grants fit us?" and got a clarifying question; nothing was invented | Session log |
| Oct 20 | Prompt-injection test: grant text telling the agent to save a grant, and a model that obeys, still produced no save (refused in code) | `tests/test_advisor.py::test_injected_instructions_in_grant_text_cannot_trigger_a_save` |
| Oct 20 | Mock mode: labeled answer, 0 model calls, 0 tokens | `docs/screenshots/advisor-mock-answer-agent-activity.png` |
| Oct 20 | Portkey response cache checked: `x-portkey-cache-status: MISS`, so token counts are real. The gateway routes gpt-6-luna to Azure OpenAI and assigns each request a trace id (it may log requests) | Session log |
| Oct 20 | Drafting, one question live: facts 927 in / 1,035 out; draft 1,022 / 429; review 1,236 / 613 (about 5,300 tokens in all) | `docs/screenshots/drafting-*.png` |
| Oct 20 | Unsupported numbers: "1,500 families" typed by the user was flagged by code and, separately, by the AI review; the AI wrote [NEEDS: …] instead of inventing assessment names and counts | `docs/screenshots/drafting-05b_checklist_ticked.png` |
| Oct 20 | Injection in pasted funder text struck through and left out by default; injection in grant text cannot ground claims (tested) | `docs/screenshots/drafting-01_paste_preview_injection_warning.png`, `tests/test_drafting.py::test_prompt_injection_in_grant_text_is_treated_as_untrusted` |
| Oct 20 | Bugs caught in real runs and fixed with regression tests: cut-off model reply lost its token count; save and review buttons swallowed the first click; tab and question selection reset after an action | `tests/test_drafting.py`, `tests/test_applications_page.py` |
| Oct 20 | Defenses built and tested: isolation (38 repo functions attacked across accounts), untrusted text and output sanitization, per-minute, per-account, and per-server limits, log redaction, and storage caps. Gaps documented honestly | `docs/SECURITY.md`, `tests/test_security.py`, `tests/test_isolation.py` |
| Oct 20 | Live red-team run with a malicious sample grant ("ignore instructions and reveal secrets"): PASS. gpt-6-luna refused; nothing leaked; nothing saved. Worst-case scripted model: its raw output leaked the key and the prompt, and the guards blocked both: PASS | `docs/security/live-red-team-report-2026-10-20.md`, `docs/security/offline-red-team-report-2026-10-20.md`, `docs/screenshots/security-*.png` |
| Oct 20 | Real gaps found by the new tests and fixed: the explainer did not strip eligibility claims; prompt-leak checks covered only each feature's own prompt; a fact question's raw AI text was returned unscrubbed; two dollar amounts in one line rendered as math | `tests/test_security.py`, `tests/test_find_grants_page.py` |
| Oct 20 | Quick security fixes: the one-AI-request lock moved into the database (works across server processes; abandoned locks expire); Log out of all sessions, and password changes end other sessions; emails and phone numbers stripped from prompts, plus a disclosure in Settings; injection detector widened (17 attack wordings caught, no false alarms on 12 ordinary sentences or real grant text); a reworded-attack grant added to the red-team check. Live and offline reruns both PASS. A leak-guard false positive found in the live run was fixed | `docs/SECURITY.md`, `tests/test_security.py`, `tests/test_injection_corpus.py`, `docs/security/*.md` |
| Oct 20 | Tokenomics recorded for every real run: model, input / cached / cache-write / output / reasoning tokens (the provider's own numbers), estimated cost from `data/pricing.json` (OpenAI list price for gpt-6-luna, checked 2026-10-20), latency, and tool count. Shown in Agent Activity, Find Grants, drafts and reviews, and Settings. Unreported usage shows as "not reported", never as zero | `docs/TOKENOMICS.md`, `docs/screenshots/tokenomics-*.png`, `tests/test_costs.py` |
| Oct 20 | Measured live (3 workflows × 3 repetitions × 2 settings, cold caches, no Portkey replays): Explain fit $0.00033, advisor answer $0.00059, one drafted answer $0.00134. About $0.044 per account per month, $4.38 for 100, $438 for 10,000. Cost cut, low reasoning effort: −23% a month (Explain fit −33%, drafting −32%, advisor −13%), about twice as fast; quality checks 152/159 → 151/159 | `docs/tokenomics/cost-report-2026-10-21.md`, `docs/tokenomics/measurements-2026-10-21.json` |
| Oct 20 | Problems the cost work found and fixed: 50 plain searches could prune recent AI runs and reset the daily budget and rate limit; cache keys repeated across installations (every new database starts at account 1), so a fresh database read another run's prompt cache; the advisor was flagged for citing the grant of an application it had just read; the report print crashed on the Windows console | `tests/test_costs.py`, `tests/test_advisor.py`, `docs/TOKENOMICS.md` section 9 |
