"""The offline demo (pretend website + pretend model) drives the real application end to end."""
import threading

import httpx
import pytest

from app import company, main, research
from app.config import get_settings
from demo import llm, site
from tests.brief_fixture import make_brief


@pytest.fixture
def demo(monkeypatch):
    servers = [site.make_server(), llm.make_server()]
    for s in servers:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    monkeypatch.setattr(company, "COMPANIES_DIR", company.ROOT / "companies")  # use the shipped sample guidelines, as the demo does
    monkeypatch.setenv("WEBSITE_BASE_URL", f"http://127.0.0.1:{servers[0].server_address[1]}/")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", f"http://127.0.0.1:{servers[1].server_address[1]}")
    monkeypatch.setenv("OLLAMA_MODEL", "demo-model")
    monkeypatch.setenv("HUMANIZE_ENABLED", "true")
    get_settings.cache_clear()
    research.clear_caches()
    yield
    for s in servers:
        s.shutdown()


async def post(body):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://t", timeout=60) as client:
        return await client.post("/api/v1/content/generate", json=body)


@pytest.mark.parametrize("content_type, length", [("article", "standard"), ("article", "detailed"), ("faq", "concise"), ("social_post", "standard"), ("video_script", "standard"), ("blog", "concise"), ("general", "concise")])
async def test_every_format_runs_end_to_end_and_ends_in_human_review_not_approval(demo, content_type, length):
    response = await post({"query": "Explain how a home battery backup works", "content_type": content_type, "length": length})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sources"] and body["sources"][0]["url"].startswith("http://127.0.0.1")
    assert body["brand_validation"]["status"] == "PASS" and body["publication_status"] == "PENDING_REVIEW"
    assert body["human_review"]["publication_authorised"] is False and body["brief_report"] is None


async def test_the_demo_brief_script_passes_every_self_check(demo):
    brief = make_brief()
    response = await post({"query": "Battery video", "content_type": "video_script", "brief": brief.model_dump(mode="json")})
    assert response.status_code == 200, response.text
    report = response.json()["brief_report"]
    assert [c for c in report["checks"] if c["status"] != "PASS"] == [], report["checks"]
    assert report["overall"] == "PASS" and report["publication_authorised"] is False
    assert report["script_table"][0]["spoken line"] == brief.approved_hook and report["script_table"][-1]["spoken line"] == brief.approved_cta
    assert report["word_count"]["minimum"] <= report["word_count"]["actual"] <= report["word_count"]["maximum"]
