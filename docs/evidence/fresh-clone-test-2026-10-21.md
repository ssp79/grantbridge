# Fresh-clone test, 2026-10-21

**Result: PASS, three times.** In the final run, on the finished code, a fresh copy of the repository installed and answered in a browser **59.3 seconds** after cloning (the limit is 10 minutes). The only API key available came from a `.env` file one folder above the repository, and all 724 tests passed inside the clone. The two earlier runs are kept below.

- **Machine:** Windows 11 Pro, Python 3.12.10, Git Bash.
- **Script:** a test script kept outside the repository. Every step it ran is listed below. The numbers are copied from its log.

## What was tested (every run)

1. **Snapshot.** The working folder was committed into a throwaway Git repository outside the project. The snapshot holds only what `.gitignore` lets through, so it is what a real commit and clone would contain. No `.git` folder was created in the project.
2. **Clone.** The snapshot was cloned to `Q:\parent\grantbridge`, and the real `.env` was copied one folder above it, to `Q:\parent\.env`. The clone has no `.env` of its own.
3. **No key in the shell.** The script removed `PORTKEY_API_KEY` and `OPENAI_API_KEY` from its own environment first, as on a grader's machine. That left the parent-folder `.env` as the only place the key could come from.
4. **Install.** `python -m venv .venv`, then `pip install --no-cache-dir -r requirements.txt` (no download cache, like a first install).
5. **Start.** `streamlit run streamlit_app.py`, timed until `/_stcore/health` and the page both answered HTTP 200.
6. **Key check.** `python -m scripts.check_model` made one tiny live call. It prints where the key came from, never the key.
7. **Tests.** `python -m pytest` ran inside the clone.
8. **Cleanup.** The clone and the copied `.env` were deleted.

## Final run: 2026-10-21, about 20:04–20:13 UTC (code with Can We Afford to Win? and the redesigned About page)

| Measure | Result |
|---|---|
| Files in the snapshot | 222 |
| `.env` files in the snapshot | 0 (`.env.example` only) |
| Database (`.db`) files in the snapshot | 0 |
| Snapshot size | 22,195,332 bytes (about 22.2 MB: the screenshots, the two PDFs, `report.html`, and `slides.html`) |
| Largest file | `report.pdf`, 2,284,900 bytes |
| Keys in the shell before the run | `PORTKEY_API_KEY` unset, `OPENAI_API_KEY` unset |
| Clone has its own `.env` / parent has `.env` | no / yes |
| `python -m venv .venv` | 3.3 s |
| `pip install` (no cache) | 54.7 s, exit code 0 |
| App start until HTTP 200 | 1.1 s |
| **Total, empty clone to running app** | **59.3 s** (the limit is 10 minutes) |
| Key check | Provider `portkey`, model `gpt-6-luna`, key **found (parent-folder .env)**. Status completed, 0.53 s, 16 input and 10 output tokens |
| Tests inside the clone | **724 passed** in 438.60 s |
| Copied `.env` removed afterwards | yes |

The install took longer than the earlier run (54.7 s against 37.2 s) on the same requirements; the difference is download speed, not the project. The app's start log had no errors or tracebacks.

## Earlier run: 2026-10-21, about 16:56–17:01 UTC (before Can We Afford to Win?)

| Measure | Result |
|---|---|
| Files in the snapshot | 192 |
| `.env` files in the snapshot | 0 (`.env.example` only) |
| Database (`.db`) files in the snapshot | 0 |
| Snapshot size | 15,424,276 bytes (about 15.4 MB, mostly screenshots, `report.html`, and `slides.html`) |
| Largest file | `docs/screenshots/e2e-01-about-landing.png`, 728,820 bytes |
| Keys in the shell before the run | `PORTKEY_API_KEY` unset, `OPENAI_API_KEY` unset |
| Clone has its own `.env` / parent has `.env` | no / yes |
| `python -m venv .venv` | 3.3 s |
| `pip install` (no cache) | 37.2 s, exit code 0 |
| App start until HTTP 200 | 0.9 s |
| **Total, empty clone to running app** | **41.5 s** (the limit is 10 minutes) |
| Key check | Provider `portkey`, model `gpt-6-luna`, key **found (parent-folder .env)**. Status completed, 1.52 s, 16 input and 10 output tokens |
| Tests inside the clone | **675 passed** in 246.66 s |
| Copied `.env` removed afterwards | yes |

The app's start log had no errors or tracebacks. Git printed its usual Windows notice that line endings would be converted ("LF will be replaced by CRLF") for some files. That notice is about line endings only, and the clone ran normally.

## First run: 2026-10-21 02:57–03:01 UTC (2026-10-20, 22:57–23:01 EDT), earlier code

| Measure | Result |
|---|---|
| Files in the snapshot | 135 |
| `.env` files in the snapshot | 0 (`.env.example` only) |
| Database (`.db`) files in the snapshot | 0 |
| Snapshot size | 9,619,779 bytes (about 9.6 MB, mostly screenshots) |
| Largest file | `docs/screenshots/before-04-advisor-with-activity-panel.png`, 343,623 bytes |
| Keys in the shell before the run | `PORTKEY_API_KEY` unset, `OPENAI_API_KEY` unset |
| Clone has its own `.env` / parent has `.env` | no / yes |
| `python -m venv .venv` | 2.8 s |
| `pip install` (no cache) | 51.4 s, exit code 0 |
| App start until HTTP 200 | 0.9 s |
| **Total, empty clone to running app** | **55.3 s** (the limit is 10 minutes) |
| Key check | Provider `portkey`, model `gpt-6-luna`, key **found (parent-folder .env)**. Status completed, 1.55 s, 16 input and 10 output tokens |
| Tests inside the clone | **445 passed** in 115 s |
| Copied `.env` removed afterwards | yes |

## Problems found along the way

- **First attempt, Windows path limit.** The clone first sat in a deep temporary folder. Pip then failed to write a pyarrow file because Windows limits paths to 260 characters by default. Every later run used a short path (`Q:\`). The README advises graders on Windows to clone into a short folder such as `C:\gb`.
- **Second attempt, key from the shell.** That run passed, but its key check reported "found (shell environment)": this computer has `PORTKEY_API_KEY` set as a user environment variable. So it did not prove the parent-folder fallback. Its numbers were 56.5 s to a running app and 443 tests passed. Both runs reported above remove both keys from the shell first, and their key checks confirm the parent-folder `.env`.
- **Harmless venv warning.** "Actual environment location may have moved due to redirects…" appears because `Q:` is a `subst` drive letter.

## How to repeat it by hand

```bash
git clone <repository-url> C:/gb/grantbridge     # a short path on Windows
cp /path/to/.env C:/gb/.env                      # one folder ABOVE the repository
cd C:/gb/grantbridge
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt     # macOS/Linux: .venv/bin/python
.venv/Scripts/python -m scripts.check_model                 # expect: API key: found (parent-folder .env)
.venv/Scripts/python -m streamlit run streamlit_app.py
```
