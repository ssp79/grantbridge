"""A measured before-and-after example of Review My Proposal with the live model, on sample demo data only.

Usage (from the repo folder):
    python -m scripts.measure_proposal_review            # live: 7 model calls, well under one cent
    python -m scripts.measure_proposal_review --offline  # scripted model: tests this script, measures nothing

The workflow runs through GrantBridge's own functions (the same ones the Applications page calls), for the
sample Harbor Lantern demo application in a throwaway database:
  1. Start from a rough first draft written for this demo (FIRST_DRAFT): question 1 vague, question 3 with an
     award that no record supports and a [NEEDS] placeholder, questions 2 and 4 blank.
  2. Draft the two blank questions ("Draft this answer") and use the drafts as written.
  3. Review the whole proposal: review 1, "before".
  4. Take the three highest-priority recommendations tied to an answered question, "Revise with AI" for each,
     and use each revision as written. (In the app a person reads every suggestion first.)
  5. Review again: review 2, "after".

Two kinds of quality measure are reported separately:
  - Code checks (no AI): unanswered questions, [NEEDS]/[VERIFY] markers, answers over the word limit, and
    figures or names that the profile and facts do not support. They are deterministic.
  - The reviewer's ratings (AI). They are advisory, and the same model rates its own revisions, so a rise is
    not independent evidence of better writing.

Token counts are the provider's own numbers. Live calls ask Portkey for fresh answers, never saved copies.
Writes <out>/proposal-review-before-after-<date>.md and .json (default out: docs/evidence).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from scripts.measure_costs import _temp_env

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "docs" / "evidence"
EMAIL = "before-after@example.org"  # a throwaway account in a throwaway database
FIRST_DRAFT = {  # sample, written for this demo; question numbers follow the sample grant's questions
    1: ("Harbor Lantern Tutoring Collective helps students in Bridgeport. We are a great organization that really "
        "cares about kids, and we have helped many students over the years with tutoring and other things. "
        "Students come to us from different schools and they are very happy with the program."),
    3: ("We track reading. Last year 72% of students who attended at least 30 sessions gained a grade level in "
        "reading. We also won the Bridgeport Literacy Prize in 2024. [NEEDS: math results]"),
}
REVISIONS = 3
USAGE_KEYS = ("model_calls", "input_tokens", "cached_tokens", "cache_write_tokens", "output_tokens",
              "reasoning_tokens", "cost_usd")


# ---------------------------------------------------------------- offline stand-in (tests the script only)

class ScriptedModel:
    """Fixed replies and fixed, made-up token counts. Reports from it say so and are never measurements."""

    USAGE = SimpleNamespace(input_tokens=1000, output_tokens=300,
                            input_tokens_details=SimpleNamespace(cached_tokens=0, cache_write_tokens=1000),
                            output_tokens_details=SimpleNamespace(reasoning_tokens=200))

    def __init__(self):
        self.responses = self
        self.reviews = 0

    def create(self, **kwargs):
        from grantbridge import proposal_review as pr

        name = kwargs["text"]["format"]["name"]
        if name == "proposal_review":
            self.reviews += 1
            score = 2 + self.reviews
            body = {"dimensions": [{"dimension": d, "rating": score, "explanation": "Scripted.", "requirement": None,
                                    "basis": "best practice"} for d in pr.DIMENSIONS],
                    "unsupported_claims": [], "unanswered_parts": [], "missing_information": [],
                    "recommendations": [{"priority": "high", "question_number": n, "action": "Scripted advice.",
                                         "why": "Scripted.", "requirement": None, "basis": "best practice"}
                                        for n in (1, 3, 2)],
                    "summary": "Scripted review."}
        elif name == "section_revision":
            body = {"revised": "Scripted revision. [NEEDS: a fact]", "changes": ["Scripted."]}
        else:
            body = {"draft": "Scripted draft. [NEEDS: a fact]", "facts_used": [], "placeholders": []}
        return SimpleNamespace(output_text=json.dumps(body), usage=self.USAGE, status="completed")


# ---------------------------------------------------------------- measuring

def _usage(outcome) -> dict:
    usage = outcome.data.get("usage") or {}
    return {k: usage.get(k, 0 if k != "cost_usd" else None) for k in USAGE_KEYS} | {
        "served_model": usage.get("served_model", ""), "model_ms": usage.get("model_ms")}


def _timed(label: str, call, *args, **kwargs) -> tuple[dict, object]:
    started = time.perf_counter()
    outcome = call(*args, **kwargs)
    record = {"step": label, "mode": outcome.mode, "notice": outcome.notice,
              "wall_ms": int((time.perf_counter() - started) * 1000), **_usage(outcome)}
    return record, outcome


def _review_summary(review: dict) -> dict:
    p = review["payload"]
    return {"id": review["id"], "mode": review["mode"], "overall": p["overall"], "totals": p["totals"],
            "ratings": {d["dimension"]: d["rating"] for d in p["dimensions"]},
            "caps": {d["dimension"]: d["cap"] for d in p["dimensions"] if d["cap"]},
            "unsupported_claims": len(p["unsupported_claims"]), "recommendations": len(p["recommendations"]),
            "missing_information": len(p["missing_information"]), "rules": p["rules"]}


def measure(client, model: str) -> dict:
    from grantbridge import auth, demo, drafting, proposal_review as pr, repo

    user = auth.sign_up(EMAIL, "correct horse battery staple", "Before After Demo")
    app_id = demo.load_demo_data(user.id)
    sections = repo.list_sections(user.id, app_id)
    for n, text in FIRST_DRAFT.items():
        repo.save_section_answer(user.id, sections[n - 1].id, text)
    steps, revisions = [], []

    for n, s in enumerate(sections, 1):  # 2. draft the blank questions and use the drafts
        if n not in FIRST_DRAFT:
            record, out = _timed(f"Draft question {n}", drafting.draft_section, user.id, s.id, client=client,
                                 model=model)
            steps.append(record)
            drafting.use_draft(user.id, s.id, out.data["draft_id"])

    record, _ = _timed("Review 1 (before)", pr.review_proposal, user.id, app_id, client=client, model=model)
    steps.append(record)
    before = repo.list_proposal_reviews(user.id, app_id)[0]

    targets, seen = [], set()  # 4. revise the top recommendations that point at an answered question
    for r in before["payload"]["recommendations"]:
        q = r["question"]
        if q and q not in seen and len(targets) < REVISIONS:
            seen.add(q)
            targets.append(r)
    for r in targets:
        section = repo.list_sections(user.id, app_id)[r["question"] - 1]
        record, out = _timed(f"Revise question {r['question']}", drafting.revise_section, user.id, section.id,
                             f"{r['action']} {r['why']}", client=client, model=model)
        steps.append(record)
        drafting.use_draft(user.id, section.id, out.data["draft_id"])
        revisions.append({"question": r["question"], "priority": r["priority"], "basis": r["basis"],
                          "feedback": r["action"], "words_before": len(out.data["before"].split()),
                          "words_after": out.data["flags"]["word_count"],
                          "verify_markers_added": out.data["flags"]["flagged"],
                          "placeholders": out.data["flags"]["placeholders"],
                          "sentence_changes": len(pr.sentence_changes(out.data["before"], out.data["text"]))})

    record, _ = _timed("Review 2 (after)", pr.review_proposal, user.id, app_id, client=client, model=model)
    steps.append(record)
    after = repo.list_proposal_reviews(user.id, app_id)[0]
    diff = pr.compare(before, after)
    return {"steps": steps, "before": _review_summary(before), "after": _review_summary(after),
            "revisions": revisions,
            "changed_questions": [{"question": c["question"], "words_before": c["before_words"],
                                   "words_after": c["after_words"], "sentence_changes": len(c["edits"])}
                                  for c in diff["changed"]]}


# ---------------------------------------------------------------- the report

def _money(x) -> str:
    return "not reported" if x is None else f"${x:.5f}"


def render(result: dict, meta: dict) -> str:
    steps, b, a = result["steps"], result["before"], result["after"]
    live = all(s["mode"] == "live" for s in steps)
    lines = [
        f"# Review My Proposal: a measured before-and-after example, {meta['when'][:10]}",
        "",
        f"- **When:** {meta['when']}",
        f"- **Mode:** {meta['mode']}",
        f"- **Model:** {meta['model']}" + (f" (served as `{meta['served_model']}`)" if meta["served_model"] else ""),
        "- **Data:** the sample Harbor Lantern demo organization and the SAMPLE grant's four questions, in a "
        "throwaway database. Questions 1 and 3 start from a rough draft written for this demo (see "
        "`scripts/measure_proposal_review.py`); questions 2 and 4 start blank.",
        "- **How to repeat:** `python -m scripts.measure_proposal_review`",
        "",
    ]
    if not live:
        lines += ["> **Not every step ran live.** Steps marked mock fell back to practice mode; their numbers are "
                  "not model measurements.", ""]
    if meta["mode"].startswith("OFFLINE"):
        lines += ["> **OFFLINE run: scripted model and made-up token counts. Nothing here is a measurement.**", ""]
    lines += ["## The steps", "",
              "| Step | Mode | Model calls | Input tokens (cached) | Output tokens (reasoning) | Estimated cost | Time |",
              "|---|---|---|---|---|---|---|"]
    for s in steps:
        lines.append(f"| {s['step']} | {s['mode']} | {s['model_calls']} | {s['input_tokens']:,} "
                     f"({s['cached_tokens']:,}) | {s['output_tokens']:,} ({s['reasoning_tokens']:,}) | "
                     f"{_money(s['cost_usd'])} | {s['wall_ms'] / 1000:.1f} s |")
    costs = [s["cost_usd"] for s in steps]
    total_cost = None if None in costs else sum(costs)
    lines += [f"| **Total** | | {sum(s['model_calls'] for s in steps)} | "
              f"{sum(s['input_tokens'] for s in steps):,} | {sum(s['output_tokens'] for s in steps):,} | "
              f"{_money(total_cost)} | {sum(s['wall_ms'] for s in steps) / 1000:.1f} s |", "",
              "Time is wall-clock time for the whole step, including GrantBridge's code checks.", "",
              "## Code checks before and after (deterministic, no AI)", "",
              "| Check | Review 1 (before) | Review 2 (after) |", "|---|---|---|"]
    from grantbridge.proposal_review import COUNT_LABELS, DIMENSIONS

    for key, label in COUNT_LABELS.items():
        lines.append(f"| {label} | {b['totals'][key]} | {a['totals'][key]} |")
    lines += ["", "## The reviewer's ratings before and after (AI, advisory)", "",
              "The same model reviewed the proposal and wrote the revisions, so a higher rating is not independent "
              "evidence that the writing improved. Ratings are not a prediction of funding.", "",
              "| Dimension | Before | After | Capped by code (before / after) |", "|---|---|---|---|"]
    for d in DIMENSIONS:
        cap_b = f"to {b['caps'][d]['to']}" if d in b["caps"] else "no"
        cap_a = f"to {a['caps'][d]['to']}" if d in a["caps"] else "no"
        lines.append(f"| {d.capitalize()} | {b['ratings'][d]} | {a['ratings'][d]} | {cap_b} / {cap_a} |")
    lines += [f"| **Average** | **{b['overall']}** | **{a['overall']}** | |", "",
              f"Statements the review could not support (quoted from the answers): {b['unsupported_claims']} before, "
              f"{a['unsupported_claims']} after.", "",
              "## The revisions", "",
              "Each revision followed one recommendation from review 1 and was used as written.", "",
              "| Question | Priority | Basis | Words before → after | Sentences changed | [VERIFY] markers added by code |",
              "|---|---|---|---|---|---|"]
    for r in result["revisions"]:
        marks = ", ".join(r["verify_markers_added"]) or "none"
        lines.append(f"| {r['question']} | {r['priority']} | {r['basis']} | {r['words_before']} → {r['words_after']} "
                     f"| {r['sentence_changes']} | {marks} |")
    lines += ["", "## Limits of this example", "",
              "- One run on one sample application. It shows the workflow and its costs; it is not a study.",
              "- The revisions were used without a person editing them. In the app, every revision is a suggestion "
              "that a person reads, edits, or discards.",
              "- No user test has been run. Nothing here measures how real nonprofit staff would use the feature.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--offline", action="store_true", help="Scripted model with made-up counts (tests only)")
    parser.add_argument("--out", default=str(OUT_DIR), help="Folder for the JSON and the report")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    from grantbridge import llm
    from grantbridge.db import init_db

    when = datetime.now(timezone.utc)
    root, level = logging.getLogger(), logging.getLogger().level
    root.setLevel(logging.WARNING)
    try:
        with tempfile.TemporaryDirectory(prefix="grantbridge-before-after-") as tmp:
            # Measurement-only limits, in this process only, as in measure_costs.py.
            with _temp_env(GRANTBRIDGE_DB=str(Path(tmp) / "measure.db"), GRANTBRIDGE_DAILY_TOKEN_BUDGET="5000000",
                           GRANTBRIDGE_AI_REQUESTS_PER_MINUTE="1000"):
                init_db()
                if args.offline:
                    client, model = ScriptedModel(), "gpt-6-luna"
                    mode = "OFFLINE: scripted model, made-up token counts (not a measurement)"
                else:
                    client, model = llm.get_client(fresh_answers=True)
                    mode = "live: real model calls through the course Portkey gateway, fresh answers only"
                result = measure(client, model)
    finally:
        root.setLevel(level)
    served = next((s["served_model"] for s in result["steps"] if s["served_model"]), "")
    meta = {"when": when.strftime("%Y-%m-%d %H:%M UTC"), "mode": mode, "model": model, "served_model": served}
    report = render(result, meta)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = ("offline-" if args.offline else "") + when.strftime("%Y-%m-%d")
    (out / f"proposal-review-before-after-{stem}.json").write_text(
        json.dumps({"meta": meta, "result": result}, indent=1), encoding="utf-8")
    (out / f"proposal-review-before-after-{stem}.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"Wrote {out / f'proposal-review-before-after-{stem}.md'} and the matching .json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
