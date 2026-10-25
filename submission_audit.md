# GrantBridge submission audit

For Sam, before submitting on Canvas (due **Monday 2026-10-26, 6:00 PM**). It maps every rubric row to its evidence, lists what is still missing, and gives the exact GitHub commands. **Nothing has been committed, pushed, published, or deployed.**

## At a glance (2026-10-24)

**Ready:**

- **Browser run:** 52 of 52 steps passed, with live AI and live Grants.gov, on the final code (`docs/evidence/e2e-run-2026-10-25.md`).
- **Tests:** **906 passed, 0 failed, 0 warnings** in 904.5 s on the final code (`docs/evidence/test-run-2026-10-25.md`).
- **Three real federal notices:** the import was run against the Fish and Wildlife, FHWA and NOAA notices, and all 240 quotations in the three outlines re-check against the notice each came from, with none missing (`docs/evidence/real-solicitations-2026-10-23.md`, reproducible offline with `python -m scripts.check_real_solicitations`). That exercise also exposed a false positive in the injection filter, now fixed and tested; report §6.
- **Fresh clone:** an empty clone ran in **88.8 s**, with the key read from a `.env` one folder above the repository, and **906 tests passed inside the clone** (measured 2026-10-25 on the final code; the 47.7 s measured on 10-24 differed almost entirely in `pip` download time).
- **Report and slides:** `report.html` prints at 15 letter pages, and `slides.html` has 10 slides (reveal.js 5.1.0, inlined, no CDN). Both open offline (0 network requests, measured). `report.pdf` and `slides.pdf` are printed from them.
- **Demo video:** `demo-video/grantbridge-demo-2026-10-24.webm`, an automated captioned recording of the running app (3 min 57 s, 1280 x 720, 41 MB), including a scene that reads a solicitation PDF into a proposal outline. It is not committed; attach it to Canvas from that folder. The 10-21 and 10-23 recordings in the same folder are earlier versions and are superseded.

**Missing, and only Sam can do it:**

1. The GitHub repository and its URL (commands in section 3).
2. ~~Reprint the two PDFs~~ — **done on 2026-10-25.** `report.pdf` (15 pages) and `slides.pdf` (10 pages) in this folder are printed from the current HTML. To rebuild them yourself: `python -m scripts.print_pdfs --browser chromium`.
3. ~~A real user test~~ — **done on 2026-10-24**; see `docs/evidence/user-test-2026-10-24.md`.
4. Optional: a narrated video in your own voice, if you want one instead of the automated recording.

## 1. Rubric crosswalk (100 points)

"Ready" means the evidence exists in the repository. It is not a prediction of the grade.

| Rubric row | Points | What it asks for | Evidence in the repository | Status |
|---|---|---|---|---|
| **Idea** | 21 | A real twist on an overdone idea. Tier 3 needs a real user, a before-and-after measurement, and an org-scale cost | The twist: decide before you apply, and code decides while the AI explains (report §3, `docs/COMPETITORS.md`, the public website). **Can We Afford to Win?** adds a question no competitor page we read answers: whether winning a grant would tie up more cash than the organization has, simulated day by day from quoted award terms. Before and after: the proposal loop measured on the software, plus the two defects a real user found and the behaviour that replaced them (report §7). **Real user: a director at a small nonprofit working with at-risk young people, 2026-10-24, all tasks unaided, seven observations, all fixed** (`docs/evidence/user-test-2026-10-24.md`). Org-scale cost: $599 a month at 10,000 accounts (report §5) | Ready. The before-and-after is measured on the software; one unmoderated session cannot measure a user's own before and after |
| **App: works** | 15 | The app works end to end | The browser run passed 52 of 52 steps: the public website and its live demonstration, sign-up, demo data, sample and live search, AI explanation, advisor with tools, drafting, proposal review and revision, budget, timeline, Should We Pursue?, Can We Afford to Win? (terms, numbers, scenarios, explanation, and its effect on the outcome and the portfolio), portfolio, mission drift, reading a solicitation PDF into an application and checking the answers against its requirements, the proposal outline read from a solicitation, phone width, and the blocked attack. **906 tests passed**, no warnings. The same import was also run against three real federal notices (`docs/evidence/real-solicitations-2026-10-23.md`) | Ready |
| **App: staff can run it** | 5 | Runs online, or from a fresh clone via the README in under 10 minutes | README "Quick start". Fresh clone on the final code: **88.8 s** from clone to a page answering, key read from the parent-folder `.env`, 906 tests passing inside the clone (`docs/evidence/fresh-clone-test-2026-10-25.md`). Practice mode if the key fails (section 5) | Ready |
| **App: look and feel** | 10 | Polished, usable interface | Section 1 of `evidence_manifest.md`. The five-page public website (licensed photograph, real product screens, live demonstrations a visitor can change), one shared design system across the public site and the application, the Dashboard's first-run steps, consistent cards and labels, 390 px phone layouts with no sideways scrolling (measured), and before-and-after redesign screenshots | Ready |
| **Report: motivation** | 8 | Why it matters, with sources | §2: the National Council of Nonprofits figure on how small most nonprofits are, and the Urban Institute (2013) and Tennessee Nonprofit Network (2024) findings on late payments and matching requirements. Every quotation was checked in the source file, with its access date and the PDF's hash (`docs/evidence/sources-2026-10-21.md`) | Ready |
| **Report: agents** | 10 | Tools, diagram, model choice, one real run traced, with screenshots | §4: the seven advisor tools; every AI step and the code around it, including the two in Can We Afford to Win?; the architecture and decision diagrams; why gpt-6-luna and why so much code; one traced run from the server log, with both its screenshots (the answer and its trace) | Ready |
| **Report: tokenomics** | 8 | Real measured tokens including cached input; cost per run, per user-month, and at 100 and 10,000 users; cost cuts and whether they hurt quality | §5: provider token counts with cache reads and writes for 10 workflows, from fresh calls only. Monthly cost at 1, 100, and 10,000 accounts, split by feature group. The low-reasoning cut: 23% cheaper and faster, with quality checks before and after. Reuse and code-only features | Ready |
| **Report: safety** | 8 | Attacks, malfunction, overspending; at least one defense shown working | §6: a risk table (injection, leaks, invented facts, invented award terms, overconfidence, invented deadlines or money, other accounts' data, runaway cost). A real blocked attack in the browser (S2 to S4 screenshots), the live red-team report (PASS), and the measured term extraction: 0 invented and 0 wrong in 150 field readings, one notice carrying an injected instruction | Ready |
| **Report: impact** | 5 | Sourced numbers, ideally a real user | §7: **a director at a small nonprofit working with at-risk young people used GrantBridge on 2026-10-24**, completed every task unaided, and gave seven observations; two were real defects, and all seven were fixed (`docs/evidence/user-test-2026-10-24.md`). Plus the sourced sector figure, the sample demonstration of a grant that fits but would strain the cash, the term-extraction evaluation against known answers, and the before-and-after proposal loop | Ready |
| **Report: design** | 2 | Readable, self-contained | Letter-size print CSS, 15 pages, embedded images, no outside requests, and a 390 px phone layout. `report.pdf` is printed from the same file | Ready |
| **Slides: content** | 6 | At most 10 slides: title, problem, what's new, agent diagram, demo screenshots, cost, safety, impact, next steps | 10 slides in exactly that order, with the demo on two slides (deciding before you write, and Can we afford to win?) | Ready |
| **Slides: design** | 2 | Self-contained | reveal.js 5.1.0, the version the course suggested, but **inlined into the file** instead of loaded from a CDN, so the deck opens offline. Its MIT license and the download's hashes are in `vendor/reveal.js-5.1.0/`. Images are embedded; `slides.pdf` prints one slide per page | Ready |

**Course rules checked:**

| Rule | How it is met | Evidence |
|---|---|---|
| `PORTKEY_API_KEY` with gpt-6-luna only; `OPENAI_API_KEY` only for your own model | `grantbridge/config.py` fixes the model to gpt-6-luna for the Portkey key | Fresh-clone key check: provider `portkey`, model `gpt-6-luna` |
| `.env` from the repository folder first, then the parent folder | `grantbridge/config.py`; the repository's `.env` wins if both exist | `tests/test_config.py`; fresh clone: "found (parent-folder .env)" |
| `.env.example` with key names only; never commit a real `.env` | `.gitignore` excludes `.env` and `.env.*` except the example | The scan in section 2: 0 `.env` files, and neither real key value appears anywhere |
| `report.html` and `slides.html` self-contained | Images are embedded as data URIs; no CDN | 0 network requests when each was opened in a browser |
| Report 10 to 15 printed pages; at most 10 slides | 15 letter pages; 10 slides | Printed to PDF and counted |
| Sample data and test accounts only | Sample demo profile, SAMPLE grants, and generated test accounts | The scan's email and phone results (section 2) |
| Not presented as production-grade security | The README, sign-in page, Trust & Responsible AI page, and report §6 and §8 say so | `docs/SECURITY.md` |

## 2. What a first commit would contain (scanned 2026-10-21)

The scan used a throwaway Git directory outside the project, with the project as its work tree. No `.git` folder was created in the project. It reports only counts and locations, never a secret's value.

| Check | Result |
|---|---|
| Files a first commit would contain | 222 (22.2 MB) |
| `.env` files | 0 (`.env.example` only) |
| Database files (`.db`, `.sqlite3`) | 0 |
| The real `PORTKEY_API_KEY` and `OPENAI_API_KEY` values, searched for in every file | **0 occurrences** |
| Key-like strings | 8 matches, all deliberate fakes in tests or the red-team script (such as `sk-proj-FAKEFAKE…`, `parent-key`, and a fake Bearer token) |
| Private key blocks | 0 |
| Email addresses outside example domains | Test-only, invented addresses on reserved `.example` domains (`attacker.example`, `harbor.example`, `harborlantern.example`) |
| Phone numbers | 5, all in the 555-01xx range reserved for fiction, in tests |
| Local paths with your user name | 0. A few files mention the word "OneDrive" in prose or a comment |
| Largest file | `report.pdf`, 2.3 MB. No file is near GitHub's 50 MB warning |

On Windows, Git prints "LF will be replaced by CRLF" for many files when it stages them. That is a line-ending notice, not an error; the fresh clone ran normally.

## 3. GitHub: the exact commands (not run; they need your approval)

They create a repository **on your GitHub account**, so run them yourself when you decide to. Open PowerShell in the `grantbridge` folder (the one that contains `README.md`), then:

```powershell
# 1. Stage everything .gitignore allows, then check that no .env or database is staged
git init -b main
git add -A
git status --short | Select-String -Pattern '\.env$', '\.db$'   # must print nothing (.env.example is fine)

# 2. The first commit
git commit -m "GrantBridge: AI Foundations final project" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"

# 3. Check which GitHub account gh will use, then create the repository and push (choose one)
gh auth status
gh repo create grantbridge --private --source . --remote origin --push
#   or public:  gh repo create grantbridge --public --source . --remote origin --push

# 4. Private repository only: give the course staff (zlisto) read access
gh api -X PUT "repos/{owner}/{repo}/collaborators/zlisto" -f permission=pull

# 5. Put the repository's link into the report and slides, then push again
.venv\Scripts\python -m scripts.build_deliverables --repo-url https://github.com/<your-user>/grantbridge
git add report.html slides.html
git commit -m "Add the repository link to the report and slides"
git push

# 6. Look at it on GitHub
gh repo view --web
```

Notes:

- `{owner}` and `{repo}` in step 4 are filled in by `gh` from the repository you just created. Type them exactly as shown.
- A collaborator invitation must be accepted. Check that zlisto appears under **Settings → Collaborators** on GitHub.
- If you would rather not use `gh`, create an empty repository on github.com (no README), then run `git remote add origin <url>` and `git push -u origin main`.
- The second line of the commit message credits the AI assistance. Remove it if your course has a different rule for that.

## 4. Canvas checklist

- [ ] GitHub repository URL. Public, or private with **zlisto** added as a collaborator (step 4 above).
- [ ] `report.html` from the repository folder (self-contained; rebuilt with the repository URL in step 5). `report.pdf` is beside it if a PDF is wanted.
- [ ] `slides.html` from the repository folder (self-contained), or `slides.pdf`.
- [ ] Optional: the demo video, `demo-video/grantbridge-demo-2026-10-21.webm`. It is not in the repository, so attach it from that folder. Most browsers play WebM; if Canvas will not take it, say so and I will convert it.
- [ ] Before submitting: `.venv\Scripts\python -m pytest` once more, and open both files in a browser.

## 5. If the staff key does not work: use practice mode, not a deployment

**Recommendation: submit the repository as it is. Practice mode is the fallback.** No deployment is needed.

- Practice mode turns on by itself when no key is found (`grantbridge/llm.py`, `choose_mode`). Each AI page also has a practice-mode toggle, and `GRANTBRIDGE_ADVISOR_MODE=mock` sets it for the whole app. AI results are then labeled MOCK, and no AI call is made.
- Most of GrantBridge is code and works the same without a key: the eligibility checks, Should We Pursue? outcomes, the Portfolio Strategist and its weekly capacity, budget arithmetic, workback plans, and the sample-grant search.
- A fresh clone runs in under a minute, so a grader with a key can run it locally. With only `OPENAI_API_KEY`, GrantBridge calls OpenAI directly, with the model named in `OPENAI_MODEL` (gpt-6-luna if unset).
- A hosted deployment would put the course key behind a public sign-up page, and it would need HTTPS and secret handling. Do it only if the course requires an online app, and only with your approval. The server-wide daily token limit (1,000,000 tokens by default) would bound its cost.

## 6. Decisions and blockers for you

| Item | Why it needs you | Suggested next step |
|---|---|---|
| GitHub repository | It is your account | Run section 3 when ready |
| Real user test | **Done 2026-10-24.** A director at a small nonprofit working with at-risk young people, 20-30 minutes, all tasks unaided, seven observations, all fixed | `docs/evidence/user-test-2026-10-24.md` |
| Demo video | An automated recording exists; a narrated one would be yours | Watch `demo-video/grantbridge-demo-2026-10-21.webm` and decide whether to submit it as it is, or record your own with narration. It is an automated tour with on-screen captions and no voice; the report says so |
| Notices are pasted, not uploaded | Can We Afford to Win? takes the funder's notice as pasted text. A file upload would break the project's no-uploads security rule and its test | Keep paste-only unless you want uploads; tell me if you do, and I will add them with the rule changed deliberately |
| Deploy or not | It is a public, outward-facing change | Section 5 recommends not deploying |

## 7. Where the earlier requests ended up

The earlier four-feature request was merged into the three-feature specification:

| Requested | Where it is |
|---|---|
| Grant Readiness Assessment | The readiness dimension of **Should We Pursue?** (and the profile completeness on the Dashboard) |
| Application Requirements Checklist | The **Requirements & source** tab, the **Needs human verification** checklist, and "What we still need to know" in Should We Pursue? |
| Proposal Quality Review | The **Review proposal** tab |
| Budget Narrative Assistant | The **Budget & narrative** tab |

## 8. How the deliverables stay honest

- `python -m scripts.build_deliverables` builds `report.html` and `slides.html` from the evidence files: test results, the browser run, token measurements, the advisor trace, and the fresh-clone test.
- The build stops if a quoted figure is no longer in its source file. It also stops if a measurement includes a cached or practice-mode call, or if the browser-run summary misses a step.
- Screenshots are real runs, cropped or resized for the slides and the report, never edited. `evidence_manifest.md` lists every one, with what it proves.
