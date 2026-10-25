"""Time and cost the solicitation import on three real federal notices, and on the sample used in the demo.

Usage (from the repo folder):
    python -m scripts.measure_outline_import              # live, one reading of each notice
    python -m scripts.measure_outline_import --reps 2

Each reading uses a new sample account in a throwaway database, so nothing is served from a saved copy. The
notices are the committed ones in data/fixtures/real_notices/ plus the demo's own sample notice. What is
recorded per reading: the characters read, the wall-clock seconds, the provider's token counts, the estimated
cost, and how many items survived verification -- never a number the model asserted about itself.

Writes <out>/outline-import-cost-<date>.json and .md (default out: docs/evidence).
"""
from __future__ import annotations

import argparse
import json
import secrets as pysecrets
import statistics
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from scripts.measure_costs import _temp_env

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "docs" / "evidence"
NOTICES = REPO / "data" / "fixtures" / "real_notices"

SOURCES = [
    ("FWS Highlands F25AS00379", "real", NOTICES / "fws-highlands.txt"),
    ("FHWA PPPP-26-001", "real", NOTICES / "fhwa-pppp.txt"),
    ("NOAA-OAR-CPO-2026-33326", "real", NOTICES / "noaa-esssp.txt"),
]
GROUPS = ("sections", "criteria", "components", "registrations", "format_rules")


def one_reading(label: str, text: str, progress) -> dict:
    from grantbridge import auth, documents as docs, outline, trace

    with tempfile.TemporaryDirectory() as tmp:
        with _temp_env(GRANTBRIDGE_DB=str(Path(tmp) / "measure.db")):
            from grantbridge.db import init_db
            init_db()
            tag = pysecrets.token_hex(3)
            user = auth.sign_up(f"outline-{tag}@example.org", f"measure pass {tag}", "Measurement Org")
            document = docs.Document(name=f"{label}.txt", text=text, kind="txt", pages=None,
                                     truncated=False)

            progress(f"reading {label} ({len(text):,} characters)")
            started = time.perf_counter()
            outcome = outline.extract(user.id, [document])
            elapsed = time.perf_counter() - started

            usage = next((r for r in trace.list_runs(user.id, limit=5)
                          if r.get("kind") == "proposal_outline"), {})
            payload = outcome.data or {}
            kept = {g: len(payload.get(g, []) or []) for g in GROUPS}
            return {
                "label": label, "chars": len(text), "mode": outcome.mode,
                "notice": outcome.notice or "", "seconds": round(elapsed, 1),
                "items": sum(kept.values()), "kept": kept, "usage": usage,
            }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument("--out", default=str(OUT_DIR))
    args = parser.parse_args(argv)

    def progress(message: str) -> None:
        print(f"  {message}", flush=True)

    rows = []
    for rep in range(1, args.reps + 1):
        for label, kind, path in SOURCES:
            text = path.read_text(encoding="utf-8", errors="replace")
            row = one_reading(label, text, progress)
            row["kind"] = kind
            row["rep"] = rep
            rows.append(row)
            print(f"    {row['seconds']} s, {row['items']} items, mode={row['mode']}", flush=True)

    live = [r for r in rows if r["mode"] == "live"]
    if not live:
        print("no live reading completed; nothing measured", file=sys.stderr)
        return 1

    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = Path(args.out)
    payload = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "reps": args.reps, "readings": rows}
    (out / f"outline-import-cost-{date}.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")

    def cost_of(row) -> float | None:
        c = (row.get("usage") or {}).get("cost_usd")
        return float(c) if c is not None else None

    costs = [c for c in (cost_of(r) for r in live) if c is not None]
    lines = [
        f"# What it costs to read a solicitation into an outline, {date}",
        "",
        "Each reading below used a new sample account in a throwaway database, so none of it came from a saved",
        "copy. Times are wall clock around the import; token counts and costs are the provider's, read from the",
        "run log. Regenerate with `python -m scripts.measure_outline_import`.",
        "",
        "| Notice | Characters | Seconds | Items kept | Input tokens | Output tokens | Estimated cost |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in live:
        u = r.get("usage") or {}
        cost = cost_of(r)
        lines.append(
            f"| {r['label']} | {r['chars']:,} | {r['seconds']} | {r['items']} | "
            f"{u.get('input_tokens', 0):,} | {u.get('output_tokens', 0):,} | "
            + (f"${cost:.4f} |" if cost is not None else "— |"))
    if costs:
        lines += ["", f"**Median cost of one reading: ${statistics.median(costs):.4f}.** "
                      f"Median time: {statistics.median([r['seconds'] for r in live]):.1f} s."]
    lines += [
        "",
        "## Limits",
        "",
        f"- {len(live)} reading(s), on one machine, on one day. Times include the network, so they vary.",
        "- The item counts are what survived verification, not what the model proposed.",
        "",
    ]
    (out / f"outline-import-cost-{date}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out / f'outline-import-cost-{date}.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
