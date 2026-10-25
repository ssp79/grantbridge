"""Input validation shared by the auth layer, the repository, and the pages.

Validators return a cleaned value or raise ValidationError with a message that
is safe to show the user.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

# NIST SP 800-63B asks for 8 or more and no composition rules; 10 keeps a margin over that without the
# friction a nonprofit tester reported at 12. Length is the only rule: no forced symbols or digits, which push
# people towards "Password1!" and a sticky note. Everything else that protects an account is unchanged —
# Argon2id hashing, lockout after five failures, and session expiry.
PASSWORD_MIN = 10
PASSWORD_MAX = 128  # caps hashing cost for absurdly long inputs

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "PR": "Puerto Rico", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}

FOCUS_AREAS = [
    "Arts & culture", "Education", "Environment", "Food security", "Health",
    "Housing", "Workforce development", "Youth", "Seniors", "Immigrant services",
    "Disability services", "Community development",
]

# Self-reported by the user; GrantBridge does not verify tax status with the IRS.
TAX_STATUSES = [
    "Yes, IRS-recognized 501(c)(3)",
    "Fiscally sponsored by a 501(c)(3)",
    "Application pending with the IRS",
    "No",
]

APPLICATION_STATUSES = ["Researching", "Drafting", "Submitted", "Awarded", "Declined"]

BUDGET_CATEGORIES = [
    "Personnel", "Fringe benefits", "Contractors and consultants", "Travel", "Equipment", "Supplies and materials",
    "Training", "Rent and facilities", "Evaluation", "Indirect costs", "Other",
]
# Who pays for a budget line, and whether that money is certain. Only the user can say a match is committed.
FUNDING_SOURCES = {
    "grant": "This grant (requested)",
    "cash_committed": "Cash match: committed",
    "cash_pending": "Cash match: pending",
    "inkind_committed": "In-kind contribution: committed",
    "inkind_pending": "In-kind contribution: pending",
    "other_committed": "Other funding: committed",
    "other_pending": "Other funding: pending",
}
MAX_BUDGET_QUANTITY = Decimal("1000000")
MAX_BUDGET_UNIT_COST = Decimal("10000000")
MAX_BUDGET_LINE_TOTAL = Decimal("100000000")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
_EIN_RE = re.compile(r"^\d{2}-\d{7}$")
_URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)


class ValidationError(ValueError):
    """A user-facing validation problem."""


def email(value: str) -> str:
    cleaned = (value or "").strip().lower()
    if len(cleaned) > 254 or not _EMAIL_RE.match(cleaned):
        raise ValidationError("Enter a valid email address.")
    return cleaned


def new_password(value: str, email_value: str = "") -> str:
    value = value or ""
    if len(value) < PASSWORD_MIN:
        raise ValidationError(f"Password must be at least {PASSWORD_MIN} characters.")
    if len(value) > PASSWORD_MAX:
        raise ValidationError(f"Password must be at most {PASSWORD_MAX} characters.")
    if len(set(value)) < 4:
        raise ValidationError("Password is too repetitive.")
    if email_value and value.strip().lower() == email_value.strip().lower():
        raise ValidationError("Password cannot be your email address.")
    return value


def text(value: str, field: str, max_len: int, required: bool = False) -> str:
    cleaned = (value or "").strip()
    if required and not cleaned:
        raise ValidationError(f"{field} is required.")
    if len(cleaned) > max_len:
        raise ValidationError(f"{field} must be {max_len} characters or fewer.")
    return cleaned


def ein(value: str) -> str:
    cleaned = (value or "").strip()
    if cleaned and not _EIN_RE.match(cleaned):
        raise ValidationError("EIN must look like 12-3456789 (or leave it blank).")
    return cleaned


def url(value: str) -> str:
    cleaned = (value or "").strip()
    if cleaned and (len(cleaned) > 300 or not _URL_RE.match(cleaned)):
        raise ValidationError("Website must start with http:// or https://.")
    return cleaned


def state(value: str) -> str:
    cleaned = (value or "").strip().upper()
    if cleaned and cleaned not in US_STATES:
        raise ValidationError("Choose a U.S. state.")
    return cleaned


def choice(value: str, options: list[str], field: str, allow_blank: bool = True) -> str:
    cleaned = (value or "").strip()
    if (cleaned or not allow_blank) and cleaned not in options:
        raise ValidationError(f"Choose a valid {field.lower()}.")
    return cleaned


def focus_areas(values: list[str]) -> list[str]:
    unknown = [v for v in values if v not in FOCUS_AREAS]
    if unknown:
        raise ValidationError("Choose focus areas from the list.")
    return list(dict.fromkeys(values))


def optional_int(value, field: str, lo: int, hi: int) -> int | None:
    if value in (None, ""):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be a whole number.") from None
    if not lo <= number <= hi:
        raise ValidationError(f"{field} must be between {lo:,} and {hi:,}.")
    return number


def decimal(value, field: str, *, places: int, lo: Decimal, hi: Decimal) -> Decimal:
    """An exact decimal with at most `places` decimal places, between lo and hi. Floats are read via str()."""
    if isinstance(value, bool) or value in (None, ""):
        raise ValidationError(f"{field} is required.")
    try:
        number = Decimal(str(value).strip().replace(",", "").lstrip("$"))
    except InvalidOperation:
        raise ValidationError(f"{field} must be a number.") from None
    if not number.is_finite():
        raise ValidationError(f"{field} must be a number.")
    if -number.as_tuple().exponent > places and number != number.quantize(Decimal(1).scaleb(-places)):
        raise ValidationError(f"{field} can have at most {places} decimal place(s).")
    if not lo <= number <= hi:
        raise ValidationError(f"{field} must be between {lo:,} and {hi:,}.")
    return number.quantize(Decimal(1).scaleb(-places)).normalize() if places else number


def budget_item(data: dict) -> dict:
    """A cleaned budget line: category, description, quantity × unit cost, who pays, and why it is needed."""
    quantity = decimal(data.get("quantity"), "Quantity", places=3, lo=Decimal("0.001"), hi=MAX_BUDGET_QUANTITY)
    unit_cost = decimal(data.get("unit_cost"), "Unit cost", places=2, lo=Decimal(0), hi=MAX_BUDGET_UNIT_COST)
    if quantity * unit_cost > MAX_BUDGET_LINE_TOTAL:
        raise ValidationError(f"A line can total at most ${MAX_BUDGET_LINE_TOTAL:,}.")
    source = (data.get("funding_source") or "").strip()
    if source not in FUNDING_SOURCES:
        raise ValidationError("Choose who pays for this line.")
    return {
        "category": choice(data.get("category"), BUDGET_CATEGORIES, "Category", allow_blank=False),
        "description": text(data.get("description"), "Description", 200, required=True),
        "quantity": format(quantity, "f"),
        "unit": text(data.get("unit"), "Unit", 30),
        "unit_cost_cents": int(unit_cost * 100),
        "funding_source": source,
        "source_name": text(data.get("source_name"), "Source name", 120),
        "justification": text(data.get("justification"), "Justification", 1000),
    }


def optional_date(value) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError:
        raise ValidationError("Dates must be YYYY-MM-DD.") from None
