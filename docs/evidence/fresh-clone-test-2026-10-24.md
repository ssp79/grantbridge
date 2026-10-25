# Fresh-clone test, 2026-10-24

**Result: PASS.** A fresh copy of the repository installed and answered in a browser **47.7 seconds** after
cloning (the course limit is 10 minutes). The only API key available came from a `.env` file one folder above
the clone, and **all 890 tests passed inside the clone**.

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
| Files in the snapshot | 261 |
| Real `.env` files in the snapshot | **0** (`.env.example` only) |
| Database (`.db`) files in the snapshot | **0** |
| Clone size | 42,400,987 bytes (about 42.4 MB) |
| Largest files | `report.pdf` 2.26 MB, `slides.pdf` 1.97 MB, `report.html` 0.60 MB |
| Keys in the shell before the run | `PORTKEY_API_KEY` unset, `OPENAI_API_KEY` unset |
| Clone has its own `.env` / parent has one | no / yes |
| `python -m venv .venv` | 3.4 s |
| `pip install --no-cache-dir -r requirements.txt` | 42.7 s |
| Start until the page answered 200 | 1.6 s |
| **Total, clone to answering** | **47.7 s** |
| Key check | Provider `portkey`, model `gpt-6-luna`, API key **found (parent-folder .env)** |
| Live call | completed, 1.12 s, 16 input + 10 output tokens |
| Tests inside the clone | **890 passed** in 401 s |

## Notes

- The clone is larger than the 22.2 MB measured on 2026-10-21, because the repository now carries more
  screenshots and a longer report. It is still a normal-sized download.
- A first attempt failed during `pip install` with a Windows 260-character path error, unpacking a deeply
  nested file in numpy's test data. That was the fault of the very long temporary folder the test was run in,
  not of this project: repeating the run from a short path installed cleanly. A grader cloning into a normal
  folder would not meet it, but it is recorded here because it is the kind of thing that looks like a project
  failure and is not.
- The snapshot still contains `report.pdf` and `slides.pdf` as they stood on 2026-10-21. They are stale and
  need reprinting; see `submission_audit.md`.
