# GrantBridge and the grant-tool landscape

**Checked on 2026-10-21.** Every competitor statement below comes from that vendor's own web page, read on that date, and is a **vendor claim**. None was tested by us, and none is independently verified. "Not stated" means the pages we read do not describe the capability; it does **not** mean the product lacks it. Prices change: check the vendor's page.

## The matrix

| | Instrumentl | Candid (Candid search, formerly Foundation Directory) | GrantStation | Grantable | Grant Assistant | Granted AI | Grants.gov | **GrantBridge** (this project) |
|---|---|---|---|---|---|---|---|---|
| **Grant discovery** | "450,000+ funder profiles", "37,000+ active RFPs", "AI-powered matching" | "300,000+ grantmaker profiles", "29 million+ nonprofit grants" | "350,000 funder records", "15,000+ curated funding opportunities" | "Search 150,000+ funders" | "matches you with best-fit funding opportunities" | "140,000+ grants", "AI matches your mission to 133K+ foundations" | Free federal search: keyword, eligibility, category, agency, and status filters | 10 sample grants and live Grants.gov federal search, with every listing labeled by source (tested) |
| **Fit and eligibility** | "Intelligent Eligibility Vetting", "Match Insights" | Funder profiles and recommendations | Review "funder priorities, eligibility, giving history" | "Fit assessment that shows its work" (22 criteria) | Not stated | "Readiness Quiz" linked, not described | Eligibility filter on listings | Code checks marked met, failed, or **unknown**. Unknown is never treated as ineligible; user confirmations are labeled as the user's; a failed check cannot be confirmed away (tested) |
| **Go/no-go or prioritization** | Not stated | Not stated | "Decision Matrix" to prioritize (described in GrantStation materials as a weighted-criteria method) | Not stated beyond fit scoring | Not stated | Not stated beyond matching | No | Four outcomes from **explicit rules the AI cannot override**, plus a portfolio score from weights you set (tested) |
| **Staff capacity against deadlines** | Not stated ("75% time saved per application" is a time claim) | Not stated | Calendars and goal-setting tools | Deadline extraction and reminders | Not stated | Not stated | No | Weekly hours, editable estimates, and commitments, scheduled earliest-deadline-first. Grants that do not fit are deferred, with the hours short (tested) |
| **Mission-drift check** | Not stated | Not stated | Not stated | Not stated | "stays true to your mission and voice" (about drafting) | Not stated | No | Five areas rated low, moderate, high, or unknown. Every rated concern quotes the grant word for word, and the profile when a verbatim quote fits. Code-checked geography wins over the AI (tested) |
| **AI proposal drafting** | "AI drafting" adapts previous proposals | "AI-powered LOI writing tool", "Fundraising assistant" | Templates and "step-by-step guidance" | AI writing "from first draft to final polish", content library | Proposal drafting, "Trained on 7,000+ winning proposals" | "AI LOI Writer", "Grant Writing Coach" | No | Drafts only from your profile and facts. Gaps become `[NEEDS]`, and figures the facts do not support become `[VERIFY]` (tested) |
| **Proposal review** | Not stated as a separate feature | Not stated | "Proposal Reviewer" | Inline AI editing | Not stated | "Granted Review Board" | No | A five-dimension advisory scorecard with code caps, verified quotes, best practice kept apart from funder requirements, and before-and-after comparisons (tested) |
| **Budget** | "Funder budget extraction", "Live expense tracking" (post-award) | Budget estimate in the fundraising assistant | Not stated | Not stated | Not stated | "Cost Calculator" linked, not described | No | Exact arithmetic in Python, checks against the request and award range, and a narrative from the lines only; pending money is never called committed (tested) |
| **Award terms and cash flow, before applying** | Post-award: "Funder budget extraction" and "Live expense tracking" ("budget-vs-actual reports ready on demand") | A fundraising-assistant "Budget estimator" that "Provides guidance on setting an appropriate budget for a grant request" | A Grant Readiness Roadmap, an organization-wide self-assessment, asks whether you can "manage a cash flow gap if grant funds are distributed on a reimbursement basis"; it "does not evaluate readiness for a specific grant opportunity" | Checklist extraction pulls limits from an RFP (its example: "Indirect ≤ 15% — Appendix C, p. 27") | Not stated | Not stated (its "Cost Calculator" gives "a realistic estimate of consultant fees for your grant proposal") | A yes/no "Cost Sharing or Matching Requirement" field | Per grant: each award term quoted from the listing or a pasted notice; the match computed; the cash the award would tie up simulated day by day against your reserves; what-if scenarios. A term no quote supports stays unknown (tested) |
| **Deadlines and planning** | Tasks from the award letter, calendar sync | Not stated | Calendars | Reminders "at 7·3·1 days" | Not stated | "Deadline Calendar" linked | Close dates on listings | A seven-step workback plan with source-labeled deadlines and a `.ics` file. No reminders are sent (tested) |
| **Price shown** | "Try 14 days free" (no price shown) | Premium $1,199 a year; Ultimate $1,699 a year; Premium monthly $219 | "41 cents a day" promotion | "Start free", "from $50/month" | "Book a demo" (no price) | "Free to start", from $29 a month | Free | Free course demo |

**Sources (all accessed 2026-10-21):**

- Instrumentl: https://www.instrumentl.com/
- Candid: https://candid.org/find-funding
- GrantStation: https://grantstation.com/
- Grantable: https://grantable.co/features
- Grant Assistant: https://grantassistant.ai/
- Granted AI: https://grantedai.com/
- Grants.gov: https://www.grants.gov/search-grants
- GrantStation's decision matrix, as a method: TechSoup, https://blog.techsoup.org/posts/grant-research-make-better-strategic-decisions-with-a-decision-matrix

**Award terms and cash flow (all accessed 2026-10-21; each quote was checked in the page's own HTML):**

- Instrumentl, post-award section of the home page: https://www.instrumentl.com/
- Candid's fundraising assistant: https://candid.org/fundraising-assistant/
- GrantStation's Grant Readiness Roadmap: https://grantstation.com/public-resources/grant-readiness-roadmap
- Grantable's checklist extraction: https://www.grantable.co/features/checklist-extraction
- Granted AI's cost calculator: https://grantedai.com/tools/cost-calculator
- Grant Assistant: https://grantassistant.ai/respond ("summarizes your funding opportunity into a two-page brief") and https://grantassistant.ai/faq ("Post-award grant management features are on the Grant Assistant product roadmap")
- Grants.gov's synopsis form: https://grants.gov/help/grantors/create-synopsis ("Cost Sharing or Matching Requirement: Select Yes or No.")
- Found in a web search, outside the seven: Grantsights' free Grant Budget Calculator, https://grantsights.com/tools/grant-budget-calculator. It says: "Before writing, check whether the federal request, match requirement, documented match, and indirect cost assumptions fit the opportunity". It reports a "match gap". Its page does not describe reimbursement timing, cash flow, or reserves.

## What is specific to GrantBridge

Several tools claim to help with fit, eligibility, prioritization, or review (see the matrix). GrantBridge's difference is **how** it decides, and the combination:

1. **Decisions come from code, not from the model.** Should We Pursue? decides from rules listed on the page, and the AI only adds fit evidence. The same holds for proposal-review caps, budget arithmetic, schedules, and portfolio selection.
2. **Uncertainty is first-class.** "Unknown" is a status of its own, never a silent "no". A person may confirm an unknown item, and it is then labeled as confirmed by them.
3. **Capacity is scheduled, not just counted.** The portfolio keeps a grant only if every deadline still fits the organization's weekly hours (earliest-deadline-first, day by day). It says exactly why a grant is deferred.
4. **Mission drift is checked with evidence.** A rated concern must quote the grant's own text word for word, or it is dropped. A quote from the profile is kept only if it is verbatim too.
5. **AI output is verified by code before anyone sees it.** Unsupported figures are marked `[VERIFY]`, quotes are matched against the source text, funding predictions are removed, and grant text is treated as untrusted data.
6. **Winning is checked for affordability, grant by grant.** Can We Afford to Win? reads the award terms with verbatim quotes, computes the match, and simulates the cash the award would tie up against the organization's reserves. The AI reads; code counts. A term no quote supports stays unknown.
7. **One profile serves every feature**, and every grant fact shows where it came from.

We found nothing on the pages above that schedules recommendations against weekly staff hours, checks mission drift, or simulates one grant's cash needs against the organization's reserves. The closest to the last were an organization-wide self-assessment (GrantStation), post-award budget tracking (Instrumentl), and a free calculator of a request's match gap (Grantsights). We do **not** claim GrantBridge is the first or only tool to do any of these: we checked seven products' own pages and a few web searches, on one day.

**What competitors have that GrantBridge does not:**

- far larger funder databases;
- foundation and 990 data;
- integrations (Salesforce, calendars), team collaboration, and post-award tracking;
- years of real users.

GrantBridge searches 10 sample samples and live Grants.gov federal listings, and nothing else.
