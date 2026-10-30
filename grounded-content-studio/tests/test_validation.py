import json
from types import SimpleNamespace

import httpx
import pytest
import respx

from app import main, validation
from app.research import Page

URL = "https://site.test/a"
PAGES = [Page("T", URL, "The company installs battery backup systems for homes. " * 6, 1.0)]
OLLAMA = "http://localhost:11434/api/chat"


def brand(*issues, status="PASS"):
    return {"status": status, "summary": "s", "issues": list(issues)}


def issue(severity="LOW", action="KEEP", category="TONE"):
    return {"text": "t", "severity": severity, "recommended_action": action, "category": category}


# --- code-level brand checks ---------------------------------------------------

def test_brand_without_guidelines_cannot_pass():
    result = validation.enforce_brand_checks(brand(), guidelines_supplied=False)
    assert result["status"] == "REVIEW_REQUIRED" and result["model_status"] == "PASS" and result["status_overridden"]


def test_brand_with_guidelines_and_no_issues_passes():
    result = validation.enforce_brand_checks(brand(), guidelines_supplied=True)
    assert result["status"] == "PASS" and "code_checks" not in result


def test_brand_high_severity_and_promises_fail():
    assert validation.enforce_brand_checks(brand(issue("HIGH", "REWRITE")), True)["status"] == "FAIL"
    assert validation.enforce_brand_checks(brand(issue("LOW", "KEEP", "MISLEADING_PROMISE")), True)["status"] == "FAIL"


def test_a_medium_issue_or_a_rewrite_downgrades_a_pass():
    assert validation.enforce_brand_checks(brand(issue("MEDIUM", "KEEP")), True)["status"] == "REVIEW_REQUIRED"
    assert validation.enforce_brand_checks(brand(issue("LOW", "REWRITE")), True)["status"] == "REVIEW_REQUIRED"


def test_a_malformed_issue_list_is_never_trusted():
    assert validation.enforce_brand_checks({"status": "PASS", "issues": "none"}, True)["status"] == "REVIEW_REQUIRED"
    assert validation.enforce_brand_checks({"status": "PASS", "issues": ["x"]}, True)["status"] == "REVIEW_REQUIRED"


def test_checks_never_lower_a_fail():
    assert validation.enforce_brand_checks(brand(status="FAIL"), True)["status"] == "FAIL"


def test_load_brand_guidelines(tmp_path, monkeypatch):
    monkeypatch.setattr("app.prompts.PROMPT_DIR", tmp_path)
    assert validation.load_brand_guidelines() == ""
    (tmp_path / "brand_guidelines.md").write_text("  Be warm.  ")
    assert validation.load_brand_guidelines() == "Be warm."


# --- provider routing ------------------------------------------------------------

def claude_returns(data, stop="tool_use"):
    async def create(**kwargs):
        create.kwargs = kwargs
        return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="tool_use", input=data)])
    return SimpleNamespace(messages=SimpleNamespace(create=create))


async def test_claude_is_used_first(monkeypatch):
    client = claude_returns(brand())
    monkeypatch.setattr(validation, "_get_client", lambda: client)

    result = await validation.validate_brand_content("q", {"a": 1}, PAGES, brand_guidelines="Be warm.")

    assert (result["provider"], result["fallback_reason"], result["status"]) == ("anthropic", None, "PASS")
    assert client.messages.create.kwargs["tool_choice"]["name"] == "submit_validation"


@respx.mock
async def test_falls_back_to_ollama_on_invalid_status(monkeypatch):
    monkeypatch.setattr(validation, "_get_client", lambda: claude_returns({"status": "MAYBE", "summary": "x"}))
    respx.post(OLLAMA).mock(return_value=httpx.Response(200, json={
        "done_reason": "stop", "message": {"content": json.dumps(brand())}}))

    result = await validation.validate_brand_content("q", {}, PAGES, brand_guidelines="Be warm.")

    assert (result["provider"], result["fallback_reason"]) == ("ollama", "bad_output")


@respx.mock
async def test_both_providers_down_raises(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    from app.config import get_settings
    get_settings.cache_clear()
    respx.post(OLLAMA).mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(httpx.ConnectError):
        await validation.validate_brand_content("q", {}, PAGES)


async def test_human_review_can_never_authorise_publication(monkeypatch):
    data = {"status": "PENDING_REVIEW", "summary": "s", "publication_authorised": True}
    monkeypatch.setattr(validation, "_get_client", lambda: claude_returns(data))

    result = await validation.prepare_human_review("q", {}, {"status": "PASS", "validation_error": False}, [])

    assert result["publication_authorised"] is False


async def test_blocked_review_lists_code_check_reasons():
    result = await validation.prepare_human_review(
        "q", {}, {"status": "REVIEW_REQUIRED", "summary": "b", "code_checks": ["No approved brand guidelines were supplied."]}, [])
    assert result["status"] == "BLOCKED" and result["brand_concerns"] == ["b", "No approved brand guidelines were supplied."]
    assert result["publication_authorised"] is False


async def test_blocked_review_does_not_report_a_pass_as_a_concern():
    brand_result = {"status": "REVIEW_REQUIRED", "summary": "No issues.", "status_overridden": True,
                    "model_status": "PASS", "code_checks": ["No approved brand guidelines were supplied."]}
    result = await validation.prepare_human_review("q", {}, brand_result, [])
    assert result["brand_concerns"] == ["No approved brand guidelines were supplied."]


async def test_a_failed_validator_still_reports_its_summary():
    brand_result = {"status": "REVIEW_REQUIRED", "summary": "Brand validation could not be completed.", "validation_error": True}
    result = await validation.prepare_human_review("q", {}, brand_result, [])
    assert result["status"] == "BLOCKED" and result["brand_concerns"] == ["Brand validation could not be completed."]


async def test_blockers_block_even_when_the_validator_passed():
    result = await validation.prepare_human_review("q", {}, {"status": "PASS", "validation_error": False}, [], blockers=["Hook: wrong"])
    assert result["status"] == "BLOCKED" and result["conflicts"] == ["Self-check failed: Hook: wrong"]


# --- endpoint behaviour ----------------------------------------------------------

CONTENT = {"title": "t", "summary": "s", "introduction": "i",
           "sections": [{"heading": "h", "body": "b"}], "conclusion": "c", "suggested_cta": None}


@pytest.fixture
def agent(monkeypatch):
    from app.agent import AgentRun
    from app.llm import LLMResult

    async def run(**kw):
        return AgentRun(LLMResult(CONTENT, "anthropic", "m"), PAGES, False, 1, 1)

    monkeypatch.setattr(main, "run_content_agent", run)


async def post(body):
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        return await client.post("/api/v1/content/generate", json=body)


async def test_a_passing_validator_leads_to_a_review_that_is_pending_not_approved(monkeypatch, agent):
    async def ok(**kw):
        return {"status": "PASS", "validation_error": False}

    async def review(brand_result, **kw):
        return {"status": "PENDING_REVIEW" if brand_result["status"] == "PASS" else "BLOCKED"}

    monkeypatch.setattr(main, "validate_brand_content", ok)
    monkeypatch.setattr(main, "prepare_human_review", review)
    body = (await post({"query": "explain battery backup"})).json()
    assert body["publication_status"] == "PENDING_REVIEW" and body["human_review"]["publication_authorised"] is False
    assert [k for k in body if k.endswith("_validation")] == ["brand_validation"]  # one validator


async def test_validator_crash_blocks_publication(monkeypatch, agent):
    async def boom(**kw):
        raise RuntimeError("down")

    monkeypatch.setattr(main, "validate_brand_content", boom)
    monkeypatch.setattr(main, "prepare_human_review", validation.prepare_human_review)  # the real fail-closed gate

    body = (await post({"query": "explain battery backup"})).json()
    assert body["publication_status"] == "BLOCKED"
    assert body["brand_validation"]["validation_error"] is True


async def test_validate_content_false_skips_validators(monkeypatch, agent):
    async def forbidden(**kw):
        raise AssertionError("validators must not run")

    for name in ("validate_brand_content", "prepare_human_review"):
        monkeypatch.setattr(main, name, forbidden)

    body = (await post({"query": "explain battery backup", "validate_content": False})).json()
    assert body["publication_status"] == "NOT_READY"
    assert body["brand_validation"]["status"] == "NOT_RUN"
    assert body["human_review"]["publication_authorised"] is False


async def test_code_warnings_reach_the_reviewer(monkeypatch):
    from app.agent import AgentRun
    from app.llm import LLMResult
    seen = {}

    async def run(**kw):
        return AgentRun(LLMResult(CONTENT, "anthropic", "m"), PAGES, False, 1, 1, format_warnings=['Contains a statistic ("60%") that is not in the website research.'])

    async def ok(**kw):
        return {"status": "PASS", "validation_error": False}

    async def review(**kw):
        seen.update(kw)
        return {"status": "PENDING_REVIEW"}

    monkeypatch.setattr(main, "run_content_agent", run)
    monkeypatch.setattr(main, "validate_brand_content", ok)
    monkeypatch.setattr(main, "prepare_human_review", review)
    await post({"query": "explain battery backup"})
    assert seen["self_check_items"] == ['Contains a statistic ("60%") that is not in the website research.']
