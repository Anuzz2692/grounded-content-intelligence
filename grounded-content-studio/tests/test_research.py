import asyncio

import httpx
import pytest
import respx

from app import research
from app.errors import ResearchError

BODY = "Energy product information for customers. " * 12


def page(title: str, extra: str = "") -> httpx.Response:
    # The title is part of the body, so different pages have different text (identical text means a duplicate).
    html = f"<html><head><title>{title}</title></head><body><main>{BODY}{title}. {extra}</main></body></html>"
    return httpx.Response(200, html=html)


HOME = """<html><head><title>Home</title></head><body>
<a href="/battery-backup">Battery backup systems</a><a href="/installation">Installation</a><a href="/about">About us</a>
<a href="/logo.png">img</a><a href="https://other.test/x">ext</a>
<main>%s</main></body></html>""" % BODY


@respx.mock
async def test_relevant_page_ranks_first_and_assets_skipped():
    respx.get("https://site.test/").mock(return_value=httpx.Response(200, html=HOME))
    battery_page = respx.get("https://site.test/battery-backup").mock(return_value=page("Battery backup", "battery backup sizing guide"))
    respx.get("https://site.test/installation").mock(return_value=page("Installation"))
    respx.get("https://site.test/about").mock(return_value=page("About"))

    pages, cached = await research.research_website("explain battery backup systems")

    assert cached is False
    assert pages[0].url == "https://site.test/battery-backup"
    assert battery_page.called
    assert all("other.test" not in p.url and not p.url.endswith(".png") for p in pages)


@respx.mock
async def test_second_query_reuses_page_cache_and_query_cache():
    home = respx.get("https://site.test/").mock(return_value=httpx.Response(200, html=HOME))
    install = respx.get("https://site.test/installation").mock(return_value=page("Installation"))
    respx.get("https://site.test/battery-backup").mock(return_value=page("Battery backup"))
    respx.get("https://site.test/about").mock(return_value=page("About"))

    await research.research_website("installation cost")
    _, cached = await research.research_website("installation cost")
    assert cached is True

    await research.research_website("something different about installation")
    assert home.call_count == 1  # site index cached
    assert install.call_count == 1  # pages cached across queries


@respx.mock
async def test_cached_pages_are_copies():
    respx.get("https://site.test/").mock(return_value=httpx.Response(200, html=HOME))
    respx.get(url__regex=r"https://site.test/.+").mock(return_value=page("X"))

    first, _ = await research.research_website("installation")
    first[0].text = "mutated"
    second, cached = await research.research_website("installation")
    assert cached and second[0].text != "mutated"


@respx.mock
async def test_slow_fetch_is_abandoned_and_not_query_cached(monkeypatch):
    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "0.3")
    from app.config import get_settings
    get_settings.cache_clear()

    async def slow(request):
        await asyncio.sleep(2)
        return page("Slow")

    respx.get("https://site.test/").mock(return_value=httpx.Response(200, html=HOME))
    respx.get("https://site.test/battery-backup").mock(side_effect=slow)
    respx.get("https://site.test/installation").mock(return_value=page("Installation"))
    respx.get("https://site.test/about").mock(return_value=page("About"))

    pages, _ = await research.research_website("battery backup")
    assert "https://site.test/battery-backup" not in [p.url for p in pages]
    assert pages  # got the rest rather than failing
    _, cached = await research.research_website("battery backup")
    assert cached is False  # partial result was not cached under the query


@respx.mock
async def test_unreachable_site_raises_research_error():
    respx.get("https://site.test/").mock(return_value=httpx.Response(500))
    with pytest.raises(ResearchError):
        await research.research_website("anything")


# --- sitemap discovery -------------------------------------------------------------------------

SITEMAP = """<?xml version="1.0"?><urlset>
<url><loc>https://site.test/battery-storage</loc></url>
<url><loc>https://site.test/blog/battery-freezing/</loc></url>
<url><loc>https://other.test/battery-storage</loc></url>
<url><loc>https://site.test/logo.png</loc></url>
<url><loc>https://site.test/installation#section</loc></url></urlset>"""

HOME_ONE_LINK = '<html><head><title>Home</title></head><body><a href="/about">About us</a><main>%s</main></body></html>' % BODY


def mock_site(sitemap_status=200, sitemap_body=SITEMAP):
    home = respx.get("https://site.test/").mock(return_value=httpx.Response(200, html=HOME_ONE_LINK))
    respx.get("https://site.test/about").mock(return_value=page("About"))
    deep = respx.get("https://site.test/battery-storage").mock(return_value=page("Battery storage", "charge to cover evening demand"))
    respx.get("https://site.test/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://site.test/sitemap.xml").mock(return_value=httpx.Response(sitemap_status, text=sitemap_body))
    respx.get("https://site.test/sitemap_index.xml").mock(return_value=httpx.Response(404))
    respx.get("https://site.test/wp-sitemap.xml").mock(return_value=httpx.Response(404))
    respx.get(url__regex=r"https://site.test/(blog|installation).*").mock(return_value=page("Other"))
    return home, deep


@respx.mock
async def test_a_page_that_is_only_in_the_sitemap_is_found_and_ranked_first():
    mock_site()
    pages, _ = await research.research_website("explain battery storage")
    assert pages[0].url == "https://site.test/battery-storage" and "charge to cover" in pages[0].text


@respx.mock
async def test_offsite_asset_and_fragment_urls_in_the_sitemap_are_ignored():
    mock_site()
    pages, _ = await research.research_website("battery storage")
    urls = [p.url for p in pages]
    assert all(u.startswith("https://site.test/") and not u.endswith(".png") for u in urls)
    assert "https://other.test/battery-storage" not in urls


@respx.mock
async def test_a_missing_or_broken_sitemap_changes_nothing():
    mock_site(sitemap_status=404)
    pages, _ = await research.research_website("about")
    assert {p.url for p in pages} == {"https://site.test/", "https://site.test/about"}  # exactly the homepage links
    research.clear_caches()
    mock_site(sitemap_status=200, sitemap_body="<<< not xml at all")
    assert await research.research_website("about")


@respx.mock
async def test_a_sitemap_index_is_followed_and_robots_txt_can_name_the_sitemap():
    respx.get("https://site.test/").mock(return_value=httpx.Response(200, html=HOME_ONE_LINK))
    respx.get("https://site.test/about").mock(return_value=page("About"))
    respx.get("https://site.test/robots.txt").mock(return_value=httpx.Response(200, text="User-agent: *\nSitemap: https://site.test/maps/index.xml\n"))
    respx.get("https://site.test/maps/index.xml").mock(return_value=httpx.Response(
        200, text="<sitemapindex><sitemap><loc>https://site.test/maps/pages.xml</loc></sitemap></sitemapindex>"))
    respx.get("https://site.test/maps/pages.xml").mock(return_value=httpx.Response(
        200, text="<urlset><url><loc>https://site.test/battery-storage</loc></url></urlset>"))
    for path in research._SITEMAP_PATHS:
        respx.get("https://site.test" + path).mock(return_value=httpx.Response(404))
    respx.get("https://site.test/battery-storage").mock(return_value=page("Battery storage"))

    pages, _ = await research.research_website("battery storage")
    assert pages[0].url == "https://site.test/battery-storage"


@respx.mock
async def test_the_sitemap_is_read_once_per_cache_lifetime():
    mock_site()
    await research.research_website("battery storage")
    await research.research_website("a different question about blog")
    calls = [c for c in respx.calls if str(c.request.url) == "https://site.test/sitemap.xml"]
    assert len(calls) == 1


def test_sitemap_parsing_and_slug_text():
    pages, nested = research._parse_sitemap("<urlset><url><loc> https://a.test/x </loc></url></urlset>")
    assert pages == ["https://a.test/x"] and nested == []
    pages, nested = research._parse_sitemap("<sitemapindex><sitemap><loc>https://a.test/s.xml</loc></sitemap></sitemapindex>")
    assert pages == [] and nested == ["https://a.test/s.xml"]
    assert research._slug_text("https://a.test/treatments/battery-storage/") == "battery storage"


# --- language and duplicates --------------------------------------------------------------------------

TAMIL = "இது சென்னையில் உள்ள ஐவிஎஃப் சிகிச்சை பற்றிய தகவல் பக்கம். " * 8
ENGLISH_BATTERY = "Battery storage holds charge so that several appliances run in one evening."


def _pages(*specs):
    return [research.Page(title=t, url=u, text=x, score=sc) for t, u, x, sc in specs]


def test_pages_in_another_script_are_skipped_for_an_english_request():
    pages = _pages(("Tamil", "https://site.test/tamil/installation", TAMIL, 9.0), ("English", "https://site.test/installation", ENGLISH_BATTERY * 3, 5.0))
    assert [p.title for p in research._select("explain battery storage", pages, 8)] == ["English"]


def test_the_language_filter_is_dropped_if_it_would_leave_nothing():
    pages = _pages(("Tamil", "https://site.test/tamil/installation", TAMIL, 9.0))
    assert len(research._select("explain battery storage", pages, 8)) == 1


def test_a_non_latin_request_keeps_pages_in_that_script():
    pages = _pages(("Tamil", "https://site.test/tamil/installation", TAMIL, 9.0), ("English", "https://site.test/installation", ENGLISH_BATTERY * 3, 5.0))
    assert len(research._select("ஐவிஎஃப் சிகிச்சை பற்றி விளக்கவும்", pages, 8)) == 2


def test_the_same_page_under_different_urls_is_listed_once():
    text = ENGLISH_BATTERY * 3
    pages = _pages(("Home", "https://site.test/", text, 3.0), ("Home again", "https://www.site.test", text, 2.0),
                   ("Home query", "http://site.test/?utm=1#top", "Other words about scans. " * 5, 1.5),
                   ("Scans", "https://site.test/scans", "Other words about scans. " * 5, 1.0))
    # www., a missing trailing slash, http versus https, and query strings all point at the same page.
    assert [p.title for p in research._select("scans", pages, 8)] == ["Home", "Scans"]


def test_two_different_urls_with_identical_text_are_one_page():
    text = ENGLISH_BATTERY * 3
    pages = _pages(("A", "https://site.test/a", text, 2.0), ("B", "https://site.test/b", text, 1.0))
    assert [p.title for p in research._select("battery", pages, 8)] == ["A"]


def test_distinct_pages_are_not_merged_just_because_they_start_alike():
    boiler = "Welcome to Example Co. " * 20
    pages = _pages(("A", "https://site.test/a", boiler + "About battery storage.", 2.0), ("B", "https://site.test/b", boiler + "About panel cleaning.", 1.0))
    assert len(research._select("installation", pages, 8)) == 2


def test_latin_ratio():
    assert research._latin_ratio("plain English text") == 1.0 and research._latin_ratio(TAMIL) < 0.1
    assert research._latin_ratio("12345 !!!") == 1.0  # no letters: not judged


def test_translated_paths_are_recognised():
    for url in ("https://site.test/tamil/installation", "https://site.test/hi/", "https://site.test/Telugu/installation-process"):
        assert research._is_translated_path(url), url
    for url in ("https://site.test/", "https://site.test/installation/tamil-nadu", "https://site.test/energy-product/hi-tech", "https://site.test/en/installation"):
        assert not research._is_translated_path(url), url


@respx.mock
async def test_translated_copies_are_not_fetched_when_the_budget_is_tight(monkeypatch):
    # Budget: MAX_PAGES_TO_FETCH=1 means two candidates. Three links compete for them. Without the
    # penalty the Tamil copy (listed first, equal score) would take a slot and /about would be left out.
    home = """<html><head><title>Home</title></head><body>
      <a href="/tamil/installation-process">Installation process</a><a href="/installation-process">Installation process</a><a href="/about">About</a>
      <main>%s</main></body></html>""" % BODY
    respx.get("https://site.test/").mock(return_value=httpx.Response(200, html=home))
    english = respx.get("https://site.test/installation-process").mock(return_value=page("Installation process"))
    about = respx.get("https://site.test/about").mock(return_value=page("About"))
    tamil = respx.get("https://site.test/tamil/installation-process").mock(return_value=page("Tamil copy"))
    for path in ("/robots.txt", *research._SITEMAP_PATHS):
        respx.get("https://site.test" + path).mock(return_value=httpx.Response(404))
    monkeypatch.setenv("MAX_PAGES_TO_FETCH", "1")
    from app.config import get_settings
    get_settings.cache_clear()

    await research.research_website("installation process")

    assert english.called and about.called and not tamil.called
