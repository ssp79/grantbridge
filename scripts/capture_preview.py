"""Capture the About page's product preview: a real GrantBridge screen with the sample demo data.

The screen: Should We Pursue? -> Can we afford to win? for the SAMPLE grant New England Youth Opportunity Fund,
with the sample award terms and the sample organization's numbers.

Usage (from the repo folder; practice mode and a fresh database, so no AI calls and no real data):
    pip install -r requirements-dev.txt && python -m playwright install msedge   # or: install chromium
    GRANTBRIDGE_DB=preview.db GRANTBRIDGE_ADVISOR_MODE=mock streamlit run streamlit_app.py --server.port 8620
    python -m scripts.capture_preview --url http://localhost:8620

Signs up the sample account dana@harborlantern.example, so it needs a database where that account does not
exist yet. Writes assets/previews/workspace-preview.webp (1600 px wide).
"""

from __future__ import annotations

import argparse
import io
import secrets
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "assets" / "previews" / "workspace-preview.webp"
WIDTH = 1600


def main() -> int:
    from PIL import Image
    from playwright.sync_api import sync_playwright

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://localhost:8620")
    parser.add_argument("--browser", default="msedge", help="msedge, chrome, or chromium")
    args = parser.parse_args()

    with sync_playwright() as p:
        browser = (p.chromium.launch(headless=True) if args.browser == "chromium"
                   else p.chromium.launch(channel=args.browser, headless=True))
        page = browser.new_page(viewport={"width": 1400, "height": 1000}, device_scale_factor=2)
        page.goto(args.url)
        page.wait_for_selector(".st-key-about-closing", timeout=60000)
        page.get_by_test_id("stTopNav").get_by_role("link", name="Sign in", exact=True).click()
        page.wait_for_selector("text=Forgot your password?", timeout=30000)
        page.get_by_role("tab", name="Create account").click()
        page.wait_for_timeout(1200)
        page.get_by_label("Organization name").fill("Harbor Lantern Tutoring Collective")
        page.locator("input[type=text]").nth(2).fill("dana@harborlantern.example")
        password = secrets.token_urlsafe(16)
        boxes = page.locator("input[type=password]")
        boxes.nth(1).fill(password)
        boxes.nth(2).fill(password)
        page.get_by_role("button", name="Create account").click()
        page.wait_for_selector("text=Get started in three steps", timeout=30000)
        page.get_by_role("button", name="Try it with sample data").click()
        page.wait_for_selector("text=Demo data loaded", timeout=30000)
        page.get_by_role("link", name="Should We Pursue?", exact=True).click()
        page.wait_for_timeout(2500)
        page.get_by_role("combobox", name="Grant or application").click()
        page.keyboard.type("New England Youth Opportunity Fund")
        page.keyboard.press("Enter")
        page.wait_for_timeout(2500)
        page.get_by_role("tab", name="Can we afford to win?").click()
        page.wait_for_timeout(1000)
        page.get_by_role("button", name="Use the sample award terms").click()
        page.wait_for_selector("text=Award terms saved", timeout=60000)
        page.get_by_role("tab", name="Can we afford to win?").click()
        page.wait_for_timeout(800)
        page.get_by_role("tab", name="Your numbers").click()
        page.wait_for_timeout(800)
        for label, value in (("Award you would request ($)", "55000"), ("Cash reserves you could use ($)", "30000"),
                             ("Match money already committed ($)", "10000")):
            box = page.get_by_label(label, exact=True)
            box.fill(value)
            box.press("Tab")
        page.get_by_role("button", name="Save my numbers").click()
        page.wait_for_selector("text=Your numbers are saved", timeout=30000)
        # the saved notice shows once; opening the same page again clears it
        page.get_by_role("link", name="Should We Pursue?", exact=True).click()
        page.wait_for_timeout(3000)
        for name in ("Can we afford to win?", "Summary"):  # reopened, the page may show its first tabs
            tab = page.get_by_role("tab", name=name, exact=True)
            if tab.get_attribute("aria-selected") != "true":
                tab.click()
                page.wait_for_timeout(1500)
        page.mouse.move(700, 5)
        page.wait_for_timeout(1500)
        page.evaluate("() => document.querySelector('[data-testid=stMain]').scrollTo(0, 0)")
        summary = page.locator(".st-key-card-afford-summary").bounding_box()
        height = int(min(summary["y"] + summary["height"] * 0.6, 2400))
        page.set_viewport_size({"width": 1400, "height": max(height + 20, 1000)})
        page.wait_for_timeout(1500)
        png = page.screenshot(clip={"x": 0, "y": 0, "width": 1400, "height": height})
        browser.close()

    image = Image.open(io.BytesIO(png)).convert("RGB")
    image = image.resize((WIDTH, round(image.height * WIDTH / image.width)), Image.LANCZOS)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUT, "WEBP", quality=82, method=6)
    print(f"Wrote {OUT.relative_to(REPO)} ({image.width}x{image.height}, {OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
