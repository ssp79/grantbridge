# Fresh-clone test from GitHub, 2026-10-25

**Result: PASS.** This run does what a grader does: clone the public GitHub repository anonymously and follow
the README. A fresh clone installed and answered in a browser **54.7 seconds** after cloning (the course limit
is 10 minutes), the only API key came from a `.env` one folder above the clone, and **all 906 tests passed
inside the clone**.

The earlier test the same day (`fresh-clone-test-2026-10-25.md`) cloned a local snapshot instead. This one
clones `https://github.com/ssp79/grantbridge` over the network with credentials disabled, so it also proves the
repository is public, complete, and clonable by someone who is not signed in.

- **Machine:** Windows 11 Pro, Python 3.12.10, Git Bash.
- **Script:** kept outside the repository, at the session's scratch path. Every number below is copied from its
  log.

## What was tested

1. **Clone**, anonymously: `GIT_TERMINAL_PROMPT=0 git -c credential.helper= clone https://github.com/ssp79/grantbridge`.
2. **Key placement** exactly as the README says: the real `.env` one folder *above* the clone, none inside it,
   and both key variables unset in the shell first.
3. **Install:** `python -m venv .venv`, then `pip install --no-cache-dir -r requirements.txt`.
4. **Start:** `streamlit run streamlit_app.py`, timed until `/_stcore/health` and the page both answered 200.
5. **Key check:** `python -m scripts.check_model`, one tiny live call. It prints where the key came from, never
   the key.
6. **Authentication and a representative workflow**, run against a throwaway database inside the clone.
7. **Tests:** `python -m pytest` inside the clone.

## Results

| Measure | Result |
| --- | --- |
| Clone (network) | 2.3 s |
| Files in the clone | 279 |
| Real `.env` files in the clone | **0** (`.env.example` only) |
| Database (`.db`) files in the clone | **0** |
| Keys in the shell before the run | `PORTKEY_API_KEY` unset, `OPENAI_API_KEY` unset |
| Clone has its own `.env` / parent has one | no / yes |
| `python -m venv .venv` | 3.6 s |
| `pip install --no-cache-dir -r requirements.txt` | 46.4 s |
| Start until the page answered 200 | 1.9 s |
| **Total, clone to answering** | **54.7 s** |
| Health endpoint / page | 200 / 200 |
| Key check | Provider `portkey`, model `gpt-6-luna`, API key **found (parent-folder .env)** |
| Live call | completed, 0.85 s, 16 input + 10 output tokens (26 total) |
| Tests inside the clone | **906 passed** in 467 s |

## Authentication and workflow, inside the clone

| Step | Result |
| --- | --- |
| Sign up a new account | ok |
| Sign in with the **wrong** password | rejected |
| Sign in with the right password | ok, same account |
| Load the sample organization and application | ok |
| Search the sample grants | ok, 10 grants |
| Should We Pursue?, in practice mode (no AI) | ok, outcome `verify` |
| Read another account's application | **blocked** |

## One failed test, and why

The **first** in-clone run reported **905 passed, 1 failed**:
`tests/test_advisor_page.py::test_empty_advisor_offers_examples`, a `RuntimeError`.

That run had a mistake in the harness, not in the project: step 4 had started a Streamlit server against the
clone's own database and **left it running** while `pytest` ran. Re-running the full suite with that server
stopped, and nothing else changed, gave **906 passed**. The test also passes on its own, with or without the
server.

So the failure is a test-isolation problem that appears only when the application is serving from the same
database while the suite runs. **A grader following the README would not meet it**, because the README does not
ask anyone to run the tests while the app is up. It is recorded here rather than left out, and it has not been
fixed: changing test isolation the day before submission is a worse risk than the narrow condition it covers.

## Limits

- One machine, one day. The install time is dominated by `pip` downloading dependencies and varies with the
  network: the same test measured 88.8 s earlier the same day and 47.7 s the day before.
- The workflow check above exercises the Python layer directly, not the browser. The browser path is covered by
  the 52-step run in `e2e-run-2026-10-25.md`, which ran against the working copy rather than this clone.
