import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from grantbridge import grants_gov, llm
from grantbridge.db import init_db

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 20, 19, 51, 37, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Every test gets its own empty SQLite file; the real data/grantbridge.db is never touched."""
    monkeypatch.setenv("GRANTBRIDGE_DB", str(tmp_path / "test.db"))
    init_db()
    return tmp_path / "test.db"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """No test may reach Grants.gov or the AI model unless it injects its own fake."""

    def refuse(request: httpx.Request):
        raise AssertionError(f"test tried to reach the network: {request.url}")

    monkeypatch.setattr(grants_gov, "_default_client", fake_client(refuse))

    def no_model():
        raise AssertionError("test tried to call the AI model")

    monkeypatch.setattr(llm, "get_client", no_model)


def fake_client(handler, **kwargs) -> grants_gov.GrantsGovClient:
    """A Grants.gov client with a fake transport, no throttling delay, and a fixed clock."""
    return grants_gov.GrantsGovClient(
        transport=httpx.MockTransport(handler), min_interval=0, sleep=lambda s: None, now=lambda: NOW, **kwargs
    )


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def envelope(data: dict) -> dict:
    return {"errorcode": 0, "msg": "Webservice Succeeds", "token": "x", "data": data}


def hit(opp_id: str, title: str, close: str = "12/11/2026", status: str = "posted", **extra) -> dict:
    return {"id": opp_id, "number": f"TEST-{opp_id}", "title": title, "agencyCode": "TEST",
            "agency": "Test Agency", "openDate": "06/05/2026", "closeDate": close, "oppStatus": status,
            "docType": "synopsis" if status == "posted" else "forecast", "cfdaList": ["93.000"], **extra}


def search_data(hits: list, hit_count: int | None = None) -> dict:
    return {"searchParams": {}, "hitCount": len(hits) if hit_count is None else hit_count, "startRecord": 0,
            "oppHits": hits, "oppStatusOptions": [], "dateRangeOptions": [], "suggestion": "",
            "eligibilities": [], "fundingCategories": [], "fundingInstruments": [], "agencies": [],
            "accessKey": "", "errorMsgs": []}
