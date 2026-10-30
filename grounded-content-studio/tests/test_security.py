import httpx
import pytest

from app import main, security
from app.agent import AgentRun
from app.config import get_settings
from app.llm import LLMResult
from app.research import Page

CONTENT = {"title": "t", "summary": "s", "introduction": "i",
           "sections": [{"heading": "h", "body": "b"}], "conclusion": "c", "suggested_cta": None}
BODY = {"query": "explain battery backup", "validate_content": False}


@pytest.fixture(autouse=True)
def agent(monkeypatch):
    async def run(**kw):
        return AgentRun(LLMResult(CONTENT, "anthropic", "m"), [Page("T", "https://site.test/a", "x", 1.0)], False, 1, 1)

    monkeypatch.setattr(main, "run_content_agent", run)


def configure(monkeypatch, keys="", limit="0"):
    monkeypatch.setenv("API_KEYS", keys)
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", limit)
    get_settings.cache_clear()


async def post(headers=None, path="/api/v1/content/generate"):
    transport = httpx.ASGITransport(app=main.app, client=("1.2.3.4", 5000))
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        if path == "/health":
            return await client.get(path)
        return await client.post(path, json=BODY, headers=headers or {})


async def test_auth_disabled_when_no_keys(monkeypatch):
    configure(monkeypatch)
    assert (await post()).status_code == 200


async def test_missing_and_wrong_keys_are_rejected(monkeypatch):
    configure(monkeypatch, keys="secret-one,secret-two")
    assert (await post()).status_code == 401
    assert (await post({"X-API-Key": "nope"})).status_code == 401
    assert (await post({"X-API-Key": ""})).status_code == 401


async def test_any_configured_key_is_accepted(monkeypatch):
    configure(monkeypatch, keys=" secret-one , secret-two ")
    assert (await post({"X-API-Key": "secret-one"})).status_code == 200
    assert (await post({"X-API-Key": "secret-two"})).status_code == 200


async def test_rate_limit_is_per_key_with_retry_after(monkeypatch):
    configure(monkeypatch, keys="a,b", limit="2")
    for _ in range(2):
        assert (await post({"X-API-Key": "a"})).status_code == 200
    blocked = await post({"X-API-Key": "a"})
    assert blocked.status_code == 429 and int(blocked.headers["Retry-After"]) >= 1
    assert (await post({"X-API-Key": "b"})).status_code == 200  # other keys unaffected


async def test_rate_limit_falls_back_to_ip_when_auth_off(monkeypatch):
    configure(monkeypatch, limit="1")
    assert (await post()).status_code == 200
    assert (await post()).status_code == 429


async def test_rejected_requests_do_not_consume_the_limit(monkeypatch):
    configure(monkeypatch, keys="a", limit="1")
    for _ in range(3):
        assert (await post({"X-API-Key": "bad"})).status_code == 401
    assert (await post({"X-API-Key": "a"})).status_code == 200


async def test_window_expires(monkeypatch):
    configure(monkeypatch, limit="1")
    clock = [1000.0]
    monkeypatch.setattr(security.time, "monotonic", lambda: clock[0])
    assert (await post()).status_code == 200
    assert (await post()).status_code == 429
    clock[0] += 61
    assert (await post()).status_code == 200


async def test_health_stays_open_and_reports_auth(monkeypatch):
    configure(monkeypatch, keys="a", limit="1")
    response = await post(path="/health")
    assert response.status_code == 200 and response.json()["auth_enabled"] is True
