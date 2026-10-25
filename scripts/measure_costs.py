"""Measure what GrantBridge's AI workflows really cost, project the monthly cost, and test a cost saving.

Usage (from the repo folder):
    python -m scripts.measure_costs                          # live: every setting, 2 repetitions
    python -m scripts.measure_costs --reps 1 --settings baseline
    python -m scripts.measure_costs --offline                # no AI calls: checks the harness itself

Three representative workflows run through GrantBridge's own code (the same functions the pages call):

    Explain fit        one model call, on three sample grants (passes every check, fails a soft check,
                       fails the state check)
    Advisor answer     the agent loop with real tools, on the advisor page's example questions
    Draft one answer   find missing facts, draft, and review one application question (three AI runs)

Every repetition of every setting uses a new sample account (the Harbor Lantern demo data) in a throwaway
database, so each starts with a cold prompt cache (prompt_cache_key is per account). Live calls send Portkey's
documented x-portkey-cache-force-refresh header, so no measured call is a saved copy of an earlier answer.

Token counts are the provider's own numbers from each response. A call without usage is reported as such and
gets no cost, never an invented one. Costs use data/pricing.json. Quality is scored with the same deterministic
checks for every setting. --offline uses a scripted model with made-up token counts: it tests this script and
its report, and its numbers are never measurements.

Writes <out>/measurements-<date>.json (every run) and <out>/cost-report-<date>.md (default out: docs/tokenomics).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import secrets as pysecrets
import statistics
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "docs" / "tokenomics"

# Each setting is a set of environment overrides applied while its runs execute.
SETTINGS = {
    "baseline": {"GRANTBRIDGE_REASONING_EFFORT": "default"},
    "low reasoning": {"GRANTBRIDGE_REASONING_EFFORT": "low"},
}
SETTING_NOTES = {
    "baseline": "as first built: no reasoning setting is sent, so gpt-6-luna's default effort (medium) applies",
    "low reasoning": "the cost saver: every model call asks for reasoning effort \"low\"",
}

EXPLAIN_GRANTS = ["sample-01", "sample-08", "sample-07"]
ADVISOR_CASES = [  # (message, the tool a good answer must call, whether it is about sample grants)
    ("Which sample grants fit us best?", "search_grants", True),
    ("What does the Connecticut After-School Learning Grant require?", "inspect_grant_requirements", True),
    ("How far along are my applications?", "get_application_state", False),
]
DRAFT_SECTION_INDEX = 1  # "Describe the after-school program ... including its schedule and staffing. (400 words)"
DRAFT_REQUIREMENTS = ["Explain how student progress is measured.", "Describe how families take part."]
DRAFT_FACTS = [  # sample answers a user might type; every setting gets exactly these
    ("Who leads this work, and what training do tutors get?",
     "Our program director, a former Bridgeport teacher, leads the program with two site coordinators. Every "
     "volunteer tutor completes 8 hours of training in reading and math strategies before starting, plus "
     "monthly coaching."),
    ("How do families take part?",
     "Families meet their child's tutor at four Family Learning Nights a year and take home learning kits in "
     "English, Spanish, and Portuguese."),
]

# Assumed use per active nonprofit account per month (reasoning in docs/TOKENOMICS.md).
MONTHLY_USE = {"Explain fit": 20, "Advisor answer": 40, "Draft one answer": 10}
SCALES = (1, 100, 10_000)
WORKFLOWS = ("Explain fit", "Advisor answer", "Draft one answer")
SUM_FIELDS = ("model_calls", "tool_calls", "input_tokens", "cached_tokens", "cache_write_tokens", "output_tokens",
              "reasoning_tokens", "elapsed_ms", "model_ms", "unreported_calls", "gateway_hits")


@contextmanager
def _temp_env(**values):
    old = {k: os.environ.get(k) for k in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ---------------------------------------------------------------- offline stand-in (tests the harness only)

class ScriptedModel:
    """Fixed replies and fixed, made-up token counts. Reports from it say so and are never measurements."""

    USAGE = SimpleNamespace(input_tokens=1000, output_tokens=300,
                            input_tokens_details=SimpleNamespace(cached_tokens=0, cache_write_tokens=1000),
                            output_tokens_details=SimpleNamespace(reasoning_tokens=200))

    def __init__(self):
        self.responses = self
        self.requests: list[dict] = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        if kwargs.get("tools"):
            return self._advisor(kwargs["input"])
        name = kwargs["text"]["format"]["name"]
        body = {
            "fact_plan": {"known": [{"fact": "Mission: from the profile", "source": "profile"}],
                          "questions": [{"ask": "Which partner schools take part?", "why": "Funders ask."}]},
            "section_draft": {"draft": "We run free small-group tutoring twice a week at two partner schools. "
                                       "[NEEDS: number of tutors per site]", "facts_used": [], "placeholders": []},
            "draft_review": {"requirements": [], "unsupported_claims": [], "missing_evidence": [],
                             "summary": "Scripted review."},
        }[name]
        return SimpleNamespace(output_text=json.dumps(body), usage=self.USAGE, status="completed")

    def _advisor(self, items):
        message = next(i["content"] for i in reversed(items) if isinstance(i, dict) and i.get("role") == "user")
        if not any(isinstance(i, dict) and i.get("type") == "function_call_output" for i in items):
            name, args = (("get_application_state", {"grant_id": None}) if "applications" in message else
                          ("inspect_grant_requirements", {"grant_id": "sample-01"}) if "require" in message else
                          ("search_grants", {"source": "sample", "keyword": None, "focus_areas": None}))
            call = SimpleNamespace(type="function_call", id="fc_1", call_id="c1", name=name, arguments=json.dumps(args))
            return SimpleNamespace(output=[call], output_text="", usage=self.USAGE)
        body = {"reply": "Scripted answer about the Connecticut After-School Learning Grant (sample grant).",
                "known_facts": [], "assumptions": ["Scripted."], "clarifying_question": None, "grant_ids_cited": []}
        return SimpleNamespace(output=[SimpleNamespace(type="message")], output_text=json.dumps(body), usage=self.USAGE)

    def parse(self, **kwargs):
        from grantbridge import fit_explainer as fx

        exp = fx.FitExplanation(verdict="possible fit", confidence="medium",
                                summary="Scripted: it is a sample for the demo, not a real opportunity.",
                                reasons=[fx.Reason(point="Serves Connecticut students.", based_on="profile")],
                                uncertainties=["Scripted."], verify_next=["Read the notice."])
        return SimpleNamespace(output_parsed=exp, usage=self.USAGE)


# ---------------------------------------------------------------- the three workflows and their quality checks

def _run_row(user_id: int, run_id: int, step: str) -> dict:
    from grantbridge import trace

    s = trace.run_summary(user_id, run_id)
    keep = ("model", "served_model", "gateway_cache", "cost_usd", "price_ref", "unpriced_calls") + SUM_FIELDS
    return {"step": step, **{k: s[k] for k in keep}}


def explain_fit_case(user_id: int, org: dict, grant_id: str, client, model: str):
    from grantbridge import fit_explainer as fx, grant_search as gs, repo

    result = gs.sample_result(repo.get_grant(grant_id), gs.filters_from_profile(org))
    fails = [c for c in result.checks if c.outcome == gs.FAILS]
    label = (f"{grant_id}: fails the {fails[0].name.lower()} check (required)" if any(c.hard for c in fails) else
             f"{grant_id}: fails the {fails[0].name.lower()} check" if fails else
             f"{grant_id}: passes every automatic check")
    out = fx.run_explain(user_id, org, result, client=client, model=model)
    e, stats = out.explanation, out.guard_stats
    if any(c.hard for c in fails):
        verdict_ok = e is not None and e.verdict == "unlikely fit" and not stats.get("guard_verdict_changed")
    elif fails:
        verdict_ok = e is not None and e.verdict != "likely fit"
    else:
        verdict_ok = e is not None and e.verdict in ("likely fit", "possible fit")
    text = " ".join([e.summary, *[r.point for r in e.reasons], *e.uncertainties]).lower() if e else ""
    checks = [
        ("Returned a readable explanation", e is not None),
        ("Verdict agrees with the automatic checks, with no correction needed", verdict_ok),
        ("No sentence had to be removed (open-status or eligibility claims)",
         e is not None and not stats.get("guard_removed_sentences") and not stats.get("guard_eligibility_claims")),
        ("Confidence fits the unchecked items (no cap needed)", e is not None and not stats.get("guard_confidence_capped")),
        ("Says the grant is a sample, not a real opportunity", "sample" in text),
        ("Gives at least two reasons", e is not None and len(e.reasons) >= 2),
        ("Lists something to verify next", e is not None and len(e.verify_next) >= 1),
    ]
    shown = f"{e.verdict} (confidence {e.confidence}). {e.summary}" if e else (out.error or "")
    return label, [_run_row(user_id, out.run_id, "explain fit")], checks, shown


def advisor_case(user_id: int, message: str, tool: str, about_samples: bool, client, model: str):
    from grantbridge import advisor, grant_search as gs, repo, trace

    repo.clear_messages(user_id)  # each question stands alone, so every setting answers exactly the same input
    turn = advisor.run_turn(user_id, message, client=client, model=model)
    steps = trace.run_steps(user_id, turn.run_id)
    used = {s["tool"] for s in steps if s["kind"] == "tool"}
    guard = next((s["summary"] for s in steps if s["tool"] == "check_reply"), {})
    reply = turn.reply.reply
    if tool == "search_grants":  # one of the three best-ranked grants, ranked exactly as the search tool does
        f = gs.filters_from_profile(repo.get_organization(user_id), keyword="", hide_research=True)
        expected = [r.title.lower() for r in gs.search_samples(f)[0][:3]]
        right_record = tool in used
    elif tool == "inspect_grant_requirements":  # the grant asked about is sample-01
        expected = ["after-school learning"]
        right_record = any(s["tool"] == tool and s["args"].get("grant_id") == "sample-01" for s in steps)
    else:  # the demo application is for sample-01
        expected = ["after-school learning"]
        right_record = tool in used
    checks = [
        ("Answered by the AI (no fallback, no limit hit)",
         turn.mode == "live" and not turn.notice and not any(s["tool"] == "stop" for s in steps)),
        ("Looked up the right record (the tool the question needs; sample-01 when asked about it)", right_record),
        ("Every figure matches a record it retrieved", not guard.get("guard_unverified_figures")),
        ("Cites only grants it looked up", not guard.get("guard_uncited_grants")),
        ("No sentence had to be removed (open-status or eligibility claims)",
         not guard.get("guard_removed_sentences") and not guard.get("guard_eligibility_claims")),
        ("Names the grant it is about (a top-3 match, or the one asked about)",
         any(e in reply.lower() for e in expected)),
        ("Stays within the 180 words its instructions allow", len(reply.split()) <= 180),
    ]
    if about_samples:
        checks.append(("Says the grants are samples (sample demo data)", "sample" in reply.lower()))
    return message, [_run_row(user_id, turn.run_id, "advisor answer")], checks, reply


def draft_case(user_id: int, app_id: int, client, model: str):
    from grantbridge import drafting, repo

    section = repo.list_sections(user_id, app_id)[DRAFT_SECTION_INDEX]
    plan = drafting.plan_facts(user_id, section.id, client=client, model=model)
    # The AI's own fact questions differ from run to run. Drop them and give every setting the same two answered
    # facts, so the draft and review steps see the same input.
    for f in repo.list_section_facts(user_id, section.id):
        if f["status"] == "pending":
            repo.delete_section_fact(user_id, f["id"])
    for prompt, answer in DRAFT_FACTS:
        repo.add_section_fact(user_id, section.id, prompt, answer=answer, status="answered")
    draft = drafting.draft_section(user_id, section.id, client=client, model=model)
    drafting.use_draft(user_id, section.id)
    review = drafting.review_answer(user_id, section.id, client=client, model=model)
    flags, reqs = draft.data["flags"], review.data["requirements"]
    checks = [
        ("All three steps answered by the AI (no fallback)", all(o.mode == "live" for o in (plan, draft, review))),
        ("Fact finder asked 1 to 4 questions", 1 <= len(plan.data["added"]) <= 4),
        ("Fact finder listed facts the profile already has", len(plan.data["known"]) >= 1),
        ("Draft stays within the word limit", not flags["over_limit"]),
        ("Draft invents no figures or names (nothing marked [VERIFY])", not flags["flagged"]),
        ("Draft uses at least 40% of the word limit", flags["word_count"] >= 0.4 * (flags["word_limit"] or 0)),
        ("Review covers every requirement", all(r["status"] != "not reviewed" for r in reqs)),
        ("Every review quote is really in the answer", all(r["status"] != "unverified" for r in reqs)),
        ("Review writes a summary", bool(review.data["summary"].strip())),
    ]
    runs = [_run_row(user_id, plan.run_id, "find facts"), _run_row(user_id, draft.run_id, "draft"),
            _run_row(user_id, review.run_id, "review")]
    shown = (f"Draft ({flags['word_count']} of {flags['word_limit']} words): {draft.data['text']}\n"
             f"Review: {review.data['summary']}")
    return section.question, runs, checks, shown


def _record(workflow: str, case: str, setting: str, rep: int, runs: list[dict], checks, shown: str) -> dict:
    totals = {k: sum(r[k] for r in runs) for k in SUM_FIELDS}
    totals["cost_usd"] = None if any(r["cost_usd"] is None for r in runs) else round(sum(r["cost_usd"] for r in runs), 10)
    return {"workflow": workflow, "case": case, "setting": setting, "rep": rep, "runs": runs, "totals": totals,
            "checks": [{"check": name, "passed": bool(ok)} for name, ok in checks], "shown": shown}


def measure(client, model: str, settings: dict[str, dict], reps: int, progress=print) -> list[dict]:
    """Run every case for every setting and repetition, each repetition of each setting in a new account."""
    from grantbridge import auth, demo, repo

    records = []
    for rep in range(1, reps + 1):
        for setting, env in settings.items():
            with _temp_env(**env):
                tag = pysecrets.token_hex(3)
                user = auth.sign_up(f"measure-{tag}@example.org", f"measure pass {tag}", "Measurement Org")
                app_id = demo.load_demo_data(user.id)
                repo.add_requirements(user.id, app_id, DRAFT_REQUIREMENTS)
                org = repo.get_organization(user.id)
                for grant_id in EXPLAIN_GRANTS:
                    progress(f"rep {rep} · {setting} · Explain fit · {grant_id}")
                    records.append(_record("Explain fit", *_split(explain_fit_case(user.id, org, grant_id, client, model),
                                                                   setting, rep)))
                for message, tool, about_samples in ADVISOR_CASES:
                    progress(f"rep {rep} · {setting} · Advisor answer · {message}")
                    records.append(_record("Advisor answer", *_split(
                        advisor_case(user.id, message, tool, about_samples, client, model), setting, rep)))
                progress(f"rep {rep} · {setting} · Draft one answer")
                records.append(_record("Draft one answer", *_split(draft_case(user.id, app_id, client, model),
                                                                    setting, rep)))
    return records


def _split(case_result, setting, rep):
    case, runs, checks, shown = case_result
    return case, setting, rep, runs, checks, shown


# ---------------------------------------------------------------- summary and report

def summarize(records: list[dict]) -> dict:
    """Per (workflow, setting): means over measured cases, cost range, and quality checks passed."""
    out: dict = {}
    for wf in WORKFLOWS:
        for setting in dict.fromkeys(r["setting"] for r in records):
            group = [r for r in records if r["workflow"] == wf and r["setting"] == setting]
            if not group:
                continue
            priced = [r["totals"]["cost_usd"] for r in group if r["totals"]["cost_usd"] is not None]
            checks = [c for r in group for c in r["checks"]]
            out[(wf, setting)] = {
                "cases": len(group),
                "ai_runs": sum(len(r["runs"]) for r in group),
                **{k: statistics.mean(r["totals"][k] for r in group) for k in SUM_FIELDS},
                "cost_mean": statistics.mean(priced) if priced else None,
                "cost_min": min(priced) if priced else None,
                "cost_max": max(priced) if priced else None,
                "unpriced_cases": len(group) - len(priced),
                "checks_passed": sum(c["passed"] for c in checks),
                "checks_total": len(checks),
            }
    return out


def monthly(summary: dict, setting: str) -> float | None:
    costs = [summary.get((wf, setting), {}).get("cost_mean") for wf in WORKFLOWS]
    if any(c is None for c in costs):
        return None
    return sum(c * MONTHLY_USE[wf] for c, wf in zip(costs, WORKFLOWS))


def monthly_tokens(summary: dict, setting: str) -> float:
    """Input plus output tokens per user per month: what the daily token budgets count."""
    return sum((summary[(wf, setting)]["input_tokens"] + summary[(wf, setting)]["output_tokens"]) * MONTHLY_USE[wf]
               for wf in WORKFLOWS if (wf, setting) in summary)


def _usd(x) -> str:
    if x is None:
        return "not estimated"
    if x == 0:
        return "$0"
    return f"${x:.5f}" if x < 0.01 else f"${x:.4f}" if x < 1 else f"${x:,.2f}"


def _pct(new, old) -> str:
    if not old or new is None:
        return "—"
    return f"{(new - old) / old * 100:+.0f}%"


def render(records: list[dict], meta: dict) -> str:
    from grantbridge import pricing

    summary = summarize(records)
    settings = list(dict.fromkeys(r["setting"] for r in records))
    price = pricing.price_for(meta["model"])
    calls = [run for r in records for run in r["runs"]]
    reported = sum(run["model_calls"] - run["unreported_calls"] for run in calls)
    unreported = sum(run["unreported_calls"] for run in calls)
    hits = sum(run["gateway_hits"] for run in calls)
    t = price.tiers[0] if price else None
    lines = [
        "# GrantBridge cost measurement", "",
        f"- Run: {meta['when']} · {meta['mode']}",
        f"- Model: {meta['model']}" + (f" (served model {meta['served_model']})" if meta.get("served_model") else ""),
        f"- Settings: " + "; ".join(f"**{s}**: {SETTING_NOTES.get(s, '')}" for s in settings),
        f"- Repetitions: {meta['reps']} per setting, each in a new sample account with a cold prompt cache",
        (f"- Prices (data/pricing.json): {price.source}, checked {price.checked}: ${t.input:.2f} per 1M input "
         f"tokens, ${t.cached_input:.2f} cached input, ${t.cache_write:.3f} cache writes, ${t.output:.2f} output. "
         f"Source: {price.source_url}" if price else "- Prices: no entry for this model, so no costs are estimated."),
        f"- Usage reported by the provider for {reported} of {reported + unreported} model calls"
        + (f"; {unreported} did not report usage and have no cost" if unreported else "")
        + (f"; {hits} were Portkey cache hits" if hits else "; none were Portkey cache hits") + ".",
        "",
        "## Cost per run (mean of the measured cases)", "",
        "| Workflow | Setting | Cases | AI runs | Model calls | Tool calls | Input tokens | of which cached "
        "| written to cache | Output tokens | of which reasoning | Time | Cost per run (min to max) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for (wf, s), g in summary.items():
        lines.append(
            f"| {wf} | {s} | {g['cases']} | {g['ai_runs'] / g['cases']:.0f} | {g['model_calls']:.1f} | "
            f"{g['tool_calls']:.1f} | {g['input_tokens']:,.0f} | {g['cached_tokens']:,.0f} | "
            f"{g['cache_write_tokens']:,.0f} | {g['output_tokens']:,.0f} | {g['reasoning_tokens']:,.0f} | "
            f"{g['elapsed_ms'] / 1000:.1f} s | {_usd(g['cost_mean'])} ({_usd(g['cost_min'])} to {_usd(g['cost_max'])}) |")
    lines += [
        "", "## Monthly cost", "",
        "Assumed use per active nonprofit account per month: "
        + ", ".join(f"{n} × {wf}" for wf, n in MONTHLY_USE.items()) + ". Model tokens only (no hosting).", "",
        "| Setting | Per user per month | 100 users | 10,000 users |", "|---|---|---|---|",
    ]
    for s in settings:
        m = monthly(summary, s)
        lines.append(f"| {s} | " + " | ".join(_usd(None if m is None else m * n) for n in SCALES) + " |")
    lines += ["", "| Setting | Tokens per user per month | Tokens per day at 10,000 users | Cost per 1M tokens, blended |",
              "|---|---|---|---|"]
    for s in settings:
        tokens, m = monthly_tokens(summary, s), monthly(summary, s)
        blended = None if m is None or not tokens else m / tokens * 1_000_000
        lines.append(f"| {s} | {tokens:,.0f} | {tokens * 10_000 / 30:,.0f} | {_usd(blended)} |")
    tokens, m = monthly_tokens(summary, settings[-1]), monthly(summary, settings[-1])
    if m is not None and tokens:
        cap = meta.get("daily_budget", 100_000)
        server = meta.get("server_daily_budget", 1_000_000)
        lines += ["", f"Limits at that usage ({settings[-1]}): the per-account budget of {cap:,} tokens a day caps one "
                  f"account at about {_usd(cap * 30 * m / tokens)} a month, whatever it does. The default server budget "
                  f"of {server:,} tokens a day covers about {server * 30 / tokens:,.0f} users at this usage, so "
                  f"10,000 users would need GRANTBRIDGE_SERVER_DAILY_TOKEN_BUDGET of about "
                  f"{tokens * 10_000 / 30 * 1.5:,.0f} (daily average plus 50% headroom)."]
    if len(settings) > 1:
        base, other = settings[0], settings[1]
        lines += ["", f"## {other} compared with {base} (same test cases)", "",
                  "| Workflow | Cost per run | Change | Output tokens | Input tokens | Time | Quality checks passed |",
                  "|---|---|---|---|---|---|---|"]
        for wf in WORKFLOWS:
            a, b = summary.get((wf, base)), summary.get((wf, other))
            if not a or not b:
                continue
            lines.append(
                f"| {wf} | {_usd(a['cost_mean'])} → {_usd(b['cost_mean'])} | {_pct(b['cost_mean'], a['cost_mean'])} | "
                f"{a['output_tokens']:,.0f} → {b['output_tokens']:,.0f} | {a['input_tokens']:,.0f} → "
                f"{b['input_tokens']:,.0f} | {a['elapsed_ms'] / 1000:.1f} s → {b['elapsed_ms'] / 1000:.1f} s | "
                f"{a['checks_passed']}/{a['checks_total']} → {b['checks_passed']}/{b['checks_total']} |")
        ma, mb = monthly(summary, base), monthly(summary, other)
        lines.append(f"| **Month, 10,000 users** | {_usd(None if ma is None else ma * 10_000)} → "
                     f"{_usd(None if mb is None else mb * 10_000)} | {_pct(mb, ma)} | | | | |")
    lines += ["", "## Quality checks (the same deterministic checks for every setting)", "",
              "| Workflow | Check | " + " | ".join(settings) + " |", "|---|---|" + "---|" * len(settings)]
    for wf in WORKFLOWS:
        names = list(dict.fromkeys(c["check"] for r in records if r["workflow"] == wf for c in r["checks"]))
        for name in names:
            cells = []
            for s in settings:
                results = [c["passed"] for r in records if r["workflow"] == wf and r["setting"] == s
                           for c in r["checks"] if c["check"] == name]
                cells.append(f"{sum(results)}/{len(results)}")
            lines.append(f"| {wf} | {name} | " + " | ".join(cells) + " |")
    lines += ["", "## Every measured run", "",
              "| Workflow | Case | Setting | Rep | Model calls | Tools | Input | Cached | Written | Output | Reasoning "
              "| Time | Cost | Portkey cache |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in records:
        for run in r["runs"]:
            tokens = (" | ".join(["not reported"] * 5) if run["unreported_calls"] else
                      f"{run['input_tokens']:,} | {run['cached_tokens']:,} | {run['cache_write_tokens']:,} | "
                      f"{run['output_tokens']:,} | {run['reasoning_tokens']:,}")
            case = r["case"] if len(r["runs"]) == 1 else f"{r['case'][:50]}… ({run['step']})"
            lines.append(f"| {r['workflow']} | {case} | {r['setting']} | {r['rep']} | {run['model_calls']} | "
                         f"{run['tool_calls']} | {tokens} | {run['elapsed_ms'] / 1000:.1f} s | {_usd(run['cost_usd'])} | "
                         f"{', '.join(run['gateway_cache']) or '—'} |")
    lines += ["", "## What the user saw (first repetition, sample demo data)", ""]
    for wf in WORKFLOWS:
        first = next((r for r in records if r["workflow"] == wf), None)
        if first is None:
            continue
        lines += [f"### {wf}: {first['case']}", ""]
        for s in settings:
            r = next((x for x in records if x["workflow"] == wf and x["case"] == first["case"] and x["setting"] == s), None)
            if r:
                excerpt = r["shown"].replace("\n", " ").replace("|", "/")
                lines += [f"**{s}:** {excerpt[:900]}{'…' if len(excerpt) > 900 else ''}", ""]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--offline", action="store_true", help="Scripted model with made-up counts (tests only)")
    parser.add_argument("--reps", type=int, default=2, help="Repetitions per setting (default 2)")
    parser.add_argument("--settings", nargs="+", choices=list(SETTINGS), default=list(SETTINGS))
    parser.add_argument("--out", default=str(OUT_DIR), help="Folder for the JSON and the report")
    parser.add_argument("--from-json", help="Rebuild the report from a saved measurements file (no AI calls)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # a Windows console cannot print every character in the report

    from grantbridge import llm
    from grantbridge.db import init_db

    if args.from_json:
        saved = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
        report = render(saved["records"], saved["meta"])
        target = Path(args.from_json).with_name(Path(args.from_json).name.replace("measurements-", "cost-report-")
                                                ).with_suffix(".md")
        target.write_text(report, encoding="utf-8")
        print(f"Rebuilt {target}")
        return 0

    when = datetime.now(timezone.utc)
    root, level = logging.getLogger(), logging.getLogger().level
    root.setLevel(logging.WARNING)  # the trace logs every step at INFO; the report has it all
    try:
        with tempfile.TemporaryDirectory(prefix="grantbridge-measure-") as tmp:
            with _temp_env(GRANTBRIDGE_DB=str(Path(tmp) / "measure.db"), GRANTBRIDGE_DAILY_TOKEN_BUDGET="5000000",
                           GRANTBRIDGE_SERVER_DAILY_TOKEN_BUDGET="50000000", GRANTBRIDGE_AI_REQUESTS_PER_MINUTE="1000"):
                init_db()
                if args.offline:
                    client, model = ScriptedModel(), "gpt-6-luna"
                    mode = "OFFLINE: scripted model, made-up token counts (not a measurement)"
                else:
                    client, model = llm.get_client(fresh_answers=True)
                    mode = "live: real model calls through the course Portkey gateway, fresh answers only"
                records = measure(client, model, {s: SETTINGS[s] for s in args.settings}, args.reps)
    finally:
        root.setLevel(level)
    served = next((run["served_model"] for r in records for run in r["runs"] if run["served_model"]), "")
    meta = {"when": when.strftime("%Y-%m-%d %H:%M UTC"), "mode": mode, "model": model, "served_model": served,
            "reps": args.reps, "settings": {s: SETTINGS[s] for s in args.settings}, "monthly_use": MONTHLY_USE,
            "daily_budget": llm.daily_budget(), "server_daily_budget": llm.server_daily_budget()}
    report = render(records, meta)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = ("offline-" if args.offline else "") + when.strftime("%Y-%m-%d")
    (out / f"measurements-{stem}.json").write_text(json.dumps({"meta": meta, "records": records}, indent=1),
                                                    encoding="utf-8")
    (out / f"cost-report-{stem}.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"Wrote {out / f'measurements-{stem}.json'} and {out / f'cost-report-{stem}.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
