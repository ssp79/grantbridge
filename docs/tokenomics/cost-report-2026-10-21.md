# GrantBridge cost measurement

- Run: 2026-10-21 00:57 UTC · live: real model calls through the course Portkey gateway, fresh answers only
- Model: gpt-6-luna (served model gpt-6-luna-2026-09-22)
- Settings: **baseline**: as first built: no reasoning setting is sent, so gpt-6-luna's default effort (medium) applies; **low reasoning**: the cost saver: every model call asks for reasoning effort "low"
- Repetitions: 3 per setting, each in a new fictional account with a cold prompt cache
- Prices (data/pricing.json): OpenAI API pricing, gpt-6-luna, Standard tier, checked 2026-10-20: $0.10 per 1M input tokens, $0.01 cached input, $0.125 cache writes, $0.50 output. Source: https://developers.openai.com/api/docs/pricing
- Usage reported by the provider for 86 of 86 model calls; none were Portkey cache hits.

## Cost per run (mean of the measured cases)

| Workflow | Setting | Cases | AI runs | Model calls | Tool calls | Input tokens | of which cached | written to cache | Output tokens | of which reasoning | Time | Cost per run (min to max) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Explain fit | baseline | 9 | 1 | 1.0 | 0.0 | 1,249 | 0 | 1,246 | 691 | 315 | 7.9 s | $0.00050 ($0.00039 to $0.00056) |
| Explain fit | low reasoning | 9 | 1 | 1.0 | 0.0 | 1,249 | 0 | 1,246 | 355 | 0 | 3.8 s | $0.00033 ($0.00028 to $0.00038) |
| Advisor answer | baseline | 9 | 1 | 2.7 | 2.0 | 4,317 | 1,118 | 2,220 | 588 | 152 | 8.4 s | $0.00068 ($0.00036 to $0.00096) |
| Advisor answer | low reasoning | 9 | 1 | 2.9 | 2.0 | 4,643 | 1,445 | 2,219 | 406 | 0 | 7.6 s | $0.00059 ($0.00037 to $0.00075) |
| Draft one answer | baseline | 3 | 3 | 3.0 | 0.0 | 3,417 | 0 | 2,480 | 3,125 | 1,813 | 38.1 s | $0.00197 ($0.00185 to $0.00207) |
| Draft one answer | low reasoning | 3 | 3 | 3.0 | 0.0 | 3,435 | 0 | 2,498 | 1,874 | 575 | 21.8 s | $0.00134 ($0.00129 to $0.00138) |

## Monthly cost

Assumed use per active nonprofit account per month: 20 × Explain fit, 40 × Advisor answer, 10 × Draft one answer. Model tokens only (no hosting).

| Setting | Per user per month | 100 users | 10,000 users |
|---|---|---|---|
| baseline | $0.0569 | $5.69 | $569.13 |
| low reasoning | $0.0438 | $4.38 | $437.96 |

| Setting | Tokens per user per month | Tokens per day at 10,000 users | Cost per 1M tokens, blended |
|---|---|---|---|
| baseline | 300,397 | 100,132,222 | $0.1895 |
| low reasoning | 287,096 | 95,698,519 | $0.1525 |

Limits at that usage (low reasoning): the per-account budget of 100,000 tokens a day caps one account at about $0.4576 a month, whatever it does. The default server budget of 1,000,000 tokens a day covers about 104 users at this usage, so 10,000 users would need GRANTBRIDGE_SERVER_DAILY_TOKEN_BUDGET of about 143,547,778 (daily average plus 50% headroom).

## low reasoning compared with baseline (same test cases)

| Workflow | Cost per run | Change | Output tokens | Input tokens | Time | Quality checks passed |
|---|---|---|---|---|---|---|
| Explain fit | $0.00050 → $0.00033 | -33% | 691 → 355 | 1,249 → 1,249 | 7.9 s → 3.8 s | 58/63 → 56/63 |
| Advisor answer | $0.00068 → $0.00059 | -13% | 588 → 406 | 4,317 → 4,643 | 8.4 s → 7.6 s | 67/69 → 68/69 |
| Draft one answer | $0.00197 → $0.00134 | -32% | 3,125 → 1,874 | 3,417 → 3,435 | 38.1 s → 21.8 s | 27/27 → 27/27 |
| **Month, 10,000 users** | $569.13 → $437.96 | -23% | | | | |

## Quality checks (the same deterministic checks for every setting)

| Workflow | Check | baseline | low reasoning |
|---|---|---|---|
| Explain fit | Returned a readable explanation | 9/9 | 9/9 |
| Explain fit | Verdict agrees with the automatic checks, with no correction needed | 9/9 | 9/9 |
| Explain fit | No sentence had to be removed (open-status or eligibility claims) | 9/9 | 9/9 |
| Explain fit | Confidence fits the unchecked items (no cap needed) | 4/9 | 2/9 |
| Explain fit | Says the grant is a sample, not a real opportunity | 9/9 | 9/9 |
| Explain fit | Gives at least two reasons | 9/9 | 9/9 |
| Explain fit | Lists something to verify next | 9/9 | 9/9 |
| Advisor answer | Answered by the AI (no fallback, no limit hit) | 9/9 | 9/9 |
| Advisor answer | Looked up the right record (the tool the question needs; sample-01 when asked about it) | 9/9 | 9/9 |
| Advisor answer | Every figure matches a record it retrieved | 9/9 | 9/9 |
| Advisor answer | Cites only grants it looked up | 9/9 | 9/9 |
| Advisor answer | No sentence had to be removed (open-status or eligibility claims) | 8/9 | 9/9 |
| Advisor answer | Names the grant it is about (a top-3 match, or the one asked about) | 9/9 | 8/9 |
| Advisor answer | Stays within the 180 words its instructions allow | 8/9 | 9/9 |
| Advisor answer | Says the grants are samples (fictional demo data) | 6/6 | 6/6 |
| Draft one answer | All three steps answered by the AI (no fallback) | 3/3 | 3/3 |
| Draft one answer | Fact finder asked 1 to 4 questions | 3/3 | 3/3 |
| Draft one answer | Fact finder listed facts the profile already has | 3/3 | 3/3 |
| Draft one answer | Draft stays within the word limit | 3/3 | 3/3 |
| Draft one answer | Draft invents no figures or names (nothing marked [VERIFY]) | 3/3 | 3/3 |
| Draft one answer | Draft uses at least 40% of the word limit | 3/3 | 3/3 |
| Draft one answer | Review covers every requirement | 3/3 | 3/3 |
| Draft one answer | Every review quote is really in the answer | 3/3 | 3/3 |
| Draft one answer | Review writes a summary | 3/3 | 3/3 |

## Every measured run

| Workflow | Case | Setting | Rep | Model calls | Tools | Input | Cached | Written | Output | Reasoning | Time | Cost | Portkey cache |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Explain fit | sample-01: passes every automatic check | baseline | 1 | 1 | 0 | 1,284 | 0 | 1,281 | 454 | 0 | 7.4 s | $0.00039 | refresh |
| Explain fit | sample-08: fails the award range check | baseline | 1 | 1 | 0 | 1,236 | 0 | 1,233 | 629 | 307 | 6.2 s | $0.00047 | refresh |
| Explain fit | sample-07: fails the state check (required) | baseline | 1 | 1 | 0 | 1,226 | 0 | 1,223 | 699 | 423 | 7.0 s | $0.00050 | refresh |
| Advisor answer | Which sample grants fit us best? | baseline | 1 | 2 | 2 | 4,014 | 0 | 3,039 | 800 | 156 | 8.9 s | $0.00088 | refresh |
| Advisor answer | What does the Connecticut After-School Learning Grant require? | baseline | 1 | 4 | 3 | 6,698 | 3,354 | 2,359 | 584 | 122 | 9.7 s | $0.00072 | refresh |
| Advisor answer | How far along are my applications? | baseline | 1 | 2 | 1 | 2,238 | 0 | 1,263 | 216 | 0 | 4.0 s | $0.00036 | refresh |
| Draft one answer | Describe the after-school program this grant would… (find facts) | baseline | 1 | 1 | 0 | 931 | 0 | 0 | 1,263 | 839 | 23.3 s | $0.00072 | refresh |
| Draft one answer | Describe the after-school program this grant would… (draft) | baseline | 1 | 1 | 0 | 1,062 | 0 | 1,059 | 941 | 415 | 9.3 s | $0.00060 | refresh |
| Draft one answer | Describe the after-school program this grant would… (review) | baseline | 1 | 1 | 0 | 1,448 | 0 | 1,445 | 928 | 516 | 8.6 s | $0.00064 | refresh |
| Explain fit | sample-01: passes every automatic check | low reasoning | 1 | 1 | 0 | 1,284 | 0 | 1,281 | 437 | 0 | 4.2 s | $0.00038 | refresh |
| Explain fit | sample-08: fails the award range check | low reasoning | 1 | 1 | 0 | 1,236 | 0 | 1,233 | 334 | 0 | 3.9 s | $0.00032 | refresh |
| Explain fit | sample-07: fails the state check (required) | low reasoning | 1 | 1 | 0 | 1,226 | 0 | 1,223 | 332 | 0 | 3.7 s | $0.00032 | refresh |
| Advisor answer | Which sample grants fit us best? | low reasoning | 1 | 2 | 2 | 4,014 | 0 | 3,039 | 535 | 0 | 6.1 s | $0.00074 | refresh |
| Advisor answer | What does the Connecticut After-School Learning Grant require? | low reasoning | 1 | 4 | 3 | 6,698 | 3,354 | 2,359 | 447 | 0 | 9.5 s | $0.00065 | refresh |
| Advisor answer | How far along are my applications? | low reasoning | 1 | 2 | 1 | 2,238 | 0 | 1,263 | 239 | 0 | 6.4 s | $0.00037 | refresh |
| Draft one answer | Describe the after-school program this grant would… (find facts) | low reasoning | 1 | 1 | 0 | 931 | 0 | 0 | 681 | 220 | 6.1 s | $0.00043 | refresh |
| Draft one answer | Describe the after-school program this grant would… (draft) | low reasoning | 1 | 1 | 0 | 1,062 | 0 | 1,059 | 600 | 128 | 6.3 s | $0.00043 | refresh |
| Draft one answer | Describe the after-school program this grant would… (review) | low reasoning | 1 | 1 | 0 | 1,459 | 0 | 1,456 | 672 | 240 | 6.6 s | $0.00052 | refresh |
| Explain fit | sample-01: passes every automatic check | baseline | 2 | 1 | 0 | 1,284 | 0 | 1,281 | 765 | 421 | 6.5 s | $0.00054 | refresh |
| Explain fit | sample-08: fails the award range check | baseline | 2 | 1 | 0 | 1,236 | 0 | 1,233 | 591 | 227 | 6.3 s | $0.00045 | refresh |
| Explain fit | sample-07: fails the state check (required) | baseline | 2 | 1 | 0 | 1,226 | 0 | 1,223 | 814 | 410 | 17.1 s | $0.00056 | refresh |
| Advisor answer | Which sample grants fit us best? | baseline | 2 | 2 | 2 | 4,014 | 0 | 3,039 | 973 | 348 | 10.0 s | $0.00096 | refresh |
| Advisor answer | What does the Connecticut After-School Learning Grant require? | baseline | 2 | 4 | 3 | 6,698 | 3,354 | 2,359 | 549 | 87 | 9.2 s | $0.00070 | refresh |
| Advisor answer | How far along are my applications? | baseline | 2 | 2 | 1 | 2,238 | 0 | 1,263 | 379 | 145 | 6.2 s | $0.00044 | refresh |
| Draft one answer | Describe the after-school program this grant would… (find facts) | baseline | 2 | 1 | 0 | 931 | 0 | 0 | 1,148 | 659 | 24.4 s | $0.00067 | refresh |
| Draft one answer | Describe the after-school program this grant would… (draft) | baseline | 2 | 1 | 0 | 1,062 | 0 | 1,059 | 601 | 171 | 6.8 s | $0.00043 | refresh |
| Draft one answer | Describe the after-school program this grant would… (review) | baseline | 2 | 1 | 0 | 1,404 | 0 | 1,401 | 1,592 | 1,173 | 13.3 s | $0.00097 | refresh |
| Explain fit | sample-01: passes every automatic check | low reasoning | 2 | 1 | 0 | 1,284 | 0 | 1,281 | 406 | 0 | 4.3 s | $0.00036 | refresh |
| Explain fit | sample-08: fails the award range check | low reasoning | 2 | 1 | 0 | 1,236 | 0 | 1,233 | 259 | 0 | 3.2 s | $0.00028 | refresh |
| Explain fit | sample-07: fails the state check (required) | low reasoning | 2 | 1 | 0 | 1,226 | 0 | 1,223 | 339 | 0 | 3.6 s | $0.00032 | refresh |
| Advisor answer | Which sample grants fit us best? | low reasoning | 2 | 3 | 2 | 5,482 | 1,473 | 3,031 | 520 | 0 | 8.1 s | $0.00075 | refresh |
| Advisor answer | What does the Connecticut After-School Learning Grant require? | low reasoning | 2 | 4 | 3 | 6,698 | 3,354 | 2,359 | 450 | 0 | 9.4 s | $0.00065 | refresh |
| Advisor answer | How far along are my applications? | low reasoning | 2 | 2 | 1 | 2,238 | 0 | 1,263 | 221 | 0 | 4.7 s | $0.00037 | refresh |
| Draft one answer | Describe the after-school program this grant would… (find facts) | low reasoning | 2 | 1 | 0 | 931 | 0 | 0 | 700 | 323 | 17.9 s | $0.00044 | refresh |
| Draft one answer | Describe the after-school program this grant would… (draft) | low reasoning | 2 | 1 | 0 | 1,062 | 0 | 1,059 | 523 | 0 | 4.3 s | $0.00039 | refresh |
| Draft one answer | Describe the after-school program this grant would… (review) | low reasoning | 2 | 1 | 0 | 1,455 | 0 | 1,452 | 549 | 209 | 5.6 s | $0.00046 | refresh |
| Explain fit | sample-01: passes every automatic check | baseline | 3 | 1 | 0 | 1,284 | 0 | 1,281 | 793 | 375 | 7.6 s | $0.00056 | refresh |
| Explain fit | sample-08: fails the award range check | baseline | 3 | 1 | 0 | 1,236 | 0 | 1,233 | 679 | 312 | 6.2 s | $0.00049 | refresh |
| Explain fit | sample-07: fails the state check (required) | baseline | 3 | 1 | 0 | 1,226 | 0 | 1,223 | 791 | 364 | 7.2 s | $0.00055 | refresh |
| Advisor answer | Which sample grants fit us best? | baseline | 3 | 2 | 2 | 4,014 | 0 | 3,039 | 817 | 179 | 8.8 s | $0.00089 | refresh |
| Advisor answer | What does the Connecticut After-School Learning Grant require? | baseline | 3 | 4 | 3 | 6,698 | 3,354 | 2,359 | 563 | 137 | 10.9 s | $0.00071 | refresh |
| Advisor answer | How far along are my applications? | baseline | 3 | 2 | 1 | 2,238 | 0 | 1,263 | 413 | 191 | 7.8 s | $0.00046 | refresh |
| Draft one answer | Describe the after-school program this grant would… (find facts) | baseline | 3 | 1 | 0 | 931 | 0 | 0 | 958 | 516 | 12.0 s | $0.00057 | refresh |
| Draft one answer | Describe the after-school program this grant would… (draft) | baseline | 3 | 1 | 0 | 1,062 | 0 | 1,059 | 773 | 325 | 8.1 s | $0.00052 | refresh |
| Draft one answer | Describe the after-school program this grant would… (review) | baseline | 3 | 1 | 0 | 1,420 | 0 | 1,417 | 1,170 | 826 | 8.7 s | $0.00076 | refresh |
| Explain fit | sample-01: passes every automatic check | low reasoning | 3 | 1 | 0 | 1,284 | 0 | 1,281 | 445 | 0 | 4.1 s | $0.00038 | refresh |
| Explain fit | sample-08: fails the award range check | low reasoning | 3 | 1 | 0 | 1,236 | 0 | 1,233 | 323 | 0 | 3.9 s | $0.00032 | refresh |
| Explain fit | sample-07: fails the state check (required) | low reasoning | 3 | 1 | 0 | 1,226 | 0 | 1,223 | 319 | 0 | 3.7 s | $0.00031 | refresh |
| Advisor answer | Which sample grants fit us best? | low reasoning | 3 | 3 | 2 | 5,482 | 1,473 | 3,031 | 525 | 0 | 7.6 s | $0.00075 | refresh |
| Advisor answer | What does the Connecticut After-School Learning Grant require? | low reasoning | 3 | 4 | 3 | 6,698 | 3,354 | 2,359 | 483 | 0 | 10.2 s | $0.00067 | refresh |
| Advisor answer | How far along are my applications? | low reasoning | 3 | 2 | 1 | 2,238 | 0 | 1,263 | 230 | 0 | 6.7 s | $0.00037 | refresh |
| Draft one answer | Describe the after-school program this grant would… (find facts) | low reasoning | 3 | 1 | 0 | 931 | 0 | 0 | 756 | 345 | 8.7 s | $0.00047 | refresh |
| Draft one answer | Describe the after-school program this grant would… (draft) | low reasoning | 3 | 1 | 0 | 1,062 | 0 | 1,059 | 409 | 0 | 3.6 s | $0.00034 | refresh |
| Draft one answer | Describe the after-school program this grant would… (review) | low reasoning | 3 | 1 | 0 | 1,411 | 0 | 1,408 | 732 | 261 | 6.2 s | $0.00054 | refresh |

## What the user saw (first repetition, fictional demo data)

### Explain fit: sample-01: passes every automatic check

**baseline:** likely fit (confidence medium). The tutoring program appears to match the sample grant’s Connecticut, education, student-age, and funding criteria. This is a sample for the demo, not a real opportunity; the listed deadline status says it is not accepting applications.

**low reasoning:** likely fit (confidence medium). The tutoring program appears closely aligned with this sample grant’s Connecticut, after-school education focus and listed award range. This is a sample for the demo, not a real opportunity.

### Advisor answer: Which sample grants fit us best?

**baseline:** - **Connecticut After-School Learning Grant (sample-01):** Strong program match for your after-school tutoring. Automatic checks meet on state, focus, request range, self-reported 501(c)(3), and budget. Human checks remain: serving K–12 students outside school hours and reporting attendance plus an academic outcome. - **New England Youth Opportunity Fund (sample-05):** Your reported ages and low-income participation appear aligned with its unchecked age and income conditions, but those need human verification. Automatic checks meet on state, focus, request range, self-reported 501(c)(3), and request versus budget. - **Small Nonprofit Capacity Grant (sample-03):** Could match your tutor expansion. Automatic checks meet across all listed criteria; human check: submitting the latest annual financial statement.  I’d prioritize sample-01 for program fit, then sample-05 and sample-03. Automati…

**low reasoning:** The strongest apparent fits are these **fictional sample grants—not real or accepting applications**:  - **Small Nonprofit Capacity Grant (sample-03):** All automatic checks meet, including focus, state, request amount, 501(c)(3) status, budget, and staff size. You’d still need to confirm the requirement to submit your latest annual financial statement. - **Connecticut After-School Learning Grant (sample-01):** All automatic checks meet. Your after-school tutoring appears relevant, but a human must confirm the K–12/outside-school-hours and attendance/outcome requirements. - **New England Youth Opportunity Fund (sample-05):** All automatic checks meet. The age requirement seems consistent with the students you serve; confirm that at least 60% of participants meet its low-income definition.  These rise to the top because they match your focus and requested amount, with the first having few…

### Draft one answer: Describe the after-school program this grant would support, including its schedule and staffing. (400 words)

**baseline:** Draft (215 of 400 words): We provide free after-school tutoring for students in grades 3–8 at two Bridgeport public schools. From October through May, groups of three students meet with a trained volunteer tutor twice a week for 90 minutes. We serve about 140 students each year, and the requested funding would support recruiting, training, and supporting 20 additional volunteer tutors and adding a third partner school, with the goal of serving 50 more students in the 2027–28 school year.  Our program director, a former Bridgeport teacher, leads the work with two site coordinators. Before tutoring, each volunteer completes eight hours of training in reading and math strategies and receives monthly coaching. In 2025–26, 58 tutors contributed about 4,100 hours, and 70% returned for a second year.  We measure student participation through attendance and academic progress through the district…

**low reasoning:** Draft (224 of 400 words): Our After-School Tutoring program provides free, small-group reading and math support to students in grades 3–8 at two Bridgeport public schools. From October through May, groups of three students meet with a trained volunteer tutor twice a week for 90 minutes. With this grant, we would recruit, train, and support 20 additional volunteer tutors and add a third partner school, with the goal of serving 50 more students in the 2027–28 school year.  Our program director, a former Bridgeport teacher, leads the work with two site coordinators. Before starting, every volunteer tutor completes eight hours of training in reading and math strategies, followed by monthly coaching. In 2025–26, 58 tutors contributed about 4,100 hours, and 70% returned for a second year.  We track student attendance and academic progress. Students attended an average of 81% of scheduled sessi…

