import shutil

import pytest

from app import company, llm, research, security
from app.config import get_settings


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    # Tests see only the sample company's profile, not the sample brand guidelines shipped next to it,
    # so "no guidelines supplied" is the default state and each test opts in to guidelines explicitly.
    folder = tmp_path / "companies" / "example_company"
    folder.mkdir(parents=True)
    shutil.copy(company.ROOT / "companies" / "example_company" / "profile.json", folder / "profile.json")
    monkeypatch.setattr(company, "COMPANIES_DIR", tmp_path / "companies")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("WEBSITE_BASE_URL", "https://site.test/")
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    monkeypatch.setenv("HUMANIZE_ENABLED", "false")
    monkeypatch.setenv("API_KEYS", "")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "0")
    security.reset_rate_limits()
    get_settings.cache_clear()
    research.clear_caches()
    llm._client = None
    yield
    get_settings.cache_clear()
    research.clear_caches()
