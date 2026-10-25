"""Print report.html and slides.html to PDF: report.pdf (US letter) and slides.pdf (one slide per page).

Usage (from the repo folder, after python -m scripts.build_deliverables):
    pip install -r requirements-dev.txt && python -m playwright install msedge   # or: install chromium
    python -m scripts.print_pdfs

The report prints with its own print styles (@page letter). The slides use reveal.js's print mode (?print-pdf), which
lays out every slide at its own size. Both pages load offline: the script fails if either makes a network request.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def pages(pdf: Path) -> int:
    return len(re.findall(rb"/Type\s*/Page(?!s)", pdf.read_bytes()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--browser", default="msedge", help="Playwright channel: msedge, chrome, or chromium")
    args = parser.parse_args(argv)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed: pip install -r requirements-dev.txt", file=sys.stderr)
        return 2
    with sync_playwright() as p:
        browser = (p.chromium.launch(headless=True) if args.browser == "chromium"
                   else p.chromium.launch(channel=args.browser, headless=True))
        for name, query in (("report", ""), ("slides", "?print-pdf")):
            page = browser.new_page()
            outside = []
            page.on("request", lambda r: outside.append(r.url) if not r.url.startswith(("file:", "data:")) else None)
            page.goto((REPO / f"{name}.html").as_uri() + query)
            if name == "slides":
                page.wait_for_function("() => window.Reveal && Reveal.isReady()", timeout=15000)
            page.wait_for_timeout(1500)  # images are data URIs; give layout and fonts a moment
            if outside:
                raise SystemExit(f"{name}.html made network requests: {outside[:3]}")
            page.emulate_media(media="print")
            target = REPO / f"{name}.pdf"
            page.pdf(path=str(target), print_background=True, prefer_css_page_size=True)
            page.close()
            print(f"Wrote {target.name}: {pages(target)} pages, {target.stat().st_size / 1_000_000:.1f} MB")
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
