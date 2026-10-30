import httpx
import pytest

from app import main
from app.agent import AgentRun
from app.errors import LLMUnavailableError, ResearchError
from app.llm import LLMResult
from app.research import Page

CONTENT = {
    "title": "t", "summary": "s", "introduction": "i",
    "sections": [{"heading": "h", "body": "b"}], "conclusion": "c", "suggested_cta": None,
}
BODY = {"query": "explain battery backup systems", "length": "concise"}


async def post(body=BODY):
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        return await client.post("/api/v1/content/generate", json=body)


@pytest.fixture
def stub_validators(monkeypatch):
    async def ok(**kw):
        return {"status": "PASS", "validation_error": False}

    async def review(**kw):
        return {"status": "PENDING_REVIEW"}

    monkeypatch.setattr(main, "validate_brand_content", ok)
    monkeypatch.setattr(main, "prepare_human_review", review)


async def test_success_reports_timings_and_fallback(monkeypatch, stub_validators):
    async def agent(**kw):
        return AgentRun(
            LLMResult(CONTENT, "ollama", "m", fallback_reason="rate_limit"),
            [Page("T", "https://site.test/a", "x", 1.0)], False, 120, 900,
        )

    monkeypatch.setattr(main, "run_content_agent", agent)
    response = await post()
    meta = response.json()["metadata"]
    assert response.status_code == 200
    assert (meta["research_ms"], meta["generation_ms"], meta["fallback_reason"]) == (120, 900, "rate_limit")
    assert response.json()["publication_status"] == "PENDING_REVIEW"


@pytest.mark.parametrize("error,status", [
    (ResearchError("x"), 502),
    (LLMUnavailableError({"anthropic": "auth", "ollama": "connection"}), 503),
    (RuntimeError("x"), 502),
])
async def test_failures_map_to_distinct_statuses(monkeypatch, error, status):
    async def agent(**kw):
        raise error

    monkeypatch.setattr(main, "run_content_agent", agent)
    response = await post()
    assert response.status_code == status
    if status == 503:
        assert "auth" in response.json()["detail"]


async def test_format_warnings_and_repair_flag_are_returned_in_metadata(monkeypatch, stub_validators):
    async def agent(**kw):
        return AgentRun(LLMResult(CONTENT, "anthropic", "m"), [Page("T", "https://site.test/a", "x", 1.0)], False, 1, 1,
                        format_warnings=['Missing the "Caption" section.'], format_repaired=True)

    monkeypatch.setattr(main, "run_content_agent", agent)
    body = (await post({"query": "explain battery backup", "content_type": "social_post"})).json()
    assert body["metadata"]["format_warnings"] == ['Missing the "Caption" section.']
    assert body["metadata"]["format_repaired"] is True and body["content"]["reviewer_notes"] == []


async def test_each_risky_sentence_comes_back_as_its_own_wording_fix(monkeypatch, stub_validators):
    risky = {**CONTENT, "introduction": "Fine start.",
             "sections": [{"heading": "h", "body": "Book a free consultation today! It is guaranteed to work. Calm sentence."}]}

    async def agent(**kw):
        return AgentRun(LLMResult(risky, "anthropic", "m"), [Page("T", "https://site.test/a", "Plain page text.", 1.0)], False, 1, 1)

    monkeypatch.setattr(main, "run_content_agent", agent)
    fixes = (await post({"query": "explain battery backup"})).json()["wording_fixes"]
    assert [f["original_text"] for f in fixes] == ["Book a free consultation today!", "It is guaranteed to work."]
    assert fixes[0]["suggested_text"] == "Book a consultation today!" and fixes[1]["suggested_text"] == ""


async def test_humanize_choice_is_passed_on_and_the_original_draft_comes_back(monkeypatch, stub_validators):
    seen = {}
    original = {**CONTENT, "introduction": "The stiff first draft."}

    async def agent(**kw):
        seen.update(kw)
        return AgentRun(LLMResult(CONTENT, "anthropic", "m"), [Page("T", "https://site.test/a", "x", 1.0)], False, 1, 1,
                        original_content=original, humanized=True, humanize_note="Rewritten for natural flow.")

    monkeypatch.setattr(main, "run_content_agent", agent)
    body = (await post({"query": "explain battery backup", "humanize": False})).json()
    assert seen["humanize"] is False
    assert body["metadata"]["humanized"] is True and body["metadata"]["humanize_note"] == "Rewritten for natural flow."
    assert body["original_content"]["introduction"] == "The stiff first draft."

    assert (await post({"query": "explain battery backup"})).status_code == 200
    assert seen["humanize"] is True  # on by default


def test_health_reports_the_company_and_no_reference_pack():
    from fastapi.testclient import TestClient
    from app.main import app
    body = TestClient(app).get("/health").json()
    assert body["company"]["name"] == "Example Co" and body["status"] == "ok" and "reference" not in body
