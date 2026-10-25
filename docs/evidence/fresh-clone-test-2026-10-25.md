# Fresh-clone test, 2026-10-25

**Result: PASS.** A fresh copy of the repository installed and answered in a browser **88.8 seconds** after
cloning (the course limit is 10 minutes). The only API key available came from a `.env` file one folder above
the clone, and **all 906 tests passed inside the clone**.

This run is on the final code, after the day's last changes: the three committed federal notices and their
re-check, and the word-boundary fix to the injection filter.

- **Machine:** Windows 11 Pro, Python 3.12.10, Git Bash.
- **Script:** kept outside the repository, at the session's scratch path. Every step it ran is listed below, and
  the numbers are copied from its log.

## What was tested

1. **Snapshot.** The working folder was committed into a throwaway Git repository outside the project, so the
   snapshot holds only what `.gitignore` lets through — what a real commit and clone would contain. No `.git`
   folder was created inside the project.
2. **Clone.** The snapshot was cloned to a short path, and the real `.env` was copied one folder *above* the
   clone. The clone has no `.env` of its own.
3. **No key in the shell.** `PORTKEY_API_KEY` and `OPENAI_API_KEY` were unset first, as on a grader's machine,
   leaving the parent-folder `.env` as the only place a key could come from.
4. **Install.** `python -m venv .venv`, then `pip install --no-cache-dir -r requirements.txt`, with no download
   cache, like a first install.
5. **Start.** `streamlit run streamlit_app.py`, timed until `/_stcore/health` and the page both answered 200.
6. **Key check.** `python -m scripts.check_model` made one tiny live call. It prints where the key came from,
   never the key.
7. **Tests.** `python -m pytest` inside the clone.

## Results

| Measure | Result |
| --- | --- |
| Files in the snapshot | 278 |
| Real `.env` files in the snapshot | **0** (`.env.example` only) |
| Database (`.db`) files in the snapshot | **0** |
| Clone size | 41,973,292 bytes (about 42.0 MB) |
| Keys in the shell before the run | `PORTKEY_API_KEY` unset, `OPENAI_API_KEY` unset |
| Clone has its own `.env` / parent has one | no / yes |
| `python -m venv .venv` | 4.0 s |
| `pip install --no-cache-dir -r requirements.txt` | 83.6 s |
| Start until the page answered 200 | 1.2 s |
| **Total, clone to answering** | **88.8 s** |
| Key check | Provider `portkey`, model `gpt-6-luna`, API key **found (parent-folder .env)** |
| Live call | completed, 16 input + 10 output tokens (26 total) |
| Tests inside the clone | **906 passed** in 912 s |

## Notes

- **Why this is slower than the 47.7 s measured on 2026-10-24.** Almost all of the difference is `pip`: 83.6 s
  here against 42.7 s then, downloading the same dependency list with no cache. The project's own startup was
  1.2 s, slightly faster than before. Both runs are well inside the ten-minute limit, and the honest reading is
  that this number is dominated by network speed on the day, not by the project.
- The snapshot was taken before `report.pdf` and `slides.pdf` were reprinted later the same day, so the copies
  inside this clone are the older ones. The repository's own copies are current: 15 and 10 pages. Nothing else
  in the clone differs from the submitted code.
- A first attempt on 2026-10-24 failed during `pip install` with a Windows 260-character path error, unpacking a
  deeply nested file in numpy's test data. That was the fault of the very long temporary folder the test ran in,
  not of this project: repeating the run from a short path installed cleanly. A grader cloning into a normal
  folder would not meet it, but it is recorded because it looks like a project failure and is not.
