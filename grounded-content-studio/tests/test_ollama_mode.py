import json

import httpx
import pytest
import respx

from app import llm, main, validation
from app.config import get_settings
from app.errors import LLMUnavailableError
from app.research import Page

CHAT = "http://localhost:11434/api/chat"
TAGS = "http://localhost:11434/api/tags"
GOOD = {"title": "t", "summary": "s", "introduction": "i",
        "sections": [{"heading": "h", "body": "b"}], "conclusion": "c", "suggested_cta": None}
PAGES = [Page("T", "https://site.test/a", "word " * 6000, 1.0)]


def provider(monkeypatch, name):
    monkeypatch.setenv("LLM_PROVIDER", name)
    get_settings.cache_clear()


def ollama_ok(payload=GOOD):
    return httpx.Response(200, json={"done_reason": "stop", "message": {"content": json.dumps(payload)}})


def no_claude(monkeypatch):
    def boom():
        raise AssertionError("Claude must not be called")

    monkeypatch.setattr(llm, "_get_client", boom)
    monkeypatch.setattr(validation, "_get_client", boom)


async def generate(length="detailed"):
    return await llm.generate_grounded_content("q", "article", "warm", length, PAGES)


# --- generation ---------------------------------------------------------------

@respx.mock
async def test_ollama_mode_skips_claude_and_is_not_a_fallback(monkeypatch):
    provider(monkeypatch, "ollama")
    no_claude(monkeypatch)
    respx.post(CHAT).mock(return_value=ollama_ok())

    result = await generate()

    assert (result.provider, result.fallback_reason) == ("ollama", None)


@respx.mock
async def test_anthropic_mode_never_falls_back(monkeypatch):
    provider(monkeypatch, "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    get_settings.cache_clear()
    route = respx.post(CHAT).mock(return_value=ollama_ok())

    with pytest.raises(LLMUnavailableError) as info:
        await generate()

    assert info.value.reasons == {"anthropic": "not_configured"} and not route.called


@respx.mock
async def test_missing_ollama_model_gets_its_own_reason(monkeypatch):
    provider(monkeypatch, "ollama")
    respx.post(CHAT).mock(return_value=httpx.Response(404, json={"error": "model not found"}))

    with pytest.raises(LLMUnavailableError) as info:
        await generate()

    assert info.value.reasons == {"ollama": "model_not_found"}


@respx.mock
async def test_missing_model_also_reported_when_used_as_fallback(monkeypatch):
    monkeypatch.setattr(llm, "_get_client", lambda: (_ for _ in ()).throw(RuntimeError("not configured")))
    respx.post(CHAT).mock(return_value=httpx.Response(404))

    with pytest.raises(LLMUnavailableError) as info:
        await generate()

    assert info.value.reasons == {"anthropic": "not_configured", "ollama": "model_not_found"}


# --- context sizing -----------------------------------------------------------

@respx.mock
async def test_context_grows_to_fit_the_prompt_and_research_is_trimmed(monkeypatch):
    provider(monkeypatch, "ollama")
    route = respx.post(CHAT).mock(return_value=ollama_ok())

    await generate("detailed")

    body = json.loads(route.calls[0].request.content)
    system, user = (m["content"] for m in body["messages"])
    options = body["options"]
    assert len(user) < 13000  # 6000-word page trimmed to OLLAMA_MAX_RESEARCH_CHARS plus framing
    assert options["num_ctx"] > 8192 and options["num_ctx"] <= 16384
    assert options["num_ctx"] % 1024 == 0
    assert (len(system) + len(user)) // 3 + options["num_predict"] < options["num_ctx"]


def test_context_never_exceeds_the_cap_and_warns(monkeypatch, caplog):
    monkeypatch.setenv("OLLAMA_MAX_CTX", "4096")
    get_settings.cache_clear()
    options = llm.ollama_options("s" * 3000, "u" * 30000, 2000, 0.1)
    assert options["num_ctx"] == 4096
    assert "capped" in caplog.text


def test_small_prompts_keep_the_configured_minimum():
    assert llm.ollama_options("a", "b", 100, 0)["num_ctx"] == 8192


# --- validators ---------------------------------------------------------------

@respx.mock
async def test_validators_use_only_ollama_in_ollama_mode(monkeypatch):
    provider(monkeypatch, "ollama")
    no_claude(monkeypatch)
    verdict = {"status": "REVIEW_REQUIRED", "summary": "s", "issues": []}
    route = respx.post(CHAT).mock(return_value=ollama_ok(verdict))

    result = await validation.validate_brand_content("q", {"a": 1}, PAGES)

    assert (result["provider"], result["fallback_reason"]) == ("ollama", None)
    evidence = json.loads(route.calls[0].request.content)["messages"][1]["content"]
    assert len(evidence) < 20000  # evidence trimmed for the local model


@respx.mock
async def test_validator_reports_missing_model(monkeypatch):
    provider(monkeypatch, "ollama")
    respx.post(CHAT).mock(return_value=httpx.Response(404))
    with pytest.raises(llm.LLMOutputError) as info:
        await validation.validate_brand_content("q", {}, PAGES)
    assert info.value.reason == "model_not_found"


# --- health ---------------------------------------------------------------------

async def health():
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        return (await client.get("/health")).json()


@respx.mock
async def test_health_reports_installed_model(monkeypatch):
    provider(monkeypatch, "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "mistral:7b")
    get_settings.cache_clear()
    respx.get(TAGS).mock(return_value=httpx.Response(200, json={"models": [{"name": "mistral:7b"}]}))
    body = await health()
    assert body["llm_provider"] == "ollama"
    assert body["ollama"] == {"reachable": True, "model": "mistral:7b", "model_installed": True}


@respx.mock
async def test_health_flags_a_model_that_is_not_pulled(monkeypatch):
    respx.get(TAGS).mock(return_value=httpx.Response(200, json={"models": [{"name": "llama3:8b"}]}))
    assert (await health())["ollama"]["model_installed"] is False


@respx.mock
async def test_health_handles_ollama_not_running_and_untagged_names(monkeypatch):
    respx.get(TAGS).mock(side_effect=httpx.ConnectError("down"))
    assert (await health())["ollama"] == {"reachable": False, "model": "qwen2.5:7b", "model_installed": None}
    assert main._model_installed("mistral", ["mistral:latest"]) is True
    assert main._model_installed("mistral:7b", ["mistral:latest"]) is False


async def test_health_skips_ollama_in_anthropic_mode(monkeypatch):
    provider(monkeypatch, "anthropic")
    assert (await health())["ollama"] is None
