"""Deterministic checks applied to AI-written text before anyone sees it.

  - strip_open_claims: drop sentences saying a grant "is open" or "is accepting
    applications" (negated sentences such as "not accepting yet" are kept).
  - strip_eligibility_claims: drop sentences saying the organization "is eligible"
    or "qualifies"; only the funder can decide that.
  - strip_predictions: drop sentences predicting funding ("likely to be funded");
    proposal reviews are advisory, never forecasts.
  - unverified_figures: dollar amounts, percentages, and dates that do not appear
    in the grounding text (tool results, the profile, the user's own message).

None of these use AI. They run on the model's output, so they hold even when a
model ignores its instructions.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date

# Sentence ends (spaces after . ! ?) and line breaks; the group keeps them so text can be rebuilt.
_SENTENCE = re.compile(r"((?<=[.!?])[ \t]+|[ \t]*\n\s*)")
_NEGATION = re.compile(r"\b(?:not|no longer|never|isn't|aren't|won't|cannot|can't|unclear|unknown|whether)\b|n't\b",
                       re.IGNORECASE)
_OPEN_CLAIM = re.compile(
    r"\b(?:is|are|remains?|currently|now|still)\s+(?:open|accepting)\b"
    r"|\baccepting (?:applications|proposals|submissions)\b"
    r"|\bopen for (?:applications|proposals|submissions)\b"
    r"|\bapplications? (?:are|is) (?:open|being accepted)\b",
    re.IGNORECASE,
)
_ELIGIBILITY_CLAIM = re.compile(
    r"\b(?:you|your organization|your nonprofit|harbor lantern|the organization|it|they)\s+"
    r"(?:are|is|'re|definitely|clearly|fully|would be|will be)?\s*"
    r"(?:definitely |clearly |fully )?(?:eligible|qualif(?:y|ies|ied))\b"
    r"|\b(?:meets?|satisf(?:y|ies)) all (?:the )?(?:requirements|criteria|eligibility)\b",
    re.IGNORECASE,
)


_PREDICTION = re.compile(
    r"\b(?:likely|unlikely|likelihood|certain(?:ly)?|sure|guarantee[sd]?|chances?|odds|probability|probabl[ey]"
    r"|good shot|strong contender|front-?runner)\b[^.!?\n]{0,60}?"
    r"\b(?:funded|funding|awarded|award|win|wins|winning|approved|approval|selected|successful|success)\b"
    r"|\b(?:will|would|should|is going to|are going to)\s+(?:be|get)\s+(?:funded|awarded|approved|selected)\b"
    r"|\b(?:will|would)\s+(?:score|rank)\s+(?:highly|well|high|top)\b"
    r"|\bfunders?\s+(?:will|would)\s+(?:love|fund|approve|choose|select|reward)\b",
    re.IGNORECASE,
)


def strip_sentences(text: str, drop) -> tuple[str, int]:
    """Drop each sentence or line for which drop(sentence) is true, unless it is negated ("not yet committed").

    Every other separator (line breaks, bullets) is kept intact.
    """
    parts = _SENTENCE.split((text or "").strip())  # [sentence, separator, sentence, separator, ...]
    kept, removed = [], 0
    for i in range(0, len(parts), 2):
        sentence, sep = parts[i], parts[i + 1] if i + 1 < len(parts) else ""
        if drop(sentence) and not _NEGATION.search(sentence):
            removed += 1
            continue
        kept.append(sentence + sep)
    return "".join(kept).strip(), removed


def _strip(text: str, pattern: re.Pattern) -> tuple[str, int]:
    return strip_sentences(text, lambda sentence: bool(pattern.search(sentence)))


def mark_unverified(text: str, raw: str) -> str:
    """Append "(unverified)" after each whole occurrence of a figure."""
    return re.sub(re.escape(raw) + r"(?![\d,.]*\d)", f"{raw} (unverified)", text)


def strip_open_claims(text: str) -> tuple[str, int]:
    return _strip(text, _OPEN_CLAIM)


def strip_eligibility_claims(text: str) -> tuple[str, int]:
    return _strip(text, _ELIGIBILITY_CLAIM)


def strip_predictions(text: str) -> tuple[str, int]:
    """Drop sentences predicting funding ("likely to be funded", "will score highly"); nobody here can know that."""
    return _strip(text, _PREDICTION)


# ---------------------------------------------------------------- figures

@dataclass(frozen=True)
class Figure:
    kind: str  # "money", "percent", or "date"
    raw: str
    value: str  # normalized, comparable form

_MONEY = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)\s?(k|m|million|thousand|billion)?\b", re.IGNORECASE)
_PERCENT = re.compile(r"\b(\d+(?:\.\d+)?)\s?(?:%|percent\b)", re.IGNORECASE)
_MONTHS = ("january february march april may june july august september october november december").split()
_DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "iso"),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"), "mdy"),
    (re.compile(r"\b(" + "|".join(m[:3] for m in _MONTHS) + r")[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})\b", re.IGNORECASE),
     "month"),
]
_MULTIPLIERS = {"k": 1_000, "thousand": 1_000, "m": 1_000_000, "million": 1_000_000, "billion": 1_000_000_000}
_PLAIN_NUMBER = re.compile(r"\b\d[\d,]*(?:\.\d+)?\b")


def _money_value(number: str, unit: str | None) -> str:
    amount = float(number.replace(",", "")) * _MULTIPLIERS.get((unit or "").lower(), 1)
    return f"{amount:.2f}"


def _dates(text: str) -> list[tuple[str, str]]:
    found = []
    for pattern, kind in _DATE_PATTERNS:
        for m in pattern.finditer(text):
            try:
                if kind == "iso":
                    d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                elif kind == "mdy":
                    d = date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
                else:
                    month = [x[:3] for x in _MONTHS].index(m.group(1).lower()[:3]) + 1
                    d = date(int(m.group(3)), month, int(m.group(2)))
            except ValueError:
                continue
            found.append((m.group(0), d.isoformat()))
    return found


def extract_figures(text: str) -> list[Figure]:
    figures = [Figure("money", m.group(0).strip(), _money_value(m.group(1), m.group(2))) for m in _MONEY.finditer(text)]
    figures += [Figure("percent", m.group(0).strip(), f"{float(m.group(1)):.2f}") for m in _PERCENT.finditer(text)]
    figures += [Figure("date", raw, iso) for raw, iso in _dates(text)]
    return figures


def _numeric_leaves(node):
    if isinstance(node, bool):
        return
    if isinstance(node, (int, float)):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _numeric_leaves(value)
    elif isinstance(node, list):
        for value in node:
            yield from _numeric_leaves(value)


def grounding_values(texts: list[str]) -> set[tuple[str, str]]:
    """Every money, percent, and date value that the grounding texts support.

    - Figures written out ("$10,000", "72%", "Dec 11, 2026") count as themselves.
    - In JSON tool results, number values count as dollar amounts, so
      "annual_budget_usd": 285000 grounds "$285,000". Numbers inside prose
      ("90 minutes") do not, and never ground a percentage.
    - In plain text (the user's own message), bare numbers count as dollar amounts.
    """
    values: set[tuple[str, str]] = set()
    for text in texts:
        for f in extract_figures(text):
            values.add((f.kind, f.value))
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            data = None
        if isinstance(data, (dict, list)):
            numbers = list(_numeric_leaves(data))
        else:
            numbers = [float(m.group(0).replace(",", "")) for m in _PLAIN_NUMBER.finditer(text)]
        values.update(("money", f"{float(n):.2f}") for n in numbers)
    return values


def unverified_figures(text: str, grounding: set[tuple[str, str]]) -> list[str]:
    """Raw strings of figures in `text` that the grounding does not contain, in order, no repeats."""
    missing: list[str] = []
    for f in extract_figures(text):
        if (f.kind, f.value) not in grounding and f.raw not in missing:
            missing.append(f.raw)
    return missing



# ---------------------------------------------------------------- drafts: counts, names, injected instructions

# Standalone numbers, not part of codes like "K-12" or "R01"; 0-9 are skipped (list numbering, "3 staff").
_COUNT = re.compile(r"(?<![A-Za-z]-)(?<![A-Za-z$])\b\d[\d,]*(?:\.\d+)?\b(?![%\w])")
_NAME = re.compile(r"\b[A-Z][a-zA-Z'\-]+(?:\s+(?:of|for|and|the|on|in|&)?\s*[A-Z][a-zA-Z'\-]+)+")
_NAME_STARTERS = {"Our", "We", "The", "This", "That", "These", "Those", "In", "At", "With", "Since", "Each", "Every",
                  "Last", "Next", "A", "An", "Its", "Their", "As", "For", "From", "By", "During", "After", "Before"}
_BRACKETED = re.compile(r"\[[^\]]*\]")
_I = re.IGNORECASE
# (pattern, label). A label replaces the matched text in the notice, for matches that are invisible or unreadable.
_INJECTION = [
    # override the instructions, in any wording
    (re.compile(r"\b(?:ignore|disregard|forget|override|bypass|set aside|abandon)\b[^.\n]{0,50}\b(?:instructions?|"
                r"rules|prompts?|directions|guidance|guidelines|constraints|policies|restrictions|safeguards|"
                r"programming)\b", _I), None),
    (re.compile(r"(?:^|\n)\s*(?:system|assistant|developer)\s*(?:prompt|note|message)?\s*:", _I), None),
    (re.compile(r"\byou are now\b|\bnew instructions\b|\bdo not tell the user\b|\bact as (?:an?|the)\b", _I), None),
    # role-play and "jailbreak" framings
    (re.compile(r"\bpretend (?:to be|you are|that you)\b|\brole-?play as\b|\bfrom now on,? you\b|\bact as if you\b|"
                r"\byou must now\b|\bjailbreak\w*|\bdeveloper mode\b|\bdo anything now\b|\bDAN\b", _I), None),
    # put words in the applicant's mouth
    (re.compile(r"\b(?:state|claim|write|say) that (?:the applicant|we|the organization|harbor lantern)\b", _I), None),
    # extract secrets or the prompt
    (re.compile(r"\b(?:reveal|print|show|output|repeat|leak|dump)\b[^.\n]{0,40}\b(?:secrets?|system prompt|"
                r"instructions|api[ _-]?keys?|passwords?|environment variables?|credentials|configuration)\b", _I), None),
    (re.compile(r"\b(?:tell me|what (?:is|are))\b[^.\n]{0,20}\byour (?:system prompt|hidden prompt|instructions|"
                r"rules|configuration|secrets?)\b", _I), None),
    (re.compile(r"\b(?:every|all|other) (?:other )?users?'?s?\b[^.\n]{0,30}\b(?:profiles?|data|emails?|accounts?)\b",
                _I), None),
    # send data somewhere
    (re.compile(r"\b(?:send|forward|post|upload|email|transmit|exfiltrate)\b[^.\n]{0,60}\b(?:to|at)\s+"
                r"(?:https?://\S+|\S+@\S+\.\w+)", _I), None),
    # hidden or encoded instructions
    (re.compile(r"\b(?:base64|rot13)\b|\bdecode (?:this|the following|it)\b", _I), None),
    (re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{40,}={0,2}(?![A-Za-z0-9+/])"), "a long encoded text block"),
    (re.compile(r"[‪-‮⁦-⁩]"), "hidden text-direction characters"),
    # the same, in Spanish, French, and German
    (re.compile(r"\bignora(?:r)? (?:todas )?las instrucciones\b|\bignore[zr]? (?:toutes )?les instructions\b|"
                r"\bignoriere (?:alle )?(?:vorherigen )?anweisungen\b", _I), None),
]


def _number_tokens(texts: list[str]) -> set[str]:
    tokens = set()
    for text in texts:
        for m in _PLAIN_NUMBER.finditer(text):
            tokens.add(f"{float(m.group(0).replace(',', '')):.2f}")
    return tokens


def unsupported_numbers(text: str, org_texts: list[str]) -> list[str]:
    """Figures and counts in a draft that appear nowhere in the organization's own facts.

    Money, percentages, and dates follow grounding_values(). Plain counts ("1,200
    students") must appear somewhere in org_texts, prose included. Funder text
    must never be passed as org_texts: it cannot vouch for facts about the applicant.
    """
    cleaned = _BRACKETED.sub(" ", text)
    found = unverified_figures(cleaned, grounding_values(org_texts))
    spans = cleaned
    for f in extract_figures(cleaned):
        spans = spans.replace(f.raw, " ")
    known = _number_tokens(org_texts)
    for m in _COUNT.finditer(spans):
        value = float(m.group(0).replace(",", ""))
        if value < 10:
            continue
        if f"{value:.2f}" not in known and m.group(0) not in found:
            found.append(m.group(0))
    return found


def unrecognized_names(text: str, known_texts: list[str]) -> list[str]:
    """Multi-word capitalized names (awards, partners, programs) that the known texts never mention."""
    haystack = " ".join(known_texts).lower()
    names: list[str] = []
    for m in _NAME.finditer(_BRACKETED.sub(" ", text)):
        words = m.group(0).split()
        while words and words[0] in _NAME_STARTERS:
            words = words[1:]
        if len(words) < 2:
            continue
        name = " ".join(words)
        if name.lower() not in haystack and name not in names:
            names.append(name)
    return names


def mark_for_verification(text: str, raw: str) -> str:
    """Wrap each whole occurrence of `raw` as [VERIFY: raw] so it cannot slip through unnoticed."""
    pattern = r"(?<!\[VERIFY: )(?<![\d,.$])" + re.escape(raw) + r"(?![\d,.]*\d)"
    return re.sub(pattern, f"[VERIFY: {raw}]", text)


def injection_signals(text: str) -> list[str]:
    """Snippets of text that look like instructions aimed at an AI model rather than at an applicant."""
    hits = []
    for pattern, label in _INJECTION:
        for m in pattern.finditer(text or ""):
            snippet = label or m.group(0).strip()
            if snippet and snippet not in hits:
                hits.append(snippet[:80])
    return hits


def as_data(value) -> str:
    """JSON with "</" escaped, so outside text cannot close the tag it is wrapped in."""
    return json.dumps(value, indent=1, default=str).replace("</", "<\\/")


# ---------------------------------------------------------------- output sanitization (all AI text, all external text)

# Domains whose links may stay clickable in AI output. Everything else becomes plain text.
ALLOWED_LINK_DOMAINS = ("grants.gov",)
REDACTED = "[REDACTED]"

_KEY_PATTERNS = [
    re.compile(r"\b(?:sk|pk|rk|ak)[-_][A-Za-z0-9_\-]{16,}"),                       # sk-..., pk-... style keys
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{12,}", re.IGNORECASE),                  # bearer tokens
    re.compile(r"\b[A-Z][A-Z0-9_]*(?:API_KEY|SECRET|TOKEN|PASSWORD)\s*[=:]\s*\S+"),  # NAME_API_KEY=value
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),  # JWTs
    re.compile(r"\$argon2id?\$[^\s\"']+"),                                          # password hashes
]
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_BARE_URL = re.compile(r"\bhttps?://[^\s)\]>\"']+", re.IGNORECASE)
_HTML_TAG = re.compile(r"</?[a-zA-Z][a-zA-Z0-9\-]*(?:\s[^<>]*)?/?>")


def redact_secrets(text: str, secrets=()) -> tuple[str, int]:
    """Replace configured secret values and anything shaped like a key, token, or password hash."""
    count = 0
    for secret in secrets:
        if secret and len(secret) >= 8 and secret in text:
            count += text.count(secret)
            text = text.replace(secret, REDACTED)
    for pattern in _KEY_PATTERNS:
        text, n = pattern.subn(REDACTED, text)
        count += n
    return text, count


def _host_allowed(url: str, extra_domains) -> bool:
    from urllib.parse import urlparse

    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in (*ALLOWED_LINK_DOMAINS, *extra_domains) if d)


def neutralize_links(text: str, extra_domains=()) -> tuple[str, int, int]:
    """Remove markdown images and turn links to unknown sites into plain text. Returns (text, images, links)."""
    text, images = _MD_IMAGE.subn("[image removed]", text)
    links = 0

    def md_link(m):
        nonlocal links
        if _host_allowed(m.group(2), extra_domains):
            return m.group(0)
        links += 1
        return f"{m.group(1)} [link removed]"

    text = _MD_LINK.sub(md_link, text)

    def bare(m):
        nonlocal links
        if _host_allowed(m.group(0), extra_domains):
            return m.group(0)
        links += 1
        return "[link removed]"

    text = _BARE_URL.sub(bare, text)
    return text, images, links


_WORD = re.compile(r"[A-Za-z0-9']+")


def _shingles(text: str, size: int) -> set[tuple[str, ...]]:
    words = [w.lower() for w in _WORD.findall(text)]
    return {tuple(words[i:i + size]) for i in range(len(words) - size + 1)}


LEAK_RUN_WORDS = 12  # real prompt dumps run to dozens of words; short echoes of a rule are not leaks


def strip_instruction_leaks(text: str, protected_texts=(), size: int = LEAK_RUN_WORDS,
                            allowed_texts=()) -> tuple[str, int]:
    """Cut every run of 12+ consecutive words copied from GrantBridge's own instructions to the model.

    Works on word runs, not sentences, so abbreviations like "U.S." cannot split a copied passage
    into fragments too short to recognize. Wording the instructions tell the model to use
    (allowed_texts) is not a leak. Returns (text, number of runs removed).
    """
    protected = set()
    for p in protected_texts:
        protected |= _shingles(p, size)
    for a in allowed_texts:
        protected -= _shingles(a, size)
    if not protected or not text:
        return text, 0
    words = list(_WORD.finditer(text))
    lowered = [w.group(0).lower() for w in words]
    marked = [False] * len(words)
    for i in range(len(words) - size + 1):
        if tuple(lowered[i:i + size]) in protected:
            for j in range(i, i + size):
                marked[j] = True
    runs, i = [], 0
    while i < len(words):
        if marked[i]:
            j = i
            while j + 1 < len(words) and marked[j + 1]:
                j += 1
            runs.append((words[i].start(), words[j].end()))
            i = j + 1
        else:
            i += 1
    for start, end in reversed(runs):
        text = text[:start] + "[removed: internal instructions]" + text[end:]
    return text.strip(), len(runs)


def internal_instructions() -> tuple[str, ...]:
    """Every instruction text GrantBridge sends to the model. A leak of any of them is cut from any output.

    Imported lazily so this module stays free of import cycles.
    """
    from grantbridge import (advisor, award_feasibility, budget, drafting, fit_explainer, mission_drift,
                             outline, proposal_review, pursuit, solicitation)

    return (advisor.INSTRUCTIONS, fit_explainer.INSTRUCTIONS, drafting.FACTS_INSTRUCTIONS,
            drafting.DRAFT_INSTRUCTIONS, drafting.REVIEW_INSTRUCTIONS, drafting.REVISE_INSTRUCTIONS,
            proposal_review.INSTRUCTIONS, budget.INSTRUCTIONS, pursuit.INSTRUCTIONS, mission_drift.INSTRUCTIONS,
            award_feasibility.INSTRUCTIONS, award_feasibility.EXPLAIN_INSTRUCTIONS, solicitation.INSTRUCTIONS,
            outline.INSTRUCTIONS)


def instruction_echoes() -> tuple[str, ...]:
    """Wording GrantBridge's instructions tell the model to use, which may appear in answers."""
    from grantbridge import award_feasibility, fit_explainer

    return fit_explainer.ECHO_PHRASES + award_feasibility.ECHO_PHRASES


def leaks_instructions(text: str) -> bool:
    """True if `text` copies 12+ consecutive words of any internal instructions (the guard's own test)."""
    return strip_instruction_leaks(text, internal_instructions(), allowed_texts=instruction_echoes())[1] > 0


def sanitize_output(text: str, *, secrets=(), extra_domains=(), protected_texts=None) -> tuple[str, dict]:
    """Clean AI-written text before it is shown or stored: secrets, images, unknown links, HTML, prompt leaks.

    protected_texts defaults to all of GrantBridge's internal instructions.
    """
    allowed = ()
    if protected_texts is None:
        protected_texts, allowed = internal_instructions(), instruction_echoes()
    text = text or ""
    text, secrets_redacted = redact_secrets(text, secrets)
    text, images, links = neutralize_links(text, extra_domains)
    text, html = _HTML_TAG.subn("", text)
    text, leaks = strip_instruction_leaks(text, protected_texts, allowed_texts=allowed)
    stats = {"secrets_redacted": secrets_redacted, "images_removed": images, "links_removed": links,
             "html_removed": html, "instruction_leaks": leaks}
    return text, stats


def sanitize_external(text: str) -> str:
    """Text from outside sources (grant listings, pasted funder text) made safe to render as markdown."""
    text, _, _ = neutralize_links(text or "")
    return _HTML_TAG.sub("", text)


def redact_for_logs(text: str, secrets=()) -> str:
    """Logs never carry secrets or email addresses."""
    text, _ = redact_secrets(text or "", secrets)
    return _EMAIL.sub("[email]", text)


def merge_stats(total: dict, more: dict) -> dict:
    for key, value in more.items():
        total[key] = total.get(key, 0) + value
    return total


# ---------------------------------------------------------------- data minimization (text sent to the model)

_PHONE = re.compile(r"(?<![\w-])(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}(?![\w-])")


def redact_contact_details(text: str) -> str:
    """Email addresses and U.S.-style phone numbers become [email] and [phone] before text goes to the model."""
    return _PHONE.sub("[phone]", _EMAIL.sub("[email]", text or ""))
