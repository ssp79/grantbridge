"""Evaluate Can We Afford to Win?'s term extraction on sample notices with known answers, and measure its cost.

Usage (from the repo folder):
    python -m scripts.measure_award_feasibility            # live: 5 notices x 3 repetitions, plus 3 explanations
    python -m scripts.measure_award_feasibility --reps 1
    python -m scripts.measure_award_feasibility --offline  # practice patterns only, no AI calls

The notices and their expected terms are in data/fixtures/award_terms_eval.json, written before any model saw them.
Each notice is read through an application with no grant listing, so only the notice's own words can produce terms.
Every field is scored against the expected value: correct, missed (expected but unknown), wrong (a different
value), invented (a value where the text states none), or correctly unknown. The fixed text patterns (practice mode)
are scored the same way, as a baseline. Every repetition uses a new sample account in a throwaway database, and
live calls ask Portkey for fresh answers, so no measured call is a saved copy.
Writes <out>/award-feasibility-eval-<date>.json and .md (default out: docs/evidence).
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from scripts.measure_costs import _temp_env

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "docs" / "evidence"
EVAL = json.loads((REPO / "data" / "fixtures" / "award_terms_eval.json").read_text(encoding="utf-8"))
OUTCOMES = ("correct", "missed", "wrong", "invented", "correct_unknown")


def score(terms: dict, expected: dict) -> dict:
    """One outcome per expected field."""
    out = {}
    for field, want in expected.items():
        got = (terms.get(field) or {}).get("value")
        if want is None:
            out[field] = "correct_unknown" if got is None else "invented"
        elif got is None:
            out[field] = "missed"
        else:
            options = want if isinstance(want, list) else [want]
            same = any((isinstance(o, (int, float)) and isinstance(got, (int, float)) and abs(float(o) - float(got))
                        < 1e-6) or o == got for o in options)
            out[field] = "correct" if same else "wrong"
    return out


def tally(scores: list[dict]) -> dict:
    counts = dict.fromkeys(OUTCOMES, 0)
    for s in scores:
        for outcome in s.values():
            counts[outcome] += 1
    return counts


def run_rep(client, model: str, rep: int, live: bool) -> list[dict]:
    from grantbridge import auth, demo, repo
    from grantbridge import award_feasibility as af

    user = auth.sign_up(f"eval-{rep}@example.org", "correct horse battery staple", f"Eval {rep}")
    demo.load_demo_data(user.id)
    rows = []
    for notice in EVAL["notices"]:
        app_id = repo.create_application(user.id, f"Evaluation {notice['id']}")  # no grant listing
        out = af.find_terms(user.id, application_id=app_id, notice=notice["text"], client=client if live else None,
                            model=model if live else None, want_mock=not live, fetch=False)
        usage = out.data.get("usage") or {}
        rows.append({"notice": notice["id"], "rep": rep, "mode": out.mode, "scores": score(out.data["terms"],
                                                                                           notice["expected"]),
                     "kept": len(out.data["conditions"]), "stats": out.data.get("stats", {}),
                     "injection_signals": out.data.get("injection_signals", 0),
                     "usage": {k: usage.get(k) for k in ("model_calls", "input_tokens", "cached_tokens",
                                                         "cache_write_tokens", "output_tokens", "reasoning_tokens",
                                                         "cost_usd", "elapsed_ms")},
                     "served_model": usage.get("served_model", "")})
    return rows


def run_explanation(client, model: str, rep: int) -> dict:
    """The explanation step on the sample demonstration grant, with the sample numbers."""
    from grantbridge import auth, demo, pursuit
    from grantbridge import award_feasibility as af

    user = auth.sign_up(f"explain-{rep}@example.org", "correct horse battery staple", f"Explain {rep}")
    demo.load_demo_data(user.id)
    data = af.demo_data()
    af.find_terms(user.id, grant_id=data["grant_id"], notice=data["notice"], want_mock=True)
    af.save_inputs(user.id, f"grant:{data['grant_id']}", {**data["inputs"], **data["finances"]})
    target = pursuit.load_target(user.id, grant_id=data["grant_id"], fetch=False)
    out = af.explain(user.id, target, client=client, model=model)
    usage = out.data.get("usage") or {}
    from grantbridge import trace
    steps = trace.run_steps(user.id, out.run_id)
    check = next((s for s in steps if s["tool"] == "check_explanation"), {})
    return {"rep": rep, "mode": out.mode, "words": len(out.data["explanation"].split()),
            "figures_replaced": (check.get("summary") or {}).get("figures_replaced"),
            "tradeoffs": len(out.data["tradeoffs"]), "questions": len(out.data["questions_for_funder"]),
            "usage": {k: usage.get(k) for k in ("model_calls", "input_tokens", "cached_tokens", "output_tokens",
                                                "reasoning_tokens", "cost_usd", "elapsed_ms")}}


def render(meta: dict, live_rows: list[dict], pattern_rows: list[dict], explanations: list[dict]) -> str:
    lines = [f"# Can We Afford to Win?: term-extraction evaluation, {meta['when'][:10]}", "",
             f"- **When:** {meta['when']}", f"- **Mode:** {meta['mode']}",
             ("- **Model:** gpt-6-luna" + (f" (served as `{meta['served_model']}`)" if meta["served_model"] else "")
              if live_rows else "- **Model:** none (no AI calls)"),
             f"- **Notices:** {len(EVAL['notices'])} sample notices with expected terms written before any run "
             "(`data/fixtures/award_terms_eval.json`), {reps} repetition(s) each".format(reps=meta["reps"]),
             "- **How to repeat:** `python -m scripts.measure_award_feasibility`", "",
             "Each expected field is scored: **correct**, **missed** (stated but returned as unknown), **wrong** (a "
             "different value), **invented** (a value where the text states none), or **correctly unknown**. "
             "These are sample notices written for this test, so the results show how the extraction behaves on "
             "clear, ambiguous, silent, and adversarial text, not how often it is right on real funders' notices.", ""]
    for name, rows in (("AI (gpt-6-luna), checked by code", live_rows), ("Fixed text patterns (practice mode, no AI)",
                                                                           pattern_rows)):
        if not rows:
            continue
        t = tally([r["scores"] for r in rows])
        total = sum(t.values())
        lines += [f"## {name}", ""]
        if rows is pattern_rows:
            lines += ["These patterns were written by the same person who wrote the notices, with the notices in view. "
                      "Their score is a baseline for comparison, not independent evidence that they work on other "
                      "text.", ""]
        lines += ["| Outcome | Fields | Share |", "|---|---|---|"]
        lines += [f"| {o.replace('_', ' ').capitalize()} | {t[o]} | {100 * t[o] / total:.0f}% |" for o in OUTCOMES]
        lines += ["", "| Notice | Correct | Missed | Wrong | Invented | Correctly unknown |", "|---|---|---|---|---|---|"]
        for notice in EVAL["notices"]:
            nt = tally([r["scores"] for r in rows if r["notice"] == notice["id"]])
            lines.append(f"| {notice['id']} | " + " | ".join(str(nt[o]) for o in OUTCOMES) + " |")
        problems = sorted({(r["notice"], f, o) for r in rows for f, o in r["scores"].items()
                           if o in ("missed", "wrong", "invented")})
        if problems:
            lines += ["", "Fields not right in at least one repetition: " + "; ".join(
                f"{n} `{f}` ({o})" for n, f, o in problems) + "."]
        lines.append("")
    if live_rows:
        drops = {k: sum((r["stats"] or {}).get(k, 0) for r in live_rows)
                 for k in ("quotes_dropped", "numbers_dropped", "injected_dropped")}
        lines += ["## What code removed from the AI's answers", "",
                  f"- Conditions whose quote was not in the notice: {drops['quotes_dropped']}",
                  f"- Numbers not found in their own quote: {drops['numbers_dropped']}",
                  f"- Conditions quoted from a sentence aimed at an AI: {drops['injected_dropped']}", ""]
        costs = [r["usage"]["cost_usd"] for r in live_rows if r["usage"]["cost_usd"] is not None]
        tokens_in = [r["usage"]["input_tokens"] or 0 for r in live_rows]
        tokens_out = [r["usage"]["output_tokens"] or 0 for r in live_rows]
        ms = [r["usage"]["elapsed_ms"] or 0 for r in live_rows]
        lines += ["## Cost per term extraction (live)", "",
                  "| Runs | Input tokens | Output tokens | Time | Cost per run (min to max) |", "|---|---|---|---|---|",
                  f"| {len(live_rows)} | {statistics.mean(tokens_in):,.0f} | {statistics.mean(tokens_out):,.0f} | "
                  f"{statistics.mean(ms) / 1000:.1f} s | ${statistics.mean(costs):.5f} (${min(costs):.5f} to "
                  f"${max(costs):.5f}) |", ""]
    if explanations:
        costs = [e["usage"]["cost_usd"] for e in explanations if e["usage"]["cost_usd"] is not None]
        lines += ["## The explanation step (live, on the sample demonstration)", "",
                  "| Runs | Words | Figures replaced by code | Output tokens | Time | Cost per run |",
                  "|---|---|---|---|---|---|",
                  f"| {len(explanations)} | {statistics.mean(e['words'] for e in explanations):.0f} | "
                  f"{sum(e['figures_replaced'] or 0 for e in explanations)} | "
                  f"{statistics.mean(e['usage']['output_tokens'] or 0 for e in explanations):,.0f} | "
                  f"{statistics.mean(e['usage']['elapsed_ms'] or 0 for e in explanations) / 1000:.1f} s | "
                  + (f"${statistics.mean(costs):.5f} |" if costs else "not reported |"), ""]
    fallbacks = sum(1 for r in live_rows if r["mode"] != "live") + sum(1 for e in explanations if e["mode"] != "live")
    lines += [f"Calls that fell back to practice mode (not counted as AI results): {fallbacks}.",
              "Token counts are the provider's own usage report; costs are estimates at the rates in "
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
    live_rows, pattern_rows, explanations = [], [], []
    try:
        with tempfile.TemporaryDirectory(prefix="grantbridge-eval-patterns-") as tmp:
            with _temp_env(GRANTBRIDGE_DB=str(Path(tmp) / "eval.db")):
                init_db()
                pattern_rows = run_rep(None, "", 0, live=False)  # deterministic: one run is enough
        if not args.offline:
            for rep in range(1, args.reps + 1):
                with tempfile.TemporaryDirectory(prefix="grantbridge-eval-") as tmp:
                    with _temp_env(GRANTBRIDGE_DB=str(Path(tmp) / "eval.db"),
                                   GRANTBRIDGE_DAILY_TOKEN_BUDGET="5000000", GRANTBRIDGE_AI_REQUESTS_PER_MINUTE="1000"):
                        init_db()
                        client, model = llm.get_client(fresh_answers=True)
                        live_rows += run_rep(client, model, rep, live=True)
                        explanations.append(run_explanation(client, model, rep))
    finally:
        root.setLevel(level)
    served = next((r["served_model"] for r in live_rows if r["served_model"]), "")
    meta = {"when": when.strftime("%Y-%m-%d %H:%M UTC"), "served_model": served, "reps": args.reps,
            "mode": "OFFLINE: practice patterns only, no AI calls" if args.offline
            else "live: real model calls, fresh answers only; practice patterns as a baseline"}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = ("offline-" if args.offline else "") + when.strftime("%Y-%m-%d")
    record = {"meta": meta, "live": live_rows, "patterns": pattern_rows, "explanations": explanations,
              "totals": {"live": tally([r["scores"] for r in live_rows]),
                         "patterns": tally([r["scores"] for r in pattern_rows])}}
    (out / f"award-feasibility-eval-{stem}.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    report = render(meta, live_rows, pattern_rows, explanations)
    (out / f"award-feasibility-eval-{stem}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
