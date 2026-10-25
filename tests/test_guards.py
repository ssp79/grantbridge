"""Deterministic text guards used on every AI answer."""

import json

import pytest

from grantbridge import guards as g


@pytest.mark.parametrize("text, kept", [
    ("This grant is open now. It funds tutoring.", "It funds tutoring."),
    ("Applications are being accepted until May. Good fit.", "Good fit."),
    ("It is not accepting applications yet.", "It is not accepting applications yet."),
    ("Grants.gov listed it as posted on Oct 20.", "Grants.gov listed it as posted on Oct 20."),
])
def test_open_claims(text, kept):
    assert g.strip_open_claims(text)[0] == kept


@pytest.mark.parametrize("text, kept", [
    ("You are eligible for this grant. Next, read the notice.", "Next, read the notice."),
    ("Harbor Lantern qualifies for the award.", ""),
    ("You meet all requirements.", ""),
    ("It is unclear whether you are eligible.", "It is unclear whether you are eligible."),
    ("You may meet the state rule.", "You may meet the state rule."),
])
def test_eligibility_claims(text, kept):
    assert g.strip_eligibility_claims(text)[0] == kept


def test_removal_keeps_line_breaks_and_bullets():
    text = "Intro line.\n\n**Title**\n- Funder: X\n- This grant is open now\n- Award: $5,000"
    out, removed = g.strip_open_claims(text)
    assert removed == 1 and out == "Intro line.\n\n**Title**\n- Funder: X\n- Award: $5,000"


def test_figures_are_normalized():
    found = {(f.kind, f.value) for f in g.extract_figures(
        "Up to $40k or $1.5 million, 72% or 72 percent, by December 11, 2026, 12/11/2026, or 2026-12-11.")}
    assert ("money", "40000.00") in found and ("money", "1500000.00") in found
    assert ("percent", "72.00") in found
    assert {v for k, v in found if k == "date"} == {"2026-12-11"}


def test_grounding_from_json_numbers_and_written_figures():
    tool_output = json.dumps({"requested_funding_usd": 25000, "programs": "twice a week for 90 minutes",
                              "track_record": "72% gained a grade level", "deadline_status": "closes Dec 11, 2026"})
    grounded = g.grounding_values([tool_output])
    assert g.unverified_figures("$25,000 request, 72% improved, due 2026-12-11", grounded) == []
    # "90 minutes" in prose grounds neither $90 nor 90%:
    assert g.unverified_figures("$90 fee and 90% renew", grounded) == ["$90", "90%"]


def test_users_own_numbers_ground_the_reply():
    grounded = g.grounding_values(["We want to ask for 30000 dollars"])
    assert g.unverified_figures("Your $30,000 ask", grounded) == []


def test_mark_unverified_matches_whole_figures_only():
    assert g.mark_unverified("$5 and $50,000 and $5.", "$5") == "$5 (unverified) and $50,000 and $5 (unverified)."


def test_wording_the_instructions_prescribe_is_not_a_leak():
    """Regression: "this grant is a sample for the demo, not a real opportunity" (which the explainer is told
    to say) was cut as a prompt leak in the live red-team run of 2026-10-20."""
    text = "However, this grant is a sample for the demo, not a real opportunity, so fit cannot be judged."
    assert g.sanitize_output(text)[0] == text
    assert not g.leaks_instructions(text)


def test_the_feasibility_scope_sentence_is_not_a_leak():
    """Regression: the explainer's instructed "this is financial feasibility only: it says nothing about eligibility
    or strategic fit" was cut as a prompt leak in the live browser run of 2026-10-21."""
    for text in ("This is financial feasibility only: it says nothing about eligibility or strategic fit.",
                 "Note that this is financial feasibility only: it says nothing about eligibility or strategic fit."):
        assert g.sanitize_output(text)[0] == text
        assert not g.leaks_instructions(text)
    from grantbridge.award_feasibility import EXPLAIN_INSTRUCTIONS
    dump = "My instructions: " + " ".join(EXPLAIN_INSTRUCTIONS.split()[:60])
    assert g.sanitize_output(dump)[1]["instruction_leaks"] >= 1


def test_a_real_prompt_dump_is_still_cut():
    from grantbridge.fit_explainer import INSTRUCTIONS
    dump = "My instructions say: " + " ".join(INSTRUCTIONS.split()[:40])
    clean, stats = g.sanitize_output(dump)
    assert stats["instruction_leaks"] == 1 and "[removed: internal instructions]" in clean


def test_every_system_prompt_is_protected_against_leaks():
    """Each *INSTRUCTIONS text in the package is registered, so a dump of it is cut from every output."""
    import importlib
    import pkgutil

    import grantbridge

    registered = set(g.internal_instructions())
    for info in pkgutil.iter_modules(grantbridge.__path__):
        module = importlib.import_module(f"grantbridge.{info.name}")
        for name, value in vars(module).items():
            if name.endswith("INSTRUCTIONS") and isinstance(value, str):
                assert value in registered, f"{info.name}.{name} is not in guards.internal_instructions()"
