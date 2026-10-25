"""Measure what the newer AI features cost per run, with the live model, on sample demo data only.

Usage (from the repo folder):
    python -m scripts.measure_new_features            # live: 5 workflows x 3 repetitions, about 15 model calls
    python -m scripts.measure_new_features --reps 1
    python -m scripts.measure_new_features --offline  # scripted model with made-up counts: tests this script only

Workflows, each through GrantBridge's own functions (the ones the pages call):
    Proposal review     Review my proposal on the demo application (two answers typed in, two drafted)
    Revise one answer   Revise with AI on one answer, from a recommendation
    Budget narrative    the narrative for three sample budget lines
    Pursuit assessment  Should We Pursue? on the SAMPLE Connecticut grant (the AI writes fit evidence)
    Mission drift       the mission-drift check on the SAMPLE workforce grant

Every repetition uses a new sample account in a throwaway database, and live calls ask Portkey for fresh
answers, so no measured call is a saved copy. Token counts are the provider's own; costs use data/pricing.json.
Writes <out>/new-features-costs-<date>.json and .md (default out: docs/tokenomics).
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from scripts.measure_costs import _temp_env

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "docs" / "tokenomics"
TODAY = date(2026, 10, 21)  # fixed, so the sample grants' example deadlines lie ahead in every repetition
ANSWERS = {  # sample, as in measure_proposal_review.py
    1: "Harbor Lantern helps students in grades 3-8 in Bridgeport become confident readers and math learners through "
       "free small-group tutoring led by trained volunteers. We serve about 140 students a year at two public schools.",
    3: "In the 2025-26 school year, 72% of students who attended at least 30 sessions gained a grade level in reading, "
       "and 64% did so in math. Students attended 81% of scheduled sessions on average.",
}
BUDGET = [
    {"category": "Personnel", "description": "Volunteer coordinator (part time)", "quantity": "0.5", "unit": "FTE",
     "unit_cost": "36000", "funding_source": "grant", "justification": "Recruits, trains, and schedules 20 new tutors."},
    {"category": "Training", "description": "Tutor training workshops", "quantity": "4", "unit": "workshops",
     "unit_cost": "750", "funding_source": "grant", "justification": "Four Saturday trainings for new volunteers."},
    {"category": "Supplies and materials", "description": "Family Learning Night materials", "quantity": "4",
     "unit": "events", "unit_cost": "500", "funding_source": "cash_pending", "source_name": "A local service club",
     "justification": "Printed activities in English, Spanish, and Portuguese."},
]
WORKFLOWS = ["Proposal review", "Revise one answer", "Budget narrative", "Pursuit assessment", "Mission drift"]
KEYS = ("model_calls", "input_tokens", "cached_tokens", "cache_write_tokens", "output_tokens", "reasoning_tokens",
        "cost_usd", "elapsed_ms")


class ScriptedModel:
    """Fixed replies and fixed, made-up token counts. Reports from it say so and are never measurements."""

    USAGE = SimpleNamespace(input_tokens=1000, output_tokens=300,
                            input_tokens_details=SimpleNamespace(cached_tokens=0, cache_write_tokens=1000),
                            output_tokens_details=SimpleNamespace(reasoning_tokens=100))

    def __init__(self):
        self.responses = self

    def create(self, **kwargs):
        name = kwargs["text"]["format"]["name"]
        body = {
            "proposal_review": {"dimensions": [], "unsupported_claims": [], "unanswered_parts": [],
                                "missing_information": [], "recommendations": [], "summary": "Scripted."},
            "section_revision": {"revised": "Scripted revision.", "changes": []},
            "budget_narrative": {"narrative": "Scripted narrative.", "lines_described": []},
            "pursuit_fit": {"fit_points": [], "gaps": [], "summary": "Scripted."},
            "mission_drift": {"concerns": [], "summary": "Scripted."},
        }[name]
        return SimpleNamespace(output_text=json.dumps(body), usage=self.USAGE, status="completed")


def _usage(outcome) -> dict:
    usage = outcome.data.get("usage") or {}
    return {k: usage.get(k) for k in KEYS} | {"served_model": usage.get("served_model", ""),
                                              "gateway_cache": usage.get("gateway_cache", []), "mode": outcome.mode}


def one_repetition(client, model: str, rep: int) -> list[dict]:
    from grantbridge import auth, budget, demo, drafting, mission_drift, proposal_review, pursuit, repo

    user = auth.sign_up(f"measure-{rep}@example.org", "correct horse battery staple", f"Measure {rep}")
    app_id = demo.load_demo_data(user.id)
    sections = repo.list_sections(user.id, app_id)
    for n, text in ANSWERS.items():
        repo.save_section_answer(user.id, sections[n - 1].id, text)
    records = []

    def record(workflow, outcome):
        records.append({"workflow": workflow, "rep": rep, **_usage(outcome)})

    record("Proposal review", proposal_review.review_proposal(user.id, app_id, client=client, model=model))
    feedback = "Add the attendance measure and the source of the reading and math results."
    record("Revise one answer", drafting.revise_section(user.id, sections[2].id, feedback, client=client,
                                                        model=model))
    for line in BUDGET:
        repo.add_budget_item(user.id, app_id, line)
    record("Budget narrative", budget.write_narrative(user.id, app_id, client=client, model=model, target_words=200))
    record("Pursuit assessment", pursuit.assess(user.id, grant_id="sample-01", client=client, model=model,
                                                today=TODAY))
    record("Mission drift", mission_drift.check(user.id, "sample-07", client=client, model=model, today=TODAY))
    return records


def summarize(records: list[dict]) -> list[dict]:
    out = []
    for workflow in WORKFLOWS:
        rows = [r for r in records if r["workflow"] == workflow and r["mode"] == "live"]
        if not rows:
            out.append({"workflow": workflow, "runs": 0})
            continue
        mean = {k: statistics.mean(r[k] or 0 for r in rows) for k in KEYS}
        costs = [r["cost_usd"] for r in rows if r["cost_usd"] is not None]
        out.append({"workflow": workflow, "runs": len(rows), **{f"mean_{k}": round(v, 6) for k, v in mean.items()},
                    "min_cost": min(costs) if costs else None, "max_cost": max(costs) if costs else None})
    return out


def render(summary: list[dict], records: list[dict], meta: dict) -> str:
    lines = [f"# Newer AI features: measured cost per run, {meta['when'][:10]}", "",
             f"- **When:** {meta['when']}", f"- **Mode:** {meta['mode']}",
             f"- **Model:** {meta['model']}" + (f" (served as `{meta['served_model']}`)" if meta["served_model"] else ""),
             f"- **Repetitions:** {meta['reps']} per workflow, each on a new sample account in a throwaway "
             "database",
             "- **How to repeat:** `python -m scripts.measure_new_features`", ""]
    if meta["mode"].startswith("OFFLINE"):
        lines += ["> **OFFLINE run: scripted model and made-up token counts. Nothing here is a measurement.**", ""]
    lines += ["| Workflow | Runs | Model calls | Input tokens | of which cached | written to cache | Output tokens | "
              "of which reasoning | Time | Cost per run (min to max) |", "|---|---|---|---|---|---|---|---|---|---|"]
    for s in summary:
        if not s["runs"]:
            lines.append(f"| {s['workflow']} | 0 | | | | | | | | not measured |")
            continue
        lines.append(f"| {s['workflow']} | {s['runs']} | {s['mean_model_calls']:.1f} | {s['mean_input_tokens']:,.0f} | "
                     f"{s['mean_cached_tokens']:,.0f} | {s['mean_cache_write_tokens']:,.0f} | "
                     f"{s['mean_output_tokens']:,.0f} | {s['mean_reasoning_tokens']:,.0f} | "
                     f"{s['mean_elapsed_ms'] / 1000:.1f} s | ${s['mean_cost_usd']:.5f} (${s['min_cost']:.5f} to "
                     f"${s['max_cost']:.5f}) |")
    mock = [r for r in records if r["mode"] != "live"]
    lines += ["", f"Calls that fell back to practice mode (not measured): {len(mock)}.",
              "Each figure is the provider's own usage report; the cost is an estimate at the rates in "
              "`data/pricing.json`.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--reps", type=int, default=3)
    parser.add_argument("--out", default=str(OUT_DIR))
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    from grantbridge import llm
    from grantbridge.db import init_db

    when = datetime.now(timezone.utc)
    root, level = logging.getLogger(), logging.getLogger().level
    root.setLevel(logging.WARNING)
    records = []
    try:
        for rep in range(1, args.reps + 1):
            with tempfile.TemporaryDirectory(prefix="grantbridge-measure-new-") as tmp:
                with _temp_env(GRANTBRIDGE_DB=str(Path(tmp) / "measure.db"), GRANTBRIDGE_DAILY_TOKEN_BUDGET="5000000",
                               GRANTBRIDGE_AI_REQUESTS_PER_MINUTE="1000"):
                    init_db()
                    if args.offline:
                        client, model = ScriptedModel(), "gpt-6-luna"
                    else:
                        client, model = llm.get_client(fresh_answers=True)
                    records += one_repetition(client, model, rep)
    finally:
        root.setLevel(level)
    summary = summarize(records)
    served = next((r["served_model"] for r in records if r["served_model"]), "")
    meta = {"when": when.strftime("%Y-%m-%d %H:%M UTC"), "model": "gpt-6-luna", "served_model": served,
            "reps": args.reps, "mode": ("OFFLINE: scripted model, made-up token counts (not a measurement)"
                                        if args.offline else "live: real model calls, fresh answers only")}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = ("offline-" if args.offline else "") + when.strftime("%Y-%m-%d")
    (out / f"new-features-costs-{stem}.json").write_text(json.dumps({"meta": meta, "summary": summary,
                                                                     "records": records}, indent=1), encoding="utf-8")
    report = render(summary, records, meta)
    (out / f"new-features-costs-{stem}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
