"""Capture the interface previews used on the public How It Works page.

Three screens, with sample data, cropped to the content area so the page shows the workspace rather than the
navigation rail: Find Grants, a completed pursuit assessment, and the recommended portfolio.

Usage (from the repo folder; practice mode and a throwaway database, so no AI calls and no real data):
    pip install -r requirements-dev.txt && python -m playwright install msedge   # or: install chromium
    GRANTBRIDGE_DB=previews.db GRANTBRIDGE_ADVISOR_MODE=mock streamlit run streamlit_app.py --server.port 8620
    python -m scripts.capture_site_previews --url http://localhost:8620

Writes assets/previews/site-{find,pursue,portfolio}.webp (1200 px wide).
"""

from __future__ import annotations

import argparse
import io
import secrets
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "assets" / "previews"
WIDTH = 1500          # the page shows them about 700 px wide, so this stays sharp on a retina screen
CROP_LEFT = 330  # the navigation rail, left out of the preview


def main() -> int:
    from PIL import Image
    from playwright.sync_api import sync_playwright

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://localhost:8620")
    parser.add_argument("--browser", default="msedge")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = (p.chromium.launch(headless=True) if args.browser == "chromium"
                   else p.chromium.launch(channel=args.browser, headless=True))
        page = browser.new_page(viewport={"width": 1500, "height": 1000}, device_scale_factor=3)
        page.goto(args.url)
        page.wait_for_selector("text=Less time chasing funding", timeout=60000)
        page.get_by_test_id("stTopNav").get_by_role("link", name="Sign in", exact=True).click()
        page.wait_for_selector("text=Forgot your password?", timeout=30000)
        page.get_by_role("tab", name="Create account").click()
        page.wait_for_timeout(1200)
        page.get_by_label("Organization name").fill("Harbor Lantern Tutoring Collective")
        page.locator("input[type=text]").nth(2).fill(f"preview-{secrets.token_hex(3)}@example.org")
        pw = secrets.token_urlsafe(16)
        page.locator("input[type=password]").nth(1).fill(pw)
        page.locator("input[type=password]").nth(2).fill(pw)
        page.get_by_role("button", name="Create account").click()
        page.wait_for_selector("text=Get started in three steps", timeout=30000)
        page.get_by_role("button", name="Try it with sample data").click()
        page.wait_for_selector("text=Demo data loaded", timeout=30000)

        def shot(name: str, height: int) -> None:
            page.mouse.move(5, 5)
            page.wait_for_timeout(1200)
            raw = page.screenshot(clip={"x": CROP_LEFT, "y": 0, "width": 1500 - CROP_LEFT, "height": height})
            image = Image.open(io.BytesIO(raw)).convert("RGB")
            image = image.resize((WIDTH, round(image.height * WIDTH / image.width)), Image.LANCZOS)
            target = OUT / f"site-{name}.webp"
            image.save(target, "WEBP", quality=90, method=6)
            print(f"Wrote {target.relative_to(REPO)} ({image.width}x{image.height}, "
                  f"{target.stat().st_size // 1024} KB)")

        page.get_by_role("link", name="Find Grants", exact=True).click()
        # The public site shows the sample results: a live search would put real funders on a marketing page.
        page.get_by_text("Practice grants (samples)", exact=True).first.click()
        page.wait_for_selector("text=sample grant(s) match", timeout=30000)
        shot("find", 900)

        page.get_by_role("link", name="Should We Pursue?", exact=True).click()
        page.wait_for_timeout(2500)
        page.get_by_role("button", name="Assess this grant").click()
        page.wait_for_selector("text=Assessment saved:", timeout=180000)
        page.get_by_role("link", name="Should We Pursue?", exact=True).click()  # clear the notice
        page.wait_for_timeout(3000)
        shot("pursue", 950)

        page.get_by_role("link", name="Portfolio Strategist", exact=True).click()
        page.wait_for_selector("text=Your capacity and priorities", timeout=30000)
        page.wait_for_timeout(2000)
        shot("portfolio", 950)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
