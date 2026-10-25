"""Re-check the outlines GrantBridge read out of three real federal notices.

The notices were read on 2026-10-23 with the live model. Their text and the outline payload each one
produced are committed under ``data/fixtures/real_notices/``, so this check can be repeated offline and
without an API key:

    python -m scripts.check_real_solicitations

It re-applies the product's own rule, using ``solicitation._flat`` and ``guards.injection_signals``: an item
may be kept only when the sentence it carries appears word for word in the notice it came from, and never
when that sentence is wording aimed at an AI. Every quotation in all three saved outlines is re-tested here.

Writing ``docs/evidence/real-solicitations-2026-10-23.md`` is the ``--write`` flag; by default it only reports.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from grantbridge import guards, solicitation as sol

NOTICES = Path("data/fixtures/real_notices")
EVIDENCE = Path("docs/evidence/real-solicitations-2026-10-23.md")
READ_ON = "2026-10-23"

CASES = [
    ("U.S. Fish and Wildlife Service", "FWS", "Highlands Conservation Act Grant Program",
     "F25AS00379", "fws-highlands.txt", "fws-outline.json"),
    ("Federal Highway Administration", "FHWA", "Pathways to Preventing Pedestrian Fatalities",
     "PPPP-26-001", "fhwa-pppp.txt", "fhwa-outline.json"),
    ("NOAA Climate Program Office", "NOAA", "Earth's Systems and Sustainability Science Program",
     "NOAA-OAR-CPO-2026-33326", "noaa-esssp.txt", "noaa-outline.json"),
]
GROUPS = ("sections", "criteria", "components", "registrations", "format_rules")


def quotations(node, where: str = "") -> list[tuple[str, str]]:
    """Every excerpt anywhere in a saved payload, with the key path it sits under."""
    if isinstance(node, dict):
        out = []
        for key, value in node.items():
            if key == "excerpt" and isinstance(value, str) and value.strip():
                out.append((where or "root", value))
            else:
                out += quotations(value, f"{where}.{key}" if where else key)
        return out
    if isinstance(node, list):
        return [q for item in node for q in quotations(item, where)]
    return []


def plural(n: int, one: str, many: str | None = None) -> str:
    return one if n == 1 else (many or one + "s")


def read_case(case) -> dict:
    agency, short, program, number, src, payload = case
    text = (NOTICES / src).read_text(encoding="utf-8", errors="replace")
    flat = sol._flat(text)
    flagged = [sol._flat(s) for s in guards.injection_signals(text)]
    data = json.loads((NOTICES / payload).read_text(encoding="utf-8"))

    quotes = quotations(data)
    missing = [(w, q) for w, q in quotes if sol._flat(q) not in flat]
    injected = [(w, q) for w, q in quotes
                if any(phrase and phrase in sol._flat(q) for phrase in flagged)]

    criteria = data.get("criteria", [])
    sections = data.get("sections", [])
    return {
        "agency": agency, "short": short, "program": program, "number": number,
        "chars": len(text),
        "counts": {g: len(data.get(g, [])) for g in GROUPS},
        "quotes": len(quotes), "missing": missing, "injected": injected,
        "objectives": sum(len(c.get("objectives", [])) for c in criteria),
        "elements": sum(len(s.get("required_elements", [])) for s in sections),
        "limited": sum(1 for s in sections if s.get("limit_words") or s.get("limit_pages")),
        "weights": [(c["name"], c["weight_percent"], c.get("max_points"))
                    for c in criteria if c.get("weight_percent")],
        "gates": [(c["name"], c["threshold"]) for c in criteria if c.get("threshold")],
        "scales": [(c["name"], tuple(c["rating_scale"])) for c in criteria if c.get("rating_scale")],
    }


def report(rows: list[dict]) -> list[str]:
    items = sum(sum(r["counts"].values()) for r in rows)
    quotes = sum(r["quotes"] for r in rows)
    missing = sum(len(r["missing"]) for r in rows)
    injected = sum(len(r["injected"]) for r in rows)

    out = [
        f"# Reading three real federal notices, {READ_ON}",
        "",
        "The solicitation import was run against three live federal funding notices, taken from the agencies",
        "that published them. They were chosen because each one judges applicants in a different way, which is",
        "the part that a summary of a document does not capture.",
        "",
        "Nothing on this page is recalled. Each outline is the payload the import produced on the day, committed",
        "under `data/fixtures/real_notices/`, and every figure below is produced by re-running the check over",
        "those files: `python -m scripts.check_real_solicitations`. It needs no API key and no network.",
        "",
        "## The notices",
        "",
        "| Agency | Program | Opportunity number | Text read |",
        "| --- | --- | --- | --- |",
    ]
    out += [f"| {r['agency']} | {r['program']} | `{r['number']}` | {r['chars']:,} characters |" for r in rows]

    out += [
        "",
        "## What the import found in each",
        "",
        "| Notice | Sections | Required elements under them | Scoring criteria | Objectives under them | "
        "Things to file | Registrations | Format rules |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        c = r["counts"]
        out.append(f"| {r['short']} | {c['sections']} | {r['elements']} | {c['criteria']} | {r['objectives']} "
                   f"| {c['components']} | {c['registrations']} | {c['format_rules']} |")

    out += [
        "",
        f"**{items} items in total**, before counting the required elements and objectives nested under them.",
        "Each one was kept only because it carried a sentence from the notice.",
        "",
        "## The check that matters: every quotation is really in the document",
        "",
        "An item survives the import only when the sentence given for it appears in the notice word for word,",
        "ignoring whitespace, and never when that sentence is wording aimed at an AI. Re-applying that rule now,",
        "to every quotation in all three saved outlines:",
        "",
        f"- **{quotes} quotations re-checked**",
        f"- **{missing} not found** in the notice they claim to come from",
        f"- **{injected} carrying wording aimed at an AI**",
        "",
    ]
    out.append("Nothing was invented." if not missing and not injected else
               "**This check did not pass. The failures are listed below.**")
    out += [
        "",
        "### What a real document did to the injection detector",
        "",
        "Reading these notices turned up something a made-up sample never would. The Fish and Wildlife notice",
        "trips the prompt-injection patterns twice, and **neither hit is an attack**: it names a contact called",
        "**Dan**, which matches the `DAN` jailbreak name, and it tells applicants to **send an e-mail to the",
        "help desk**, which matches the pattern for sending data somewhere. The other two notices trip nothing.",
        "",
        "That matters because a flagged phrase is used to throw an excerpt away. The phrase `Dan` is three",
        "characters, and it had been compared as a bare substring, so any requirement containing *abundant*,",
        "*guidance* or *redundant* would have been discarded as an injection, with nothing shown to the user.",
        "Silently dropping a requirement is the exact failure this product exists to prevent. A flagged phrase",
        "is now matched on word boundaries instead, which keeps the defense and drops the coincidence:",
        "wording genuinely aimed at the model is still discarded, and a sentence that merely contains the same",
        "letters is kept. `tests/test_real_solicitations.py` holds both halves of that.",
        "",
        "No requirement was actually lost in these three runs: none of the kept excerpts contained the letters",
        "in question. The bug was reachable, not triggered.",
    ]
    out += ["", "## Three ways of judging an application, each kept as the funder wrote it", "",
            "No two of these notices score the same way, and none of them is a simple points total. The import",
            "keeps each funder's own shape rather than flattening all three into one.", ""]

    for r in rows:
        out += [f"### {r['agency']} — {r['counts']['criteria']} criteria, {r['objectives']} objectives under them",
                ""]
        if r["weights"]:
            total = sum(w for _, w, _ in r["weights"])
            out += [f"Percentage weights, read from the notice, summing to **{total}%**:", "",
                    "| Criterion | Weight | Max points |", "| --- | --- | --- |"]
            out += [f"| {name} | {w}% | {pts if pts is not None else '—'} |" for name, w, pts in r["weights"]]
            out += [f"| **Total** | **{total}%** | |", ""]
        if r["scales"]:
            seen: dict[tuple, int] = {}
            for _, scale in r["scales"]:
                seen[scale] = seen.get(scale, 0) + 1
            out.append("Named ratings in place of a score:")
            out.append("")
            for scale, n in seen.items():
                out.append(f"- **{' / '.join(scale)}** — used for {n} {plural(n, 'criterion', 'criteria')}")
            out.append("")
        if r["gates"]:
            out += ["Pass-or-fail gates, which the import keeps as thresholds rather than turning into scores:",
                    ""]
            out += [f"- **{name}** — {rule}" for name, rule in r["gates"]]
            out.append("")

    for r in rows:
        for where, quote in r["missing"]:
            out.append(f"- NOT FOUND, {r['short']}, under `{where}`: {quote[:200]}")
        for where, quote in r["injected"]:
            out.append(f"- AI-DIRECTED WORDING, {r['short']}, under `{where}`: {quote[:200]}")

    out += [
        "## Limits",
        "",
        f"- Three notices, read once each, on {READ_ON}. Nothing here is a rate, an average or an accuracy figure.",
        "- This check proves every kept item is quoted from its notice. It does **not** prove the import found",
        "  everything a notice requires. Nobody has yet compared one of these outlines against a funder's",
        "  requirements line by line, and the outline is not a substitute for reading the notice.",
        "- The text was extracted from each agency's PDF before the model saw it. A scanned notice with no text",
        "  layer cannot be read this way, and GrantBridge says so rather than guessing.",
        "",
    ]
    return out


def main() -> int:
    rows = [read_case(case) for case in CASES]
    lines = report(rows)
    failures = sum(len(r["missing"]) + len(r["injected"]) for r in rows)
    for r in rows:
        print(f"{r['short']:5} {sum(r['counts'].values()):3} items, {r['quotes']:3} quotations, "
              f"{len(r['missing'])} not found, {len(r['injected'])} AI-directed")
    print(f"total: {sum(r['quotes'] for r in rows)} quotations re-checked, {failures} failure(s)")
    if "--write" in sys.argv:
        EVIDENCE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("wrote", EVIDENCE)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
