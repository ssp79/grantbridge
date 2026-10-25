"""Small shared UI helpers for the Streamlit pages."""

from __future__ import annotations

import re
from html import escape

import streamlit as st

from grantbridge.validation import US_STATES

STATUS_ICONS = {
    "Researching": ":material/search:",
    "Drafting": ":material/edit_note:",
    "Submitted": ":material/send:",
    "Awarded": ":material/emoji_events:",
    "Declined": ":material/block:",
}

_WORD_LIMIT_RE = re.compile(r"\((\d+)\s*words?\)", re.IGNORECASE)

# Colors, fonts, and radii live in .streamlit/config.toml. These few rules add what the theme cannot:
# visible keyboard focus, white cards (containers whose key starts with "card"), and a distinct edge for
# SAMPLE versus live grant cards, so the two can never look alike.
CSS = """
<style>
  /* ---------------------------------------------------------------- design tokens
     One palette and one spacing scale for the whole product. The theme in .streamlit/config.toml sets what
     Streamlit can theme itself (page and sidebar colours, radii, semantic colours); these tokens cover the rest,
     so no rule below hard-codes a colour. Small text uses --ink-soft and --teal-ink, which keep at least 4.5:1 on
     both --page and --card. */
  :root {
    --ivory: #F7F4EE; --navy: #173341; --teal: #287F78; --sand: #D9C6AA; --sage: #66756D;
    --teal-ink: #1F6A64;          /* teal darkened for small text and links */
    --ink-soft: #56645D;          /* sage darkened for captions */
    --page: #FAF8F3; --card: #FFFDFA; --rail: #F3EEE4;
    --line: #E3DACB; --line-soft: #EFE8DC;
    --s1: 4px; --s2: 8px; --s3: 16px; --s4: 24px; --s5: 32px; --s6: 48px;   /* 8px scale, with a 4px half-step */
    --r-sm: 8px; --r-md: 12px; --r-lg: 16px;
    --shadow-sm: 0 1px 2px rgba(23, 51, 65, 0.06);
    --shadow-md: 0 6px 20px rgba(23, 51, 65, 0.08);
    --serif: "Iowan Old Style", "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif;
  }

  /* ---------------------------------------------------------------- accessibility */
  a:focus-visible, button:focus-visible, summary:focus-visible, [role="tab"]:focus-visible,
  [role="radio"]:focus-visible, [role="checkbox"]:focus-visible, [role="switch"]:focus-visible,
  input:focus-visible, textarea:focus-visible, [tabindex]:focus-visible {
    outline: 3px solid var(--teal) !important; outline-offset: 2px !important;
  }

  /* ---------------------------------------------------------------- application shell */
  [data-testid="stSidebarNav"] a, [data-testid="stSidebarNav"] span { font-weight: 600; }
  [data-testid="stNavSectionHeader"] {
    font-size: 0.72rem !important; letter-spacing: 0.12em; text-transform: uppercase; color: var(--ink-soft) !important;
    font-weight: 700 !important; margin: var(--s3) 0 var(--s1) !important;
  }
  [data-testid="stSidebar"] [data-testid="stSidebarHeader"] { padding-bottom: var(--s2); }
  [data-testid="stSidebar"] hr { border-color: var(--line); margin: var(--s3) 0; }

  /* Streamlit's default top padding leaves the title floating; an application wants to start nearer the top. */
  [data-testid="stMainBlockContainer"] { padding-top: 3.5rem; }

  /* ---------------------------------------------------------------- content widths
     Full-bleed text is the single biggest thing that makes a Streamlit page look unconsidered: at 1440px a
     paragraph ran to about 160 characters a line. The public pages get a 1200px grid, and running prose inside
     them is held to roughly 70 characters. Anything that needs the room — images, charts, tables, columns, the
     demonstration, the footer — is exempted below. The application keeps its width for data-heavy screens. */
  .stApp:has(.st-key-about-page) [data-testid="stMainBlockContainer"] { max-width: 1200px; }
  .st-key-about-page [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]
    [data-testid="stMarkdownContainer"] > p,
  .st-key-about-page [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]
    [data-testid="stMarkdownContainer"] > ul { max-width: 42rem; }   /* about 70 characters a line */
  .st-key-about-page [data-testid="stColumn"] [data-testid="stMarkdownContainer"] > p,
  .st-key-about-page [data-testid="stColumn"] [data-testid="stMarkdownContainer"] > ul,
  .st-key-about-demo [data-testid="stMarkdownContainer"] > p,
  .st-key-public-footer [data-testid="stMarkdownContainer"] > p,
  div[class*="st-key-explore-card-"] [data-testid="stMarkdownContainer"] > p,
  div[class*="st-key-how-step-"] [data-testid="stExpander"] [data-testid="stMarkdownContainer"] > p,
  div[class*="st-key-how-step-"] [data-testid="stExpander"] [data-testid="stMarkdownContainer"] > ol,
  div[class*="st-key-how-step-"] [data-testid="stExpander"] [data-testid="stMarkdownContainer"] > ul {
    max-width: none;
  }
  /* The application: a ceiling so dashboards do not stretch on a very wide screen, but no reading column. */
  .stApp:not(:has(.st-key-about-page)) [data-testid="stMainBlockContainer"] { max-width: 1480px; }

  /* One page header everywhere: title, then a single line of orientation, then a hairline.
     flow-root keeps the last paragraph's bottom margin inside the box, or the rule is drawn through the text. */
  .st-key-page-head { display: flow-root; border-bottom: 1px solid var(--line); padding-bottom: var(--s3);
                      margin-bottom: var(--s4); }
  .st-key-page-head h1, .st-key-page-head h2 { margin-bottom: var(--s1); }
  .st-key-page-head [data-testid="stCaptionContainer"] p { color: var(--ink-soft); font-size: 0.97rem; margin: 0;
                                                           max-width: 46rem; }
  .st-key-page-head [data-testid="stMarkdownContainer"] p { color: var(--ink-soft); margin: 0; max-width: 46rem; }

  /* Running prose in the workspace is held to about 80 characters, the same reason as on the public pages: a
     1,400px line is hard to track back from. Only text sitting directly in the page is narrowed. Anything laid
     out deliberately — a card, a column, an expander, a chat message, an alert — keeps the width it was given,
     because its own box already sets the measure and narrowing it would leave a ragged gap inside. */
  [data-testid="stMainBlockContainer"] > div > [data-testid="stVerticalBlock"]
    > [data-testid="stElementContainer"] > [data-testid="stMarkdown"] [data-testid="stMarkdownContainer"] > p,
  [data-testid="stMainBlockContainer"] > div > [data-testid="stVerticalBlock"]
    > [data-testid="stElementContainer"] > [data-testid="stCaptionContainer"] > p {
      max-width: 48rem;
  }

  /* ---------------------------------------------------------------- panels and cards */
  div[class*="st-key-card"] { background: var(--card); border-radius: var(--r-md); }
  div[class*="st-key-card-sample"] { background: #FFFCF5; border-left: 6px solid #B54708 !important; }
  div[class*="st-key-card-live"] { border-left: 6px solid var(--navy) !important; }
  .gb-card-meta { color: var(--ink-soft); font-size: 0.95rem; margin: var(--s1) 0 var(--s2); }

  /* ---------------------------------------------------------------- status pills */
  .gb-badge {
    display: inline-block; padding: 0.1rem 0.55rem; border-radius: 999px;
    font-size: 0.8rem; font-weight: 600; border: 1px solid currentColor; margin-right: var(--s1);
  }
  .gb-badge-example { color: #7A2E0E; background: #FEF0C7; }
  .gb-badge-ok { color: #05603A; background: #E8F5EE; }
  .gb-badge-no { color: #912018; background: #FDECEA; }
  .gb-badge-warn { color: #7A2E0E; background: #FFF6E0; }
  .gb-badge-info { color: var(--navy); background: #E7EFEC; }
  .gb-badge-live { color: var(--navy); background: #E7EFEC; }

  /* ---------------------------------------------------------------- tabs
     Tabs read as plain words unless they are given an edge: a real user could not tell they were clickable. */
  [role="tablist"] {
    gap: var(--s1) !important; background: var(--rail); border-radius: var(--r-sm); padding: var(--s1);
    border: 1px solid var(--line); width: fit-content; max-width: 100%; flex-wrap: wrap;
  }
  [role="tablist"] [data-testid="stTab"] {
    border-radius: var(--r-sm); padding: 0.3rem 0.85rem !important; cursor: pointer;
  }
  [role="tablist"] [data-testid="stTab"] [data-testid="stMarkdownContainer"] p {
    font-weight: 600; color: var(--navy);
  }
  [role="tablist"] [data-testid="stTab"]:hover { background: var(--line-soft); }
  [role="tablist"] [data-testid="stTab"][aria-selected="true"] {
    background: #FFFFFF; box-shadow: var(--shadow-sm);
  }
  [role="tablist"] .react-aria-SelectionIndicator { display: none; }

  /* ---------------------------------------------------------------- public pages (Home and About GrantBridge)
     The same palette, set in an editorial key: ivory field, serif headings, generous measure. */
  .stApp:has(.st-key-about-page), .stApp:has(.st-key-about-page) [data-testid="stAppViewContainer"],
  .stApp:has(.st-key-about-page) header[data-testid="stHeader"],
  .stApp:has(.st-key-public-page), .stApp:has(.st-key-public-page) [data-testid="stAppViewContainer"],
  .stApp:has(.st-key-public-page) header[data-testid="stHeader"] { background: var(--ivory); }
  .st-key-about-page, .st-key-public-page { color: var(--navy); }
  .st-key-about-page h1, .st-key-about-page h2, .st-key-about-page h3, .st-key-about-page h4,
  .st-key-public-page h1, .st-key-public-page h2, .st-key-public-page h3, .st-key-public-page h4 {
    font-family: var(--serif) !important; color: var(--navy); font-weight: 600; letter-spacing: -0.012em;
  }
  .st-key-about-page [data-testid="stMarkdownContainer"] p, .st-key-about-page li,
  .st-key-public-page [data-testid="stMarkdownContainer"] p, .st-key-public-page li { color: var(--navy); }
  .st-key-about-page [data-testid="stCaptionContainer"] p, .st-key-about-page [data-testid="stCaptionContainer"] a,
  .st-key-public-page [data-testid="stCaptionContainer"] p,
  .st-key-public-page [data-testid="stCaptionContainer"] a { color: var(--ink-soft); }
  /* Section rhythm: a section opens with its eyebrow, so the gap above the label is the gap between sections,
     and the label stays tight against the heading it introduces. One rule, instead of spacers on every page. */
  div[class*="st-key-about-eyebrow"], div[class*="st-key-public-eyebrow"] { margin-top: var(--s6); }
  div[class*="st-key-about-eyebrow-hero"], div[class*="st-key-about-eyebrow-how"],
  div[class*="st-key-about-eyebrow-try"], div[class*="st-key-about-eyebrow-trust"],
  div[class*="st-key-about-eyebrow-aboutus"] { margin-top: 0; }
  .st-key-about-page h2, .st-key-about-page h3 { margin-top: var(--s1); margin-bottom: var(--s2); }
  div[class*="st-key-about-eyebrow"] [data-testid="stMarkdownContainer"] p,
  div[class*="st-key-public-eyebrow"] [data-testid="stMarkdownContainer"] p {
    font-size: 0.78rem; letter-spacing: 0.14em; text-transform: uppercase; color: var(--teal-ink) !important;
    font-weight: 700; margin: 0 0 var(--s1);
  }
  .st-key-about-lede [data-testid="stMarkdownContainer"] p,
  .st-key-public-lede [data-testid="stMarkdownContainer"] p {
    font-size: 1.16rem; line-height: 1.62; color: #2E4450 !important; max-width: 33rem;
  }
  .st-key-about-hero, .st-key-public-hero { padding: var(--s4) 0 var(--s2); }
  .st-key-about-hero h1, .st-key-public-hero h1 { font-size: 3.05rem; line-height: 1.07; margin: var(--s1) 0 var(--s3); }
  .st-key-about-photo img, .st-key-public-photo img { border-radius: 18px; border: 1px solid var(--sand); }
  .st-key-about-page button [data-testid="stMarkdownContainer"] p,
  .st-key-public-page button [data-testid="stMarkdownContainer"] p { color: inherit !important; }
  .st-key-about-page button[kind="secondary"], .st-key-public-page button[kind="secondary"] {
    background: transparent; border-color: var(--navy); color: var(--navy);
  }
  .st-key-about-page button[kind="secondary"]:hover, .st-key-public-page button[kind="secondary"]:hover {
    background: #EFE7DA; border-color: var(--navy); color: var(--navy);
  }
  .st-key-about-strip { border-top: 1px solid var(--sand); border-bottom: 1px solid var(--sand);
                        padding: 0.55rem 0 var(--s1); margin: var(--s2) 0 var(--s4); }
  .st-key-about-mission { border-left: 3px solid var(--sand); padding: var(--s1) 0 var(--s1) var(--s4);
                          margin: var(--s3) 0 var(--s4); }
  .st-key-about-mission [data-testid="stMarkdownContainer"] p {
    font-family: var(--serif); font-size: 1.36rem; line-height: 1.55;
  }
  .st-key-about-positioning h3 { font-size: 2rem; line-height: 1.22; max-width: 46rem; }
  div[class*="st-key-about-feature-"], div[class*="st-key-about-step-"], .st-key-about-trust,
  .st-key-about-preview, .st-key-public-preview { background: var(--card); border-color: var(--line) !important; }
  div[class*="st-key-about-feature-"] h3 { color: var(--teal); margin-bottom: 0; }
  .st-key-about-preview img, .st-key-public-preview img { border-radius: 10px; border: 1px solid var(--line); }
  .st-key-about-page [data-testid="stMetricValue"],
  .st-key-public-page [data-testid="stMetricValue"] { font-family: var(--serif); color: var(--navy); }
  .st-key-about-closing, div[class*="st-key-public-closing"] {
    background: var(--navy); border-radius: 20px; padding: 2.6rem 2.4rem;
  }
  .st-key-about-closing h3, .st-key-about-closing [data-testid="stMarkdownContainer"] p,
  div[class*="st-key-public-closing"] h3,
  div[class*="st-key-public-closing"] [data-testid="stMarkdownContainer"] p { color: var(--ivory) !important; }
  .st-key-about-closing button[kind="primary"], div[class*="st-key-public-closing"] button[kind="primary"] {
    background: var(--sand); border-color: var(--sand); color: var(--navy);
  }
  .st-key-about-closing button[kind="primary"]:hover,
  div[class*="st-key-public-closing"] button[kind="primary"]:hover { background: #E6D7BF; border-color: #E6D7BF; }
  .st-key-about-closing button[kind="secondary"], div[class*="st-key-public-closing"] button[kind="secondary"] {
    color: var(--ivory); border-color: var(--ivory);
  }
  .st-key-about-closing button[kind="secondary"]:hover,
  div[class*="st-key-public-closing"] button[kind="secondary"]:hover {
    background: rgba(247, 244, 238, 0.12); color: var(--ivory);
  }
  .st-key-about-closing button[kind="tertiary"], div[class*="st-key-public-closing"] button[kind="tertiary"] {
    color: var(--ivory);
  }
  .st-key-about-closing button[kind="tertiary"]:hover,
  div[class*="st-key-public-closing"] button[kind="tertiary"]:hover { color: var(--sand); }
  .st-key-about-closing button:focus-visible,
  div[class*="st-key-public-closing"] button:focus-visible { outline-color: var(--sand) !important; }
  .st-key-public-footer { border-top: 1px solid var(--line); padding-top: var(--s3); }
  .st-key-public-footer [data-testid="stCaptionContainer"] p { color: var(--ink-soft); }

  /* The live example must not read as another screenshot: it sits next to one. A teal frame, a tinted header
     strip, and tabs in the page's own colours mark it as something to touch. */
  .st-key-about-demo { border: 2px solid var(--teal) !important; background: var(--card); border-radius: var(--r-lg);
                       padding: var(--s1) 1.1rem 1.1rem; }
  .st-key-about-try [data-testid="stMarkdownContainer"] p {
    background: #E7F1EE; border-left: 4px solid var(--teal); border-radius: var(--r-sm); padding: 0.6rem 0.9rem;
    color: var(--navy) !important; font-size: 1.02rem;
  }
  .st-key-about-demo [role="tablist"] { background: #F1EBE0; border-color: var(--line); }
  .st-key-about-demo [role="tablist"] [data-testid="stTab"] [data-testid="stMarkdownContainer"] p {
    color: var(--teal-ink); font-size: 1.12rem !important;
  }
  .st-key-about-demo [role="tablist"] [data-testid="stTab"]:hover { background: #E6DCCB; }
  .st-key-about-demo [role="tablist"] [data-testid="stTab"][aria-selected="true"] { background: var(--teal); }
  .st-key-about-demo [role="tablist"] [data-testid="stTab"][aria-selected="true"]
    [data-testid="stMarkdownContainer"] p { color: var(--ivory); }
  div[class*="st-key-about-move"] [data-testid="stMarkdownContainer"] p,
  .st-key-about-demo-pick [data-testid="stMarkdownContainer"] p {
    color: var(--teal-ink) !important; font-weight: 700; font-size: 1.06rem; margin: var(--s2) 0 var(--s1);
  }
  .st-key-about-demo [role="tablist"] [data-testid="stTab"] { padding: 0.45rem 1.15rem !important; }
  .st-key-about-demo [data-testid="stCaptionContainer"] p { font-size: 0.98rem; }
  .st-key-about-demo [data-testid="stSlider"] [data-testid="stWidgetLabel"] p { font-size: 1.04rem; }
  .st-key-about_demo_confirm [data-testid="stCheckbox"] {
    transform: scale(1.22); transform-origin: left center; margin: 0.45rem 0 1.05rem;
  }
  .st-key-about_demo_payment [data-testid="stWidgetLabel"] p { font-size: 1.04rem; }
  .st-key-about_demo_payment button p { font-size: 1.02rem !important; }

  /* Home's explore cards. The page link is stretched over the whole card, so the card is the click target while
     staying one real, focusable anchor for the keyboard. */
  div[class*="st-key-explore-card-"] {
    position: relative; background: var(--card); border-color: var(--line) !important; transition:
      border-color 120ms ease, background 120ms ease, transform 120ms ease;
  }
  div[class*="st-key-explore-card-"]:hover { border-color: var(--teal) !important; background: #FFFFFF;
                                             transform: translateY(-2px); }
  div[class*="st-key-explore-card-"]::after {
    content: "↗"; position: absolute; top: var(--s3); right: var(--s3); color: var(--teal);
    font-size: 1.1rem; line-height: 1; transition: transform 120ms ease; pointer-events: none;
  }
  div[class*="st-key-explore-card-"]:hover::after { transform: translate(2px, -2px); }
  div[class*="st-key-explore-card-"] { padding: var(--s4) !important; }
  div[class*="st-key-explore-card-"] [data-testid="stPageLink"] a { background: transparent !important; }
  /* the link's label sits in its own markdown container, which resets the font: style that, not just the anchor */
  div[class*="st-key-explore-card-"] [data-testid="stPageLink"] a [data-testid="stMarkdownContainer"] p {
    font-family: var(--serif) !important; font-size: 1.3rem !important; font-weight: 600;
    color: var(--navy) !important; margin: 0;
  }
  div[class*="st-key-explore-card-"] [data-testid="stPageLink"] a::before { content: ""; position: absolute;
                                                                           inset: 0; border-radius: var(--r-md); }
  div[class*="st-key-explore-card-"]:focus-within { border-color: var(--teal) !important;
                                                    outline: 3px solid var(--teal); outline-offset: 2px; }
  div[class*="st-key-explore-card-"] [data-testid="stPageLink"] { margin: 0; }
  div[class*="st-key-explore-card-"] [data-testid="stPageLink"] a { padding: 0 !important; margin: 0 !important; }
  div[class*="st-key-explore-card-"] [data-testid="stCaptionContainer"] p { margin: var(--s1) 0 0; }
  div[class*="st-key-explore-card-"] [data-testid="stVerticalBlock"] { gap: 0; }

  /* How It Works: an editorial timeline. One hairline runs down the whole sequence, with the step number set
     on it, so the six steps read as a journey rather than six identical cards. */
  div[class*="st-key-how-step-"] {
    border-left: 2px solid var(--sand); padding: 0 0 var(--s6) var(--s5); margin-left: 44px;
  }
  div[class*="st-key-how-step-"]:last-of-type { border-left-color: transparent; }
  div[class*="st-key-how-num-"] [data-testid="stMarkdownContainer"] p {
    font-family: var(--serif); font-size: 1.5rem; font-weight: 600; color: var(--teal); line-height: 1;
    margin: 0 0 var(--s2) -72px; width: 56px; text-align: right;
  }
  div[class*="st-key-how-step-"] h3 { margin-top: 0; font-size: 1.72rem; }
  div[class*="st-key-how-helps-"] [data-testid="stMarkdownContainer"] p {
    color: var(--ink-soft) !important; border-left: 2px solid var(--line); padding-left: var(--s3);
    margin: var(--s2) 0 var(--s3);
  }
  div[class*="st-key-how-shot-"] img { border-radius: 10px; border: 1px solid var(--line); box-shadow: var(--shadow-sm); }
  div[class*="st-key-how-step-"] [data-testid="stExpander"] { border-color: var(--line); background: var(--card); }
  div[class*="st-key-how-step-"] [data-testid="stExpander"] summary p { font-weight: 600; color: var(--teal-ink); }

  @media (max-width: 640px) {
    div[class*="st-key-how-step-"] { margin-left: 0; padding-left: var(--s3); }
    div[class*="st-key-how-num-"] [data-testid="stMarkdownContainer"] p {
      margin-left: 0; width: auto; text-align: left;
    }
    .st-key-about-hero h1, .st-key-public-hero h1 { font-size: 2.15rem; }
    .st-key-about-mission [data-testid="stMarkdownContainer"] p { font-size: 1.14rem; }
    .st-key-about-positioning h3 { font-size: 1.5rem; }
    .st-key-about-closing, div[class*="st-key-public-closing"] { padding: var(--s4) var(--s3); }
    .st-key-about-strip { row-gap: 0.1rem !important; }
  }
</style>
"""


def inject_css() -> None:
    st.html(CSS)


def badge(text: str, kind: str) -> str:
    """Return badge HTML. Badges always carry text, so meaning never depends on color alone."""
    return f'<span class="gb-badge gb-badge-{kind}">{escape(text)}</span>'


def money(amount: int | None) -> str:
    # "\$" keeps Streamlit's Markdown from reading "$2,500 – $10,000" as a math formula.
    return f"\\${amount:,.0f}" if amount is not None else "—"


def amount_range(lo: int | None, hi: int | None) -> str:
    if lo and hi:
        return f"{money(lo)} – {money(hi)}"
    return money(hi or lo)


def deadline_label(deadline: str) -> str:
    return "Rolling (no fixed deadline)" if deadline == "rolling" else deadline


def state_name(code: str) -> str:
    return US_STATES.get(code, code)


def word_count(text: str) -> int:
    return len(text.split())


def word_limit(question: str) -> int | None:
    match = _WORD_LIMIT_RE.search(question)
    return int(match.group(1)) if match else None


def clip(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def profile_basis(org: dict) -> str:
    """One line naming the profile facts the deterministic checks use."""
    parts = [
        state_name(org["state"]) if org.get("state") else "state not set",
        f"501(c)(3): {org['tax_status']} (self-reported)" if org.get("tax_status") else "501(c)(3) status not set",
        f"budget {money(org['annual_budget'])}" if org.get("annual_budget") is not None else "budget not set",
        f"request {money(org['requested_amount'])}" if org.get("requested_amount") else "request not set",
    ]
    return " · ".join(parts)


_STEP_TYPES = {"code": "Code", "tool": "Tool", "llm": "AI model"}


def _details(values: dict) -> str:
    return "; ".join(f"{k}={','.join(map(str, v)) if isinstance(v, list) else v}" for k, v in values.items())


def _inputs(args: dict) -> str:
    """Trace inputs for display; the keyword is shown only as its length."""
    shown = {}
    for key, value in args.items():
        if key == "keyword_chars":
            continue
        if key == "has_keyword":
            shown["keyword"] = f"[redacted, {args.get('keyword_chars', 0)} chars]" if value else "none"
            continue
        if key == "message_chars":
            shown["message"] = f"[redacted, {value} chars]"
            continue
        shown[key] = value
    return _details(shown) or "—"


def usd(amount: float | None) -> str:
    """An estimated cost, e.g. $0, $0.00042, $0.0123, $1,250.00. None: it could not be estimated."""
    if amount is None:
        return "not estimated"
    if amount == 0:
        return "$0"
    if amount < 0.01:
        return f"${amount:.5f}"
    if amount < 1:
        return f"${amount:.4f}"
    return f"${amount:,.2f}"


def _step_tokens(s: dict) -> str:
    if s["kind"] != "llm":
        return "—"
    if s.get("usage_status") == "not reported":
        return "not reported"
    return f"{s['input_tokens']:,} / {s['cached_tokens']:,} / {s['output_tokens']:,}"


def trace_rows(steps: list[dict]) -> list[dict]:
    return [
        {
            "#": s["position"] + 1,
            "Step": s["tool"],
            "Type": _STEP_TYPES.get(s["kind"], s["kind"]),
            "Status": s["status"],
            "Time (ms)": s["duration_ms"],
            "Tokens in / cached / out": _step_tokens(s),
            "Est. cost": usd(s.get("cost_usd")) if s["kind"] == "llm" else "—",
            "Inputs (redacted)": _inputs(s["args"]),
            "Output": _details(s["summary"]) or "—",
        }
        for s in steps
    ]


def run_rows(runs: list[dict]) -> list[dict]:
    return [
        {
            "Run": r["id"],
            "What": r["kind"].replace("_", " "),
            "Status": r["status"],
            "Started (UTC)": r["started_at"].replace("T", " ")[:16],
            "Time (s)": round(r["duration_ms"] / 1000, 1),
            "Model": r["model"] or "—",
            "Model calls": r["model_calls"],
            "Tool calls": r["tool_calls"],
            "Tokens in / cached / out": (f"{r['input_tokens']:,} / {r['cached_tokens']:,} / {r['output_tokens']:,}"
                                         if r["model_calls"] else "—"),
            "Est. cost": usd(r["cost_usd"]) if r["model_calls"] else "$0 (no AI call)",
        }
        for r in runs
    ]


def _rate(x: float) -> str:
    return f"${x:.2f}" if round(x, 2) == x else f"${x:g}"


def price_note(model: str | None) -> str:
    """Where cost estimates come from, for captions (markdown-safe)."""
    from grantbridge import pricing

    price = pricing.price_for(model)
    if price is None:
        return md_safe(f"No price for {model or 'this model'} in data/pricing.json, so GrantBridge shows no "
                       "cost estimate for it.")
    t = price.tiers[0]
    return md_safe(f"Estimated with {price.source} (checked {price.checked}): {_rate(t.input)} per 1M input "
                   f"tokens, {_rate(t.cached_input)} cached, {_rate(t.cache_write)} written to the cache, "
                   f"{_rate(t.output)} output. Rates live in data/pricing.json.")


def token_breakdown(u: dict) -> str:
    """'Tokens: 5,432 in (2,304 from the prompt cache, 1,800 written to it) · 812 out (640 reasoning)'."""
    if u.get("unreported_calls"):
        return (f"**Tokens:** not reported for {u['unreported_calls']} of {u['model_calls']} model call(s), so no "
                "cost is estimated for them.")
    return (f"**Tokens:** {u['input_tokens']:,} in ({u['cached_tokens']:,} read from the prompt cache, "
            f"{u['cache_write_tokens']:,} written to it) · {u['output_tokens']:,} out "
            f"({u['reasoning_tokens']:,} of them reasoning)")


def usage_line(u: dict | None) -> str:
    """One caption line for an AI result: model, tokens, estimated cost, and time (markdown-safe)."""
    if not u or not u.get("model_calls"):
        return ""
    parts = [u.get("model") or "AI model"]
    if u.get("unreported_calls"):
        parts.append(f"token usage not reported for {u['unreported_calls']} call(s)")
    else:
        parts.append(f"{u['input_tokens']:,} input tokens ({u['cached_tokens']:,} cached) + "
                     f"{u['output_tokens']:,} output ({u['reasoning_tokens']:,} reasoning)")
    parts.append(f"estimated cost {usd(u['cost_usd'])}" if u.get("cost_usd") is not None else "cost not estimated")
    seconds = (u.get("elapsed_ms") or u.get("model_ms") or 0) / 1000
    parts.append(f"{seconds:.1f} s")
    if u.get("gateway_hits"):
        parts.append("reused Portkey's saved copy of an identical earlier answer (no new tokens billed)")
    return md_safe(" · ".join(parts))


def md_safe(text: str) -> str:
    """Text for st.markdown without dollar signs turning into math formulas."""
    return (text or "").replace("$", "\\$")


def external_md(text: str) -> str:
    """Outside text (grant listings, pasted funder text, chat input) safe to render as markdown:
    no images, no links to unknown sites, no HTML, and no dollar-sign math."""
    from grantbridge.guards import sanitize_external

    return md_safe(sanitize_external(text))
