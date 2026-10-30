import asyncio
import logging
import re
from dataclasses import dataclass, replace
from urllib.parse import urljoin, urlparse, urldefrag

import httpx
from bs4 import BeautifulSoup
from cachetools import TTLCache

from app.config import get_settings
from app.errors import ResearchError

logger = logging.getLogger("content-agent.research")


@dataclass
class Page:
    title: str
    url: str
    text: str
    score: float = 0.0


@dataclass
class _Link:
    url: str
    anchor: str


@dataclass
class _SiteIndex:
    home: Page | None
    links: list[_Link]


_HEADERS = {
    "User-Agent": "ARTContentResearchBot/1.0 (+website-grounded content research)"
}
_SKIP_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf", ".zip", ".css", ".js", ".svg")

# Caches are built lazily so they pick up CACHE_TTL_SECONDS from settings.
# All access happens on the event loop without awaiting in between, so no lock is needed.
_caches: dict[str, TTLCache] = {}


def _cache(name: str) -> TTLCache:
    if name not in _caches:
        _caches[name] = TTLCache(maxsize=256, ttl=get_settings().cache_ttl_seconds)
    return _caches[name]


def clear_caches() -> None:
    _caches.clear()


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-zA-Z0-9]+", text.lower()) if len(t) > 2}


def _score(query: str, title: str, text: str, url: str) -> float:
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.0
    title_tokens = _tokens(title)
    body_tokens = _tokens(text[:12000])
    url_tokens = _tokens(url.replace("/", " ").replace("-", " "))
    title_hits = len(query_tokens & title_tokens)
    body_hits = len(query_tokens & body_tokens)
    url_hits = len(query_tokens & url_tokens)
    return round((title_hits * 4 + url_hits * 2 + body_hits) / len(query_tokens), 4)


def _link_score(query_tokens: set[str], link: _Link) -> int:
    """Cheap pre-fetch relevance estimate from the anchor text and URL slug."""
    link_tokens = _tokens(link.anchor) | _tokens(link.url.replace("/", " ").replace("-", " "))
    return len(query_tokens & link_tokens)


def _extract_page(html: str, url: str) -> Page | None:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form"]):
        tag.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else url
    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = re.sub(r"\s+", " ", main.get_text(" ", strip=True)).strip()
    if len(text) < 180:
        return None
    return Page(title=title[:240], url=url, text=text[: get_settings().max_chars_per_page])


def _allowed_url(url: str, base_url: str) -> bool:
    parsed, base = urlparse(url), urlparse(base_url)
    return (
        parsed.scheme in {"http", "https"}
        and parsed.netloc.lower() == base.netloc.lower()
        and not parsed.path.lower().endswith(_SKIP_EXTENSIONS)
    )


def _discover_links(html: str, page_url: str, base_url: str) -> list[_Link]:
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, _Link] = {}
    for a in soup.find_all("a", href=True):
        url = urldefrag(urljoin(page_url, a["href"]))[0]
        if not _allowed_url(url, base_url):
            continue
        anchor = a.get_text(" ", strip=True)
        existing = found.get(url)
        if existing is None:
            found[url] = _Link(url=url, anchor=anchor)
        elif anchor and anchor not in existing.anchor:
            existing.anchor = f"{existing.anchor} {anchor}".strip()
    return list(found.values())


async def _fetch_html(client: httpx.AsyncClient, url: str) -> tuple[str, str] | None:
    try:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type:
            return None
        return str(response.url), response.text
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Fetch failed for %s (%s)", url, type(exc).__name__)
        return None


async def _fetch_page(client: httpx.AsyncClient, url: str) -> Page | None:
    result = await _fetch_html(client, url)
    if not result:
        return None
    final_url, html = result
    # HTML parsing is CPU-bound; keep it off the event loop.
    return await asyncio.to_thread(_extract_page, html, final_url)


# Pages deeper in the site are often not linked from the homepage, but a sitemap lists them.
_SITEMAP_PATHS = ("/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml")
MAX_SITEMAP_FILES = 6
MAX_SITEMAP_URLS = 2000
_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)


def _parse_sitemap(xml: str) -> tuple[list[str], list[str]]:
    """(page URLs, nested sitemap URLs). A plain regex: no XML parser means no entity-expansion risk."""
    locs = _LOC.findall(xml)
    return ([], locs) if "<sitemapindex" in xml.lower() else (locs, [])


def _slug_text(url: str) -> str:
    segment = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"[-_]+", " ", segment).strip()


async def _fetch_text(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        return response.text
    except (httpx.HTTPError, ValueError):
        return None


async def _sitemap_urls(client: httpx.AsyncClient, base_url: str) -> list[str]:
    """Page URLs from the site's sitemap(s). Any failure just means no extra pages."""
    root = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"
    queue = [root + path for path in _SITEMAP_PATHS]
    robots = await _fetch_text(client, root + "/robots.txt")
    if robots:
        queue = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", robots) + queue

    pages: list[str] = []
    seen_files: set[str] = set()
    while queue and len(seen_files) < MAX_SITEMAP_FILES and len(pages) < MAX_SITEMAP_URLS:
        batch = [u for u in dict.fromkeys(queue) if u not in seen_files and _allowed_url(u, base_url)]
        queue = []
        batch = batch[: MAX_SITEMAP_FILES - len(seen_files)]
        seen_files.update(batch)
        for text in await asyncio.gather(*[_fetch_text(client, u) for u in batch]):
            if not text:
                continue
            found, nested = _parse_sitemap(text)
            pages += found
            queue += nested
    return [u for u in dict.fromkeys(urldefrag(p)[0] for p in pages) if _allowed_url(u, base_url)][:MAX_SITEMAP_URLS]


async def _site_index(client: httpx.AsyncClient) -> _SiteIndex:
    settings = get_settings()
    cache = _cache("site")
    cached = cache.get("index")
    if cached:
        return cached

    result = await _fetch_html(client, settings.website_base_url)
    if not result:
        raise ResearchError("The configured website could not be fetched.")
    base_url, html = result
    home = await asyncio.to_thread(_extract_page, html, base_url)
    links = await asyncio.to_thread(_discover_links, html, base_url, settings.website_base_url)
    try:
        known = {link.url for link in links}
        links += [_Link(url=u, anchor=_slug_text(u)) for u in await _sitemap_urls(client, settings.website_base_url) if u not in known]
    except Exception as exc:  # the sitemap is a bonus, never a reason to fail
        logger.warning("Sitemap discovery failed (%s)", type(exc).__name__)
    index = _SiteIndex(home=home, links=links)
    cache["index"] = index
    return index


async def _fetch_missing(client: httpx.AsyncClient, urls: list[str]) -> bool:
    """Fetch uncached pages concurrently, stopping at the request deadline.

    Slow pages are abandoned rather than holding up the whole request.
    Returns False if any fetch was abandoned, so callers avoid caching a partial result.
    """
    page_cache = _cache("pages")
    missing = [u for u in urls if u not in page_cache]
    if not missing:
        return True

    deadline = get_settings().request_timeout_seconds
    tasks = {asyncio.create_task(_fetch_page(client, u)): u for u in missing}
    done, pending = await asyncio.wait(tasks, timeout=deadline)
    for task in pending:
        task.cancel()
        logger.warning("Abandoned slow fetch for %s", tasks[task])
    for task in done:
        if task.cancelled() or task.exception():
            continue
        page = task.result()
        if page:
            page_cache[tasks[task]] = page
    return not pending


def _latin_ratio(text: str) -> float:
    """Share of letters that are Latin-script. A Tamil or Telugu page scores near 0."""
    letters = [c for c in text if c.isalpha()]
    return sum(ord(c) < 0x250 for c in letters) / len(letters) if letters else 1.0


# Sites often keep translated copies under /tamil/, /hi/ and the like.
_LANGUAGE_SEGMENTS = frozenset(
    "tamil telugu hindi gujarati kannada malayalam marathi bengali punjabi odia urdu assamese ta te hi gu kn ml mr bn pa ur".split()
)


def _is_translated_path(url: str) -> bool:
    segments = [s.lower() for s in urlparse(url).path.split("/") if s]
    return bool(segments) and segments[0] in _LANGUAGE_SEGMENTS


def _same_page_key(url: str) -> str:
    """http/https, www, trailing slash, query and fragment do not make a different page."""
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    return f"{host}{parsed.path.rstrip('/')}"


def _select(query: str, pages: list[Page], limit: int) -> list[Page]:
    """The best distinct pages, in the query's language.

    Pages in another script (the site's Tamil or Telugu versions) are useless evidence for an
    English request and would use up the research budget, so they are skipped. If that would
    leave nothing, the language filter is dropped.
    """
    distinct: list[Page] = []
    seen_urls: set[str] = set()
    seen_text: set[int] = set()
    for page in pages:  # already sorted best first
        url_key, text_key = _same_page_key(page.url), hash(" ".join(page.text.lower().split()))
        if url_key in seen_urls or text_key in seen_text:
            continue
        seen_urls.add(url_key)
        seen_text.add(text_key)
        distinct.append(page)

    if _latin_ratio(query) >= 0.8:
        same_language = [p for p in distinct if _latin_ratio(p.text[:2000]) >= 0.6]
        distinct = same_language or distinct
    return distinct[:limit]


async def research_website(query: str) -> tuple[list[Page], bool]:
    """Return the most relevant pages for the query and whether it was fully cached."""
    settings = get_settings()
    query_key = " ".join(query.lower().split())
    query_cache = _cache("queries")
    cached = query_cache.get(query_key)
    if cached:
        return [replace(p) for p in cached], True

    timeout = httpx.Timeout(settings.request_timeout_seconds)
    limits = httpx.Limits(max_connections=10, max_keepalive_connections=5)
    async with httpx.AsyncClient(timeout=timeout, headers=_HEADERS, limits=limits) as client:
        index = await _site_index(client)

        # Rank links by anchor text and URL before fetching, so the request budget goes
        # to the pages most likely to matter. Ties keep homepage order (stable sort).
        query_tokens = _tokens(query)
        # For an English request, translated copies of pages go to the back of the queue so the
        # fetch budget is spent on pages that can actually be used.
        english = _latin_ratio(query) >= 0.8
        ranked = sorted(index.links, key=lambda link: (english and _is_translated_path(link.url), -_link_score(query_tokens, link)))
        candidates = [link.url for link in ranked[: settings.max_pages_to_fetch * 2]]
        complete = await _fetch_missing(client, candidates)

    page_cache = _cache("pages")
    pages = [replace(index.home)] if index.home else []
    pages += [replace(page_cache[u]) for u in candidates if u in page_cache]

    for page in pages:
        page.score = _score(query, page.title, page.text, page.url)

    pages.sort(key=lambda p: p.score, reverse=True)
    pages = _select(query, pages, settings.max_pages_to_fetch)
    if not pages:
        raise ResearchError("No readable website pages were found.")
    if complete:
        query_cache[query_key] = [replace(p) for p in pages]
    return pages, False
