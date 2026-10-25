"""Record a captioned demo video of the running app: a tour of about two and a half minutes, with sample data.

Usage (from the repo folder, with the app running; see README):
    pip install -r requirements-dev.txt && python -m playwright install msedge ffmpeg
    streamlit run streamlit_app.py --server.port 8600
    python -m scripts.record_demo --url http://localhost:8600

This is an automated screen recording of the real app in a headless browser. The captions and the round pointer are
drawn by this script on top of the page; nothing on the page is edited. AI steps are live when the server has an API
key (a few thousand tokens). Writes demo-video/grantbridge-demo-<date>.webm. That folder is not committed: the video
is submitted on its own.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts.e2e_scenario import AFFORD, AFFORD_GRANT, AFFORD_NUMBERS, Run, wait_for_answer

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "demo-video"
SIZE = {"width": 1280, "height": 720}

CAPTION_JS = """text => {
  let box = document.getElementById('gb-caption');
  if (!box) {
    box = document.createElement('div'); box.id = 'gb-caption';
    Object.assign(box.style, {position: 'fixed', left: '50%', bottom: '26px', transform: 'translateX(-50%)',
      maxWidth: '80%', background: 'rgba(23, 51, 65, 0.95)', color: '#F7F4EE', padding: '12px 22px',
      borderRadius: '12px', font: '600 20px/1.35 "Segoe UI", system-ui, sans-serif', zIndex: 999999,
      boxShadow: '0 8px 24px rgba(0, 0, 0, 0.25)', textAlign: 'center', pointerEvents: 'none'});
    document.body.appendChild(box);
  }
  box.textContent = text;
  box.style.display = text ? 'block' : 'none';
}"""

POINTER_JS = """([x, y]) => {
  let dot = document.getElementById('gb-pointer');
  if (!dot) {
    dot = document.createElement('div'); dot.id = 'gb-pointer';
    Object.assign(dot.style, {position: 'fixed', width: '24px', height: '24px', borderRadius: '50%',
      border: '3px solid #D9C6AA', background: 'rgba(40, 127, 120, 0.35)', zIndex: 999998, pointerEvents: 'none',
      transform: 'translate(-50%, -50%)', transition: 'left 0.45s ease, top 0.45s ease', left: '50%', top: '40%'});
    document.body.appendChild(dot);
  }
  dot.style.left = x + 'px'; dot.style.top = y + 'px';
}"""


class Tour:
    def __init__(self, page, url: str):
        self.pg, self.url = page, url
        self.run = Run(page, OUT, "video-")  # for its sidebar navigation and sign-up helpers

    def say(self, text: str, seconds: float = 3.5) -> None:
        self.pg.evaluate(CAPTION_JS, text)
        self.pg.wait_for_timeout(int(seconds * 1000))

    def point(self, locator) -> None:
        locator.scroll_into_view_if_needed()
        box = locator.bounding_box()
        if box:
            self.pg.evaluate(POINTER_JS, [box["x"] + box["width"] / 2, box["y"] + box["height"] / 2])
            self.pg.wait_for_timeout(650)

    def click(self, locator) -> None:
        self.point(locator)
        locator.click()

    def scroll(self, pixels: int, steps: int = 6) -> None:
        for _ in range(steps):
            self.pg.evaluate("d => document.querySelector('[data-testid=stMain]').scrollBy({top: d, behavior: "
                             "'smooth'})", pixels // steps)
            self.pg.wait_for_timeout(350)

    def nav(self, name: str) -> None:
        link = self.pg.get_by_role("link", name=name, exact=True)
        if link.count():  # the sidebar hides later pages behind "View N more"; Run.nav opens that itself
            self.point(link)
        self.run.nav(name)


def tour(t: Tour) -> None:
    pg = t.pg
    pg.goto(t.url)
    pg.wait_for_selector(".st-key-about-closing", timeout=60000)
    t.say("GrantBridge: an AI grant strategy partner for small nonprofits. An automated recording of the running app "
          "· sample data · captions added by the recording script", 6)
    t.say("The public Home page. No sign-in needed.", 3)
    t.scroll(1200)
    t.say("Five public pages, each at its own address. Try Features is the one a visitor can play with.", 3.5)
    t.run.top_nav("Try Features")
    demo = pg.locator(".st-key-about-demo")
    demo.wait_for(timeout=60000)
    demo.scroll_into_view_if_needed()
    t.say("Its sample example runs GrantBridge's real rules, with no AI call: Should we pursue it?", 4)
    t.click(pg.get_by_role("tab", name="Can we afford to win it?", exact=True))
    t.say("And can we afford to win it? A grant that fits can still strain a small budget.", 4)
    thumb = pg.locator(".st-key-about_demo_match").get_by_role("slider")
    t.point(thumb)
    thumb.focus()
    thumb.press("Home")
    t.say("Remove the required match, and the cash winning would tie up falls at once.", 4)

    t.say("Create a free account, then load the sample demo organization.", 2.5)
    t.run.sign_up(t.url, "Demo Video Org")
    t.click(pg.get_by_role("button", name="Try it with sample data"))
    pg.wait_for_selector("text=Demo data loaded", timeout=30000)
    t.say("The sample Harbor Lantern Tutoring Collective: a profile, saved SAMPLE grants, and an application.", 3.5)

    t.nav("Find Grants")
    t.say("Find Grants opens on real federal listings from Grants.gov. The samples are for learning the tool.", 3)
    t.click(pg.get_by_text("Practice grants (samples)", exact=True).first)
    pg.wait_for_selector("text=sample grant(s) match", timeout=30000)
    t.say("Find Grants: SAMPLE listings and live Grants.gov, each labeled by source. Code checks eligibility, and "
          "unknown is never treated as ineligible.", 5)
    t.scroll(500)

    t.nav("Should We Pursue?")
    t.say("Should We Pursue? Code decides the outcome from rules shown on the page. The AI only adds fit evidence.", 3)
    t.click(pg.get_by_role("combobox", name="Grant or application"))
    pg.get_by_role("option", name="Connecticut After-School Learning Grant · SAMPLE · saved", exact=True).click()
    pg.wait_for_timeout(1500)
    t.click(pg.get_by_role("button", name=re.compile(r"^(Assess this grant|Assess again)$")))
    pg.wait_for_selector("text=Assessment saved: Promising, but verify first.", timeout=180000)
    t.say("Promising, but verify first: two listing rules need a person to confirm them.", 4)
    form = pg.locator("[data-testid='stForm']").filter(has_text="Save confirmations and assess again")
    for i in range(form.locator("[data-testid='stCheckbox']").count()):
        t.click(form.locator("[data-testid='stCheckbox']").nth(i))
    t.click(form.get_by_role("button", name="Save confirmations and assess again"))
    pg.wait_for_selector("text=Assessment saved: Strong candidate.", timeout=180000)
    t.say("Confirmed by the user, and labeled as theirs: Strong candidate.", 4)

    t.click(pg.get_by_role("combobox", name="Grant or application"))
    pg.get_by_role("option", name=AFFORD_GRANT, exact=True).click()
    pg.wait_for_timeout(1500)
    t.click(pg.get_by_role("tab", name="Can we afford to win?", exact=True))
    t.say("Can we afford to win? Paste the funder's award terms (here, sample ones).", 3)
    box = pg.locator("textarea[aria-label='Notice or award terms']")
    t.point(box)
    box.fill(AFFORD["notice"])
    t.click(pg.get_by_role("button", name=re.compile(r"^Find the award terms")))
    t.say("The AI lists each condition with a quote. Code checks that every quote, and every number in it, is "
          "really in the text.", 1)
    pg.wait_for_selector("text=Award terms saved:", timeout=180000)
    t.click(pg.get_by_role("tab", name="Terms found", exact=True))
    t.say("Every term is quoted word for word, with its source. Anything the text does not state stays unknown.", 4)
    t.scroll(600)
    t.click(pg.get_by_role("tab", name="Your numbers", exact=True))
    t.say("Enter the organization's own numbers: the award, its reserves, and match money already committed.", 2)
    for label, value in AFFORD_NUMBERS:
        field = pg.get_by_label(label, exact=True)
        t.point(field)
        field.fill(value)
        field.press("Tab")
    t.click(pg.get_by_role("button", name="Save my numbers"))
    pg.wait_for_selector("text=Your numbers are saved", timeout=30000)
    t.click(pg.get_by_role("tab", name="Summary", exact=True))
    card = pg.locator(".st-key-card-afford-summary")
    card.get_by_text("Winning would strain your cash").first.wait_for(timeout=30000)
    card.scroll_into_view_if_needed()
    peak = card.get_by_test_id("stMetric").filter(has_text="Cash tied up at the worst point") \
        .get_by_test_id("stMetricValue").inner_text().strip()
    t.say(f"Code simulates every day of the grant: winning would tie up about {peak} of the organization's own cash, "
          "against $30,000 of reserves.", 5.5)
    t.click(pg.get_by_role("tab", name="What if", exact=True))
    option = pg.locator(".st-key-afford-what-if").get_by_text("In installments (part in advance)", exact=True)
    t.click(option)
    t.say("What if half were paid in advance? The arithmetic reruns at once, and nothing is saved.", 4.5)
    t.click(pg.get_by_role("tab", name="Should we pursue?", exact=True))
    t.click(pg.get_by_role("button", name=re.compile(r"^(Assess this grant|Assess again)$")))
    pg.wait_for_selector("text=Assessment saved: Proceed with caution.", timeout=180000)
    t.say("The cash burden feeds the go/no-go decision: Proceed with caution.", 4)

    t.nav("Portfolio Strategist")
    pg.wait_for_selector("text=Your capacity and priorities", timeout=30000)
    t.say("Portfolio Strategist: the grants that fit the team's weekly hours, each with its reason.", 4)
    t.click(pg.locator(".st-key-pf_defer_cash label").first)
    card = pg.locator(".st-key-card-pf-grant-sample-05")
    card.get_by_text("You chose to defer grants that would strain your cash").first.wait_for(timeout=30000)
    card.scroll_into_view_if_needed()
    t.say("Switched on, grants that would strain the cash are deferred, with the reason.", 4)

    # ---- the funder's own solicitation, read into an outline
    t.nav("Applications")
    t.say("Most solicitations do not ask questions. They prescribe the sections you must write.", 3.5)
    t.click(pg.get_by_role("button", name="New application").first)
    pg.wait_for_timeout(2000)
    t.click(pg.get_by_text("From the funder's documents"))
    pg.wait_for_timeout(1500)
    pg.set_input_files("input[type=file]", str(REPO / "data" / "fixtures" / "sample_solicitation.pdf"))
    pg.wait_for_timeout(2000)
    t.say("Upload the funder's notice as a PDF. GrantBridge reads it, and code keeps only what it can find in "
          "the document word for word.", 4)
    t.click(pg.get_by_role("button", name="Analyze the solicitation"))
    pg.wait_for_selector("text=Check what GrantBridge found", timeout=180000)
    t.say("Everything it found, each beside the sentence it came from, and nothing saved until you confirm.", 4.5)
    t.scroll(900)
    title = pg.get_by_label("New application title *")
    if title.count():
        title.fill("Harborview Reading Fund")
        pg.wait_for_timeout(1200)
    t.click(pg.get_by_role("button", name=re.compile(r"^Add \d+ item\(s\)")).first)
    pg.wait_for_timeout(6000)
    t.click(pg.get_by_role("tab", name="Proposal outline"))
    pg.wait_for_timeout(2500)
    t.say("The outline the funder asked for: every section, what each must contain, and how it will be scored.",
          4.5)
    t.scroll(700)
    t.say("Or take it into Word, write there, and upload it back.", 3.5)

    t.nav("AI Grant Advisor")
    ask = pg.get_by_placeholder("Ask about grants, requirements, or your applications…")
    t.point(ask)
    ask.fill("Which sample grants fit us best?")
    ask.press("Enter")
    t.say("AI Grant Advisor: one agent with seven real tools. Code checks every figure it writes.", 1)
    wait_for_answer(pg, "Which sample grants fit us best?")
    pg.wait_for_selector("text=From your records", timeout=30000)
    t.say("Each answer lists the facts it used and where they came from.", 4)

    t.nav("Account")
    t.click(pg.get_by_text("Technical details: your AI usage and estimated cost"))
    pg.wait_for_selector("text=AI runs, last 24 h", timeout=10000)
    t.say("Every AI run records its model, tokens, time, and estimated cost.", 4)
    t.say("GrantBridge: less time chasing funding, more time changing lives. A course demo with sample data, not "
          "production-grade security.", 5)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://localhost:8600")
    parser.add_argument("--browser", default="msedge", help="Playwright channel: msedge, chrome, or chromium")
    args = parser.parse_args(argv)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed: pip install -r requirements-dev.txt", file=sys.stderr)
        return 2
    OUT.mkdir(exist_ok=True)
    raw = OUT / "raw"
    with sync_playwright() as p:
        browser = (p.chromium.launch(headless=True) if args.browser == "chromium"
                   else p.chromium.launch(channel=args.browser, headless=True))
        context = browser.new_context(viewport=SIZE, record_video_dir=str(raw), record_video_size=SIZE)
        page = context.new_page()
        started = datetime.now(timezone.utc)
        target = OUT / f"grantbridge-demo-{started.strftime('%Y-%m-%d')}.webm"
        try:
            tour(Tour(page, args.url))
        finally:
            video = page.video
            page.close()  # the video is written when its page closes
            video.save_as(target)  # inside the Playwright context, while the connection is open
            context.close()
            browser.close()
        seconds = (datetime.now(timezone.utc) - started).total_seconds()
    shutil.rmtree(raw, ignore_errors=True)
    print(f"Wrote {target.relative_to(REPO)} ({target.stat().st_size / 1_000_000:.1f} MB, about {seconds:.0f} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
