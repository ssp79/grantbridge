"""Find Grants page end to end: sample mode, live mode, failures, details, and AI explanations."""

from types import SimpleNamespace

import httpx
import pytest

from grantbridge import auth, demo, fit_explainer as fx, grants_gov, llm, trace
from tests.conftest import envelope, fake_client, hit, load_fixture, search_data
from tests.test_pages import PASSWORD, fresh_app, log_in, page_text


@pytest.fixture
def at():
    user = auth.sign_up("alice@example.org", PASSWORD, "Alice Org")
    demo.load_demo_data(user.id)
    app = log_in(fresh_app(), "alice@example.org", PASSWORD)
    app.switch_page("app_pages/find_grants.py").run()
    assert app.title[0].value == "Find Grants"
    return app


@pytest.fixture
def samples(at):
    """The page opens on real federal grants, so the sample tests choose samples for themselves."""
    at.segmented_control(key="search_source").set_value("sample").run()
    return at


def use_samples(app):
    app.segmented_control(key="search_source").set_value("sample").run()
    return app


def use_grants_gov(monkeypatch, handler):
    monkeypatch.setattr(grants_gov, "_default_client", fake_client(handler))


def search_live(at):
    at.segmented_control(key="search_source").set_value("grants.gov").run()
    next(b for b in at.button if b.label == "Search").click().run()
    return at


def text(at) -> str:
    return page_text(at) + "\n".join(str(e.value) for e in (*at.error, *at.success))


def test_sample_mode_runs_when_chosen_with_labels_and_trace(samples):
    at = samples
    assert not at.exception
    body = text(at)
    assert "SAMPLE / NOT LIVE" in body
    assert "10 sample grant(s) match" in body
    assert "**Source:** none (sample grant)" in body
    assert len(at.dataframe) == 2  # last-search steps and recent activity
    steps = at.dataframe[0].value
    assert list(steps["Step"]) == ["build_query_from_profile", "search_sample_grants", "rank_results"]


def test_results_refresh_after_the_profile_changes():
    """Regression: results computed before Load demo data kept their empty-profile checks."""
    user = auth.sign_up("bob@example.org", PASSWORD, "Bob Org")
    app = log_in(fresh_app(), "bob@example.org", PASSWORD)
    app.switch_page("app_pages/find_grants.py").run()
    use_samples(app)
    assert "your profile does not say yours" in text(app)       # empty profile: unknown checks
    demo.load_demo_data(user.id)
    app.switch_page("app_pages/find_grants.py").run()
    use_samples(app)
    body = text(app)
    assert "your profile does not say yours" not in body
    assert "You reported IRS-recognized 501(c)(3) status" in body


def test_sample_no_results(samples):
    at = samples
    keyword = next(t for t in at.text_input if t.label == "Keyword (optional)")
    keyword.input("zzqxjv")
    next(b for b in at.button if b.label == "Search").click().run()
    assert "No grants match these filters" in text(at)


def test_live_mode_shows_source_timestamp_and_attribution(at, monkeypatch):
    use_grants_gov(monkeypatch, lambda r: httpx.Response(200, json=envelope(search_data([hit("361822", "Literacy Partnerships")]))))
    search_live(at)
    assert not at.exception
    body = text(at)
    assert grants_gov.ATTRIBUTION in body
    assert "Live results from Grants.gov" in body
    assert "[Grants.gov page](https://www.grants.gov/search-results-detail/361822)" in body
    assert "Oct 20, 2026 19:51 UTC" in body
    assert "Posted on Grants.gov" in body
    assert "SAMPLE / NOT LIVE." not in body


def test_live_mode_bad_network_shows_friendly_error(at, monkeypatch):
    def down(request):
        raise httpx.ConnectError("no route")

    use_grants_gov(monkeypatch, down)
    search_live(at)
    assert not at.exception
    assert any("Grants.gov is not responding" in e.value for e in at.error)


def test_live_mode_malformed_response_shows_friendly_error(at, monkeypatch):
    use_grants_gov(monkeypatch, lambda r: httpx.Response(200, text="<html>oops</html>"))
    search_live(at)
    assert any("could not read" in e.value for e in at.error)


def test_live_mode_no_results(at, monkeypatch):
    use_grants_gov(monkeypatch, lambda r: httpx.Response(200, json=envelope(search_data([]))))
    search_live(at)
    assert "No grants match these filters" in text(at)


def test_live_load_details_updates_the_card(at, monkeypatch):
    def handler(request):
        if request.url.path.endswith("/search2"):
            return httpx.Response(200, json=envelope(search_data([hit("361822", "Home Study Services")])))
        return httpx.Response(200, json=load_fixture("grants_gov_fetch_synopsis_361822.json"))

    use_grants_gov(monkeypatch, handler)
    search_live(at)
    next(b for b in at.button if b.label == "Load details").click().run()
    assert not at.exception
    body = text(at)
    assert "\\$1,000,000 – \\$100,000,000" in body
    assert "below the \\$1,000,000 minimum award" in body


def test_explain_fit_button_shows_explanation_with_uncertainty(samples, monkeypatch):
    at = samples
    parsed = fx.FitExplanation(
        verdict="possible fit", confidence="high", summary="Partly matches; grade levels need checking.",
        reasons=[fx.Reason(point="Serves Connecticut students.", based_on="profile")],
        uncertainties=["Grades served may differ."], verify_next=["Read the notice."],
    )
    usage = SimpleNamespace(input_tokens=1200, output_tokens=300,
                            input_tokens_details=SimpleNamespace(cached_tokens=0),
                            output_tokens_details=SimpleNamespace(reasoning_tokens=100))
    fake = SimpleNamespace(responses=SimpleNamespace(parse=lambda **kw: SimpleNamespace(output_parsed=parsed, usage=usage)))
    monkeypatch.setattr(llm, "get_client", lambda: (fake, "gpt-6-luna"))
    next(b for b in at.button if b.label == "Explain fit (AI)").click().run()
    assert not at.exception
    body = text(at)
    assert "**AI fit explanation:** possible fit · confidence medium" in body  # capped from "high"
    assert "Grades served may differ." in body
    assert "AI can be wrong" in body
    runs = trace.list_runs(1)
    assert runs[0]["kind"] == "explain_fit" and runs[0]["input_tokens"] == 1200


def test_saved_grants_list_shows_samples_and_live_snapshots(at, monkeypatch):
    from grantbridge import advisor_tools, repo
    user_id = 1
    ctx = advisor_tools.ToolContext(user_id=user_id, user_message="save this one",
                                    gg_client=fake_client(lambda r: httpx.Response(
                                        200, json=load_fixture("grants_gov_fetch_synopsis_361822.json"))))
    assert advisor_tools.call_tool(ctx, "save_grant", {"grant_id": "361822"}).output["saved"]
    at.switch_page("app_pages/saved_grants.py").run()
    body = text(at)
    assert at.title[0].value == "Saved Grants"
    assert "Saved copy from Grants.gov, 2026-10-20 19:51 UTC" in body
    assert "SAMPLE / NOT LIVE" in body  # demo data saved sample-01 and sample-05
    assert len(repo.list_saved_grants(user_id)) == 3


def test_two_dollar_amounts_in_one_line_are_not_rendered_as_math(samples):
    at = samples
    """Regression: "Your $25,000 request is above the $15,000 maximum" rendered as a math formula."""
    lines = [str(m.value) for m in at.markdown if "maximum award" in str(m.value)]
    assert any(r"\$25,000 request is above the \$15,000 maximum award" in line for line in lines)
    # Every dollar sign in these lines is escaped, so Markdown cannot pair two of them into a formula.
    assert all(line.count("$") == line.count(r"\$") for line in lines)


def test_the_page_opens_on_real_federal_grants_and_sends_nothing_until_you_search(at):
    """Real funding is the default; the samples are for learning the tool.

    Opening the page must not call Grants.gov: a search only happens when the user presses Search.
    """
    assert at.segmented_control(key="search_source").value == "grants.gov"
    assert at.segmented_control(key="search_source").options[0] == "Real federal grants (Grants.gov)"
    assert "Nothing is sent until you do" in text(at)
