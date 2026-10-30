import json
import os
import re
import shutil
import time

import httpx
import pytest

from app import company, prompts, selfcheck
from app.config import get_settings
from app.format_checks import check_risky_claims
from app.prompts import PROMPT_DIR
from tests.brief_fixture import make_brief, make_typed


@pytest.fixture
def companies(tmp_path, monkeypatch):
    """An empty companies/ folder for tests; the real example_company profile (without its sample guidelines) is copied in."""
    monkeypatch.setattr(company, "COMPANIES_DIR", tmp_path)
    shutil.copytree(company.ROOT / "companies" / "example_company", tmp_path / "example_company", ignore=shutil.ignore_patterns("prompts"))
    return tmp_path


def use(monkeypatch, name):
    monkeypatch.setenv("COMPANY", name)
    get_settings.cache_clear()


def write_profile(root, name="acme", **over):
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    data = {"name": "Acme Corp", "website_url": "https://www.acme.test/", **over}
    (folder / "profile.json").write_text(json.dumps(data), encoding="utf-8")
    return folder


# --- profiles -----------------------------------------------------------------------------------------------

def test_the_shipped_default_profile_is_valid():
    profile = company.load_profile("example_company")
    assert profile.name == "Example Co" and profile.website_url == "https://example.com/"
    assert [label for label, _ in profile.restricted_terms] == ["Acme Pro"] and profile.examples
    assert profile.public()["brand_check_label"] and "restricted_terms" not in profile.public()


def test_the_shipped_sample_guidelines_are_found_for_the_default_company(monkeypatch):
    monkeypatch.setattr(company, "COMPANIES_DIR", company.ROOT / "companies")
    get_settings.cache_clear()
    assert "Example Co brand guidelines" in prompts.load_brand_guidelines()


def test_the_website_comes_from_the_profile_unless_the_environment_overrides_it(companies, monkeypatch):
    write_profile(companies)
    monkeypatch.delenv("WEBSITE_BASE_URL", raising=False)
    use(monkeypatch, "acme")
    assert get_settings().website_base_url == "https://www.acme.test/"
    monkeypatch.setenv("WEBSITE_BASE_URL", "https://override.test/")
    get_settings.cache_clear()
    assert get_settings().website_base_url == "https://override.test/"


@pytest.mark.parametrize("bad", ["../etc", "Upper", "a", "x/y", "with space", ""])
def test_a_company_id_cannot_escape_the_companies_folder(bad):
    with pytest.raises(company.ProfileError, match="not a valid folder name"):
        company.load_profile(bad)


def test_a_missing_or_broken_profile_gives_an_actionable_error(companies):
    with pytest.raises(company.ProfileError, match="python -m app.company new nope"):
        company.load_profile("nope")
    folder = companies / "broken"
    folder.mkdir()
    (folder / "profile.json").write_text("{ not json", encoding="utf-8")
    with pytest.raises(company.ProfileError, match="could not be read"):
        company.load_profile("broken")
    write_profile(companies, "nourl", website_url="ftp://x")
    with pytest.raises(company.ProfileError, match="website_url"):
        company.load_profile("nourl")


def test_restricted_terms_accept_plain_labels_and_reject_bad_patterns(companies):
    write_profile(companies, restricted_terms=["price lock", {"label": "Fare lock", "pattern": "fare[- ]lock"}])
    profile = company.load_profile("acme")
    assert [label for label, _ in profile.restricted_terms] == ["price lock", "Fare lock"]
    assert re.search(profile.restricted_terms[0][1], "A PRICE-lock!", re.I) and not re.search(profile.restricted_terms[0][1], "reprice locked", re.I)
    write_profile(companies, "badre", restricted_terms=[{"label": "x", "pattern": "("}])
    with pytest.raises(company.ProfileError, match="not a valid regular expression"):
        company.load_profile("badre")


def test_edits_to_a_profile_are_picked_up_without_a_restart(companies):
    folder = write_profile(companies)
    assert company.load_profile("acme").name == "Acme Corp"
    data = json.loads((folder / "profile.json").read_text())
    data["name"] = "Acme"
    (folder / "profile.json").write_text(json.dumps(data))
    os.utime(folder / "profile.json", (time.time() + 5, time.time() + 5))
    assert company.load_profile("acme").name == "Acme"


# --- prompts --------------------------------------------------------------------------------------------------

def test_the_default_company_uses_the_shared_prompts_with_its_name_filled_in():
    text = prompts.read_prompt("content_generation.txt")
    assert "Example Co (https://example.com/)" in text and "{{" not in text
    assert "{{company_name}}" in (PROMPT_DIR / "content_generation.txt").read_text(encoding="utf-8")


def test_placeholders_follow_the_active_company(companies, monkeypatch):
    folder = write_profile(companies, audience="shoppers", subject="Acme")
    (folder / "prompts").mkdir()
    (folder / "prompts" / "content_generation.txt").write_text("# Core\nVersion: 1.0\nWrite for {{audience}} about {{ subject }} at {{company_name}} ({{website_url}}). {{unknown}}", encoding="utf-8")
    use(monkeypatch, "acme")
    assert prompts.read_prompt("content_generation.txt") == "# Core\nVersion: 1.0\nWrite for shoppers about Acme at Acme Corp (https://www.acme.test/). {{unknown}}"


def test_another_company_uses_its_own_prompts_and_never_falls_back(companies, monkeypatch):
    folder = write_profile(companies)
    (folder / "prompts").mkdir()
    (folder / "prompts" / "content_generation.txt").write_text("# Acme core\nVersion: 1.0\nWrite for shoppers.", encoding="utf-8")
    use(monkeypatch, "acme")
    assert "shoppers" in prompts.read_prompt("content_generation.txt")
    with pytest.raises(RuntimeError, match="missing for this company"):
        prompts.read_prompt("content_website.txt")  # exists in the shared folder, but that is another business's


def test_brand_guidelines_are_per_company(companies, monkeypatch, tmp_path):
    folder = write_profile(companies)
    (folder / "prompts").mkdir()
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "brand_guidelines.md").write_text("Shared rules", encoding="utf-8")
    monkeypatch.setattr(prompts, "PROMPT_DIR", shared)
    use(monkeypatch, "example_company")
    assert prompts.load_brand_guidelines() == "Shared rules"   # the default company may use the shared folder
    use(monkeypatch, "acme")
    assert prompts.load_brand_guidelines() == ""                # another company never inherits it
    (folder / "prompts" / "brand_guidelines.md").write_text("Acme rules", encoding="utf-8")
    assert prompts.load_brand_guidelines() == "Acme rules"


# --- scaffold and check ---------------------------------------------------------------------------------------------

def test_scaffold_copies_every_prompt_and_refuses_to_overwrite(companies):
    target = company.scaffold("acme", "Acme Corp", "https://www.acme.test/")
    assert {p.name for p in (target / "prompts").glob("*.txt")} == {p.name for p in PROMPT_DIR.glob("*.txt")}
    assert company.load_profile("acme").website_url == "https://www.acme.test/"
    (target / "marker").write_text("keep")
    with pytest.raises(company.ProfileError, match="already exists"):
        company.scaffold("acme", "Other", "https://x.test/")
    assert (target / "marker").read_text() == "keep"
    for bad in ("Bad Id", "../x"):
        with pytest.raises(company.ProfileError):
            company.scaffold(bad, "n", "https://x.test/")
    with pytest.raises(company.ProfileError, match="http"):
        company.scaffold("ok_id", "n", "www.x.test")


def test_a_fresh_scaffold_needs_no_prompt_edits_to_run(companies, monkeypatch):
    """The shipped prompts use placeholders, so the new company's name and site are in them already."""
    company.scaffold("acme", "Acme Corp", "https://www.acme.test/")
    problems, warnings = company.check("acme")
    assert problems == []
    assert any("brand_guidelines.md" in w for w in warnings) and any("example topics" in w for w in warnings)
    use(monkeypatch, "acme")
    assert "Acme Corp (https://www.acme.test/)" in prompts.read_prompt("content_generation.txt")


def test_check_reports_missing_files_duplicate_versions_unknown_placeholders_and_unexplained_fields(companies):
    target = company.scaffold("acme", "Acme Corp", "https://www.acme.test/")
    (target / "prompts" / "human_review.txt").unlink()
    (target / "prompts" / "brand_validation.txt").write_text("# x\nVersion: 1\nVersion: 2\n{{nonsense}}", encoding="utf-8")
    video = target / "prompts" / "content_video.txt"
    video.write_text(video.read_text(encoding="utf-8").replace("closing_line", "ending"), encoding="utf-8")
    problems, _ = company.check("acme")
    joined = " | ".join(problems)
    assert "human_review.txt is missing" in joined and "exactly one 'Version:'" in joined and "closing_line" in joined and "{{nonsense}}" in joined


def test_check_warns_when_a_prompt_grows_past_the_local_model_limit(companies):
    target = company.scaffold("acme", "Acme Corp", "https://www.acme.test/")
    core = target / "prompts" / "content_generation.txt"
    core.write_text(core.read_text(encoding="utf-8") + "\n" + "Extra rule. " * 600, encoding="utf-8")
    _, warnings = company.check("acme")
    assert any("over 14000 characters" in w for w in warnings)


def test_the_command_line_creates_and_checks(companies, capsys):
    assert company.main(["new", "acme", "--name", "Acme Corp", "--url", "https://www.acme.test/"]) == 0
    assert "Created" in capsys.readouterr().out
    assert company.main(["new", "acme", "--name", "x", "--url", "https://x.test/"]) == 1
    assert company.main(["check", "acme"]) == 0
    assert company.main(["check", "nope"]) == 1


# --- behaviour that follows the profile -------------------------------------------------------------------------------

POST = {"title": "t", "summary": "s", "introduction": "i", "conclusion": "c"}


def content(body):
    return {**POST, "sections": [{"heading": "h", "body": body}]}


def test_a_company_can_list_its_own_claims_that_need_support(companies, monkeypatch):
    write_profile(companies, risky_terms=[{"label": "fastest", "pattern": r"\bfastest\b"}])
    use(monkeypatch, "acme")
    assert any("fastest" in m for m in check_risky_claims(content("Get the fastest pickup in town."), []))
    assert check_risky_claims(content("Get the fastest pickup in town."), ["the website says fastest pickup"]) == []
    use(monkeypatch, "example_company")  # the sample company flags the same word through its own list
    assert check_risky_claims(content("Get the fastest pickup in town."), []) != []


def test_unsupported_statements_about_the_company_use_its_own_name(companies, monkeypatch):
    write_profile(companies)
    use(monkeypatch, "acme")
    evidence = ["Customers book trips in the app and pay by card or cash."]
    text = "At Acme Corp drivers receive weekly bonuses based on complex regional leaderboards."
    assert check_risky_claims(content(text), evidence)
    use(monkeypatch, "example_company")
    assert not check_risky_claims(content(text), evidence)  # not this company's name, and no "we/our"


def test_restricted_brief_terms_come_from_the_profile(companies, monkeypatch):
    def brand_status(typed):
        return {c["id"]: c["status"] for c in selfcheck.deterministic_checks(make_brief(), typed)}["brand_restrictions"]

    typed = make_typed()
    typed["scenes"][1]["on_screen_text"] = "Acme Pro"
    use(monkeypatch, "example_company")
    assert brand_status(typed) == "FAIL"
    write_profile(companies, restricted_terms=["price lock"])
    use(monkeypatch, "acme")
    assert brand_status(typed) == "PASS"                      # another company's list does not apply
    typed["scenes"][1]["on_screen_text"] = "Free consultation"
    assert brand_status(typed) == "FAIL"                      # the universal list always does
    typed["scenes"][1]["on_screen_text"] = "Our price lock"
    assert brand_status(typed) == "FAIL"


async def test_health_reports_the_company_for_the_page(companies, monkeypatch):
    from app import main
    write_profile(companies, audience="shoppers", examples=["How do refunds work?"])
    use(monkeypatch, "acme")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://t") as client:
        body = (await client.get("/health")).json()
    assert body["company"]["name"] == "Acme Corp" and body["company"]["audience"] == "shoppers" and body["company"]["examples"] == ["How do refunds work?"]
    assert "restricted_terms" not in body["company"] and "reference" not in body
