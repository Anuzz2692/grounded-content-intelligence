
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import anthropic
import httpx
from anthropic import AsyncAnthropic

from app.config import get_settings
from app.errors import LLMUnavailableError
from app.prompts import load_brand_guidelines, read_prompt
from app.brief import Brief, brief_block
from app.structured import BRIEF_VIDEO, loosen, to_content, typed_schema
from app.research import Page

logger = logging.getLogger("content-agent.llm")


@dataclass
class LLMResult:
    data: dict[str, Any]
    provider: str
    model: str
    # Why the primary provider was skipped, when Ollama produced this result.
    fallback_reason: str | None = None
    # The model's own strict-format fields, when this request used one. Kept so the fix pass can
    # ask for a corrected version in the same format.
    typed: dict[str, Any] | None = None


class LLMOutputError(ValueError):
    """The model answered, but not with usable content."""

    def __init__(self, message: str, reason: str = "bad_output"):
        super().__init__(message)
        self.reason = reason


GENERATION_PROMPT_FILE = "content_generation.txt"

# The core prompt is always sent; one small module per format is added, so the system prompt
# stays short enough for local models.
CONTENT_GROUPS = {
    "article": "website",
    "blog": "website",
    "social_post": "social",
    "video_script": "video",
    BRIEF_VIDEO: "brief_video",
    "faq": "faq",
    "general": "general",
}
MODULE_FILES = {
    "website": "content_website.txt",
    "social": "content_social.txt",
    "video": "content_video.txt",
    "brief_video": "content_brief_video.txt",
    "faq": "content_faq.txt",
    "general": "content_general.txt",
}

# Output token budgets per format group and length, for MAX_OUTPUT_TOKENS=2200. They scale with
# that setting. A detailed website page (1,400-1,800 words plus FAQs) needs far more than a post.
TOKEN_BUDGETS = {
    "website": {"concise": 1400, "standard": 2600, "detailed": 5600},
    "social": {"concise": 1400, "standard": 1600, "detailed": 2000},
    "video": {"concise": 1500, "standard": 1800, "detailed": 2400},
    "brief_video": {"concise": 2200, "standard": 2200, "detailed": 2400},
    "faq": {"concise": 1200, "standard": 2000, "detailed": 3200},
    "general": {"concise": 1320, "standard": 2200, "detailed": 3960},
}
BASE_OUTPUT_TOKENS = 2200

LENGTH_GUIDANCE = {
    "website": {
        "concise": "main article of about 400-600 words; no FAQs or People Also Ask",
        "standard": "main article of about 800-1,100 words; no People Also Ask",
        "detailed": "a complete website page: main article of 1,400-1,800 words, then exactly 5 FAQs and exactly 5 People Also Ask questions",
    },
    "social": {
        "concise": "post copy of up to 40 words",
        "standard": "post copy of about 40-80 words",
        "detailed": "post copy of about 80-150 words",
    },
    "video": {
        "concise": "about 30 seconds, roughly 75 spoken words",
        "standard": "about 60 seconds, roughly 150 spoken words",
        "detailed": "about 90-120 seconds, roughly 225-300 spoken words",
    },
    "brief_video": {k: "the duration, segments and spoken-word budget in <content_brief>" for k in ("concise", "standard", "detailed")},
    "faq": {"concise": "3 questions", "standard": "5 questions", "detailed": "8 questions"},
    "general": {
        "concise": "roughly 300-450 words in total",
        "standard": "roughly 700-900 words in total",
        "detailed": "roughly 1,200-1,600 words in total",
    },
}

CONTENT_TYPE_GUIDANCE = {
    "article": "a long-form website article or page",
    "blog": "a conversational website blog post",
    "social_post": "a social media post with caption, tags and hashtags",
    "video_script": "a short video with script, title, description, tags, hashtags and thumbnail hook",
    BRIEF_VIDEO: "a presenter-led short video written strictly to the <content_brief>",
    "faq": "an FAQ; each section is one reader question and its answer",
    "general": "well-structured content suited to the request",
}


def content_group(content_type: str) -> str:
    return CONTENT_GROUPS.get(content_type, "general")


def system_prompt(content_type: str) -> str:
    """Core prompt plus the module for this content type."""
    return read_prompt(GENERATION_PROMPT_FILE) + "\n\n" + read_prompt(MODULE_FILES[content_group(content_type)])


# JSON schema shared with Ollama's structured-output feature.
CONTENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "introduction": {"type": "string"},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["heading", "body"],
                "additionalProperties": False,
            },
        },
        "conclusion": {"type": "string"},
        "suggested_cta": {
            "type": ["string", "null"],
        },
        "reviewer_notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "title",
        "summary",
        "introduction",
        "sections",
        "conclusion",
        "suggested_cta",
    ],
    "additionalProperties": False,
}


def _research_block(pages: list[Page], max_chars: int | None = None) -> str:
    research = []
    limit = get_settings().max_research_chars
    remaining = min(limit, max_chars) if max_chars else limit

    for page in pages:
        if remaining <= 0:
            break

        excerpt = page.text[:remaining]
        remaining -= len(excerpt)

        # Stop page text from closing the tag early and posing as instructions.
        excerpt = excerpt.replace("</", "<\\/")
        research.append(
            f'<source title="{page.title.replace(chr(34), chr(39))}" url="{page.url}">\n'
            f"{excerpt}\n"
            "</source>"
        )
    return "\n\n".join(research) or "(No relevant website research was retrieved.)"


def _guidelines_block() -> str:
    guidelines = load_brand_guidelines()
    return f"\n<brand_guidelines>\n{guidelines.replace('</', '<\\/')}\n</brand_guidelines>\n" if guidelines else ""


def _request_block(query: str, content_type: str, tone: str, length: str) -> str:
    group = content_group(content_type)
    guidance_type = CONTENT_TYPE_GUIDANCE.get(content_type, CONTENT_TYPE_GUIDANCE["general"])
    guidance_length = LENGTH_GUIDANCE[group].get(length, LENGTH_GUIDANCE[group]["standard"])
    return f"""<request>
USER REQUEST: {query.replace("</", "<\\/")}
CONTENT TYPE: {content_type} ({guidance_type})
TONE: {tone.replace("</", "<\\/")}
LENGTH: {length} ({guidance_length})
</request>"""


def _build_prompt(
    query: str,
    content_type: str,
    tone: str,
    length: str,
    pages: list[Page],
    max_chars: int | None = None,
    brief: Brief | None = None,
) -> str:
    return f"""
{_request_block(query, content_type, tone, length)}{brief_block(brief) if brief else ""}

<website_research>
{_research_block(pages, max_chars)}
</website_research>
{_guidelines_block()}""".strip()


def _validate_content(parsed: Any, optional: tuple[str, ...] = ()) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        raise LLMOutputError("LLM response must be a JSON object.")

    required = {"title", "summary", "introduction", "sections", "conclusion"}
    missing = required - parsed.keys()
    if missing:
        raise LLMOutputError(
            "LLM JSON is missing required content fields: " + ", ".join(sorted(missing))
        )

    for field in ("title", "summary", "introduction", "conclusion"):
        if field in optional and isinstance(parsed[field], str):
            continue
        if not isinstance(parsed[field], str) or not parsed[field].strip():
            raise LLMOutputError(f"LLM field '{field}' must be a non-empty string.")

    sections = parsed["sections"]
    if not isinstance(sections, list) or not sections:
        raise LLMOutputError("LLM field 'sections' must be a non-empty list.")

    for index, section in enumerate(sections):
        if not isinstance(section, dict):
            raise LLMOutputError(f"LLM section {index} must be a JSON object.")
        for field in ("heading", "body"):
            value = section.get(field)
            if not isinstance(value, str) or not value.strip():
                raise LLMOutputError(
                    f"LLM section {index} field '{field}' must be a non-empty string."
                )

    notes = parsed.get("reviewer_notes")
    if isinstance(notes, str):
        notes = [notes]
    parsed["reviewer_notes"] = [str(n).strip() for n in notes if str(n).strip()] if isinstance(notes, list) else []

    if "suggested_cta" not in parsed:
        parsed["suggested_cta"] = None
    elif parsed["suggested_cta"] is not None and not isinstance(parsed["suggested_cta"], str):
        raise LLMOutputError("LLM field 'suggested_cta' must be a string or null.")

    return parsed


def _loads(text: str) -> dict[str, Any]:
    """Parse model text (used for Ollama) into a JSON object."""
    text = text.strip()

    # Remove optional Markdown code fences.
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Recover a JSON object if the model added text around it.
        start = text.find("{")
        end = text.rfind("}")

        if start < 0 or end <= start:
            raise LLMOutputError("LLM did not return a JSON object.") from None

        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMOutputError("LLM returned malformed JSON.") from exc

    if not isinstance(parsed, dict):
        raise LLMOutputError("LLM response must be a JSON object.")
    return parsed


def _parse_json(text: str) -> dict[str, Any]:
    return _validate_content(_loads(text))


def _finish(raw: Any, content_type: str, length: str, generic: bool) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Turn the model's output into shared content. Returns (content, the strict-format fields or None)."""
    if not isinstance(raw, dict):
        raise LLMOutputError("LLM response must be a JSON object.")
    if not generic and typed_schema(content_type, length) is not None:
        # A brief-driven video has no separate summary or conclusion: its parts are the script, caption and hashtags.
        optional = ("summary", "conclusion") if content_type == BRIEF_VIDEO else ()
        return _validate_content(to_content(content_type, length, raw), optional), raw
    return _validate_content(raw), None


def _schema_for(content_type: str, length: str, generic: bool) -> dict[str, Any]:
    return CONTENT_SCHEMA if generic else (typed_schema(content_type, length) or CONTENT_SCHEMA)


def _max_tokens(content_type: str, length: str) -> int:
    budgets = TOKEN_BUDGETS[content_group(content_type)]
    base = budgets.get(length, budgets["standard"])
    return int(base * get_settings().max_output_tokens / BASE_OUTPUT_TOKENS)


_client: AsyncAnthropic | None = None
_client_key: tuple[str, float] | None = None


def _get_client() -> AsyncAnthropic:
    """Reuse one client so connections are pooled across requests."""
    global _client, _client_key
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured.")
    key = (settings.anthropic_api_key, settings.llm_timeout_seconds)
    if _client is None or _client_key != key:
        _client = AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )
        _client_key = key
    return _client


async def _call_anthropic(
    prompt: str, content_type: str, length: str, system: str | None = None, generic: bool = False, temperature: float | None = None
) -> LLMResult:
    settings = get_settings()
    client = _get_client()
    tool = {
        "name": "submit_content",
        "description": "Submit the finished content in the required structure.",
        "input_schema": _schema_for(content_type, length, generic),
    }

    # Forcing a tool call makes the API return schema-shaped JSON, which avoids
    # most parse failures (and therefore needless fallbacks to the weaker model).
    response = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=_max_tokens(content_type, length),
        temperature=0.3 if temperature is None else temperature,
        tools=[tool],
        tool_choice={"type": "tool", "name": "submit_content"},
        system=system or system_prompt(content_type),
        messages=[{"role": "user", "content": prompt}],
    )

    if response.stop_reason == "max_tokens":
        raise LLMOutputError("Anthropic output hit the token limit.", reason="truncated")

    tool_inputs = [
        block.input for block in response.content if getattr(block, "type", "") == "tool_use"
    ]
    if not tool_inputs:
        raise LLMOutputError("Anthropic returned no structured content.")

    content, typed = _finish(tool_inputs[0], content_type, length, generic)
    return LLMResult(content, "anthropic", settings.anthropic_model, typed=typed)


def ollama_options(system: str, user: str, num_predict: int, temperature: float) -> dict[str, Any]:
    """Size the context window to the prompt.

    Ollama silently drops the start of a prompt that does not fit, and the start is where the
    instructions are. Estimate the prompt conservatively (about 3 characters per token) and
    grow num_ctx to fit it plus the answer, up to OLLAMA_MAX_CTX.
    """
    settings = get_settings()
    needed = (len(system) + len(user)) // 3 + num_predict + 256
    wanted = -(-max(settings.ollama_num_ctx, needed) // 1024) * 1024
    num_ctx = min(settings.ollama_max_ctx, wanted)
    if needed > num_ctx:
        logger.warning(
            "Prompt needs about %d tokens but the Ollama context is capped at %d; "
            "raise OLLAMA_MAX_CTX or lower MAX_RESEARCH_CHARS.",
            needed,
            num_ctx,
        )
    return {"temperature": temperature, "num_ctx": num_ctx, "num_predict": num_predict}


def ensure_ollama_ok(response: httpx.Response) -> None:
    """Ollama answers 404 when the requested model has not been pulled."""
    if response.status_code == 404:
        raise LLMOutputError("The Ollama model is not installed.", reason="model_not_found")
    response.raise_for_status()


async def _call_ollama(
    prompt: str, content_type: str, length: str, system: str | None = None, generic: bool = False, temperature: float | None = None
) -> LLMResult:
    settings = get_settings()
    url = settings.ollama_base_url.rstrip("/") + "/api/chat"
    system = system or system_prompt(content_type)
    schema = _schema_for(content_type, length, generic)

    def payload(format_schema: dict[str, Any]) -> dict[str, Any]:
        return {
            "model": settings.ollama_model,
            "stream": False,
            "format": format_schema,
            "options": ollama_options(system, prompt, _max_tokens(content_type, length), 0.1 if temperature is None else temperature),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }

    async with httpx.AsyncClient(timeout=settings.ollama_timeout_seconds) as client:
        response = await client.post(url, json=payload(schema))
        if response.status_code == 400 and loosen(schema) != schema:
            # An older Ollama may reject item-count limits. Retry without them; the format
            # checks and the fix pass still catch a wrong count.
            logger.warning("Ollama rejected the output schema; retrying without item-count limits")
            response = await client.post(url, json=payload(loosen(schema)))
        ensure_ollama_ok(response)
        body = response.json()

    if body.get("done_reason") == "length":
        raise LLMOutputError("Ollama output hit the token limit.", reason="truncated")

    text = body.get("message", {}).get("content", "")
    if not isinstance(text, str) or not text.strip():
        raise LLMOutputError("Ollama returned an empty response.")

    content, typed = _finish(_loads(text), content_type, length, generic)
    return LLMResult(content, "ollama", settings.ollama_model, typed=typed)


def classify_error(exc: Exception) -> str:
    """Map a provider exception to a short, safe reason code (no secrets or raw messages)."""
    if isinstance(exc, LLMOutputError):
        return exc.reason
    if isinstance(exc, anthropic.AuthenticationError | anthropic.PermissionDeniedError):
        return "auth"
    if isinstance(exc, anthropic.RateLimitError):
        return "rate_limit"
    if isinstance(exc, anthropic.APITimeoutError | httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, anthropic.APIConnectionError | httpx.ConnectError):
        return "connection"
    if isinstance(exc, anthropic.APIStatusError):
        return f"http_{exc.status_code}"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"http_{exc.response.status_code}"
    if isinstance(exc, RuntimeError) and "not configured" in str(exc):
        return "not_configured"
    return "provider_error"


async def _only(provider: str, call) -> LLMResult:
    """Run a single provider (no fallback) and report failure by reason code."""
    try:
        return await call
    except Exception as exc:
        reason = classify_error(exc)
        logger.error("%s failed (%s: %s)", provider, type(exc).__name__, reason)
        raise LLMUnavailableError({provider: reason}) from exc


async def generate_grounded_content(
    query: str,
    content_type: str,
    tone: str,
    length: str,
    pages: list[Page],
    brief: Brief | None = None,
) -> LLMResult:
    settings = get_settings()
    provider = settings.llm_provider

    def local_prompt() -> str:
        # Local models get a smaller research budget so the prompt fits their context.
        return _build_prompt(query, content_type, tone, length, pages, settings.ollama_max_research_chars, brief)

    if provider == "ollama":
        return await _only("ollama", _call_ollama(local_prompt(), content_type, length))

    prompt = _build_prompt(query, content_type, tone, length, pages, brief=brief)
    if provider == "anthropic":
        return await _only("anthropic", _call_anthropic(prompt, content_type, length))

    reasons: dict[str, str] = {}
    try:
        return await _call_anthropic(prompt, content_type, length)
    except Exception as exc:
        # Never log the exception message: provider errors can echo request details.
        reasons["anthropic"] = classify_error(exc)
        logger.warning(
            "Primary LLM failed (%s: %s); falling back to Ollama",
            type(exc).__name__,
            reasons["anthropic"],
        )

    try:
        result = await _call_ollama(local_prompt(), content_type, length)
    except Exception as exc:
        reasons["ollama"] = classify_error(exc)
        logger.error("Fallback LLM failed (%s: %s)", type(exc).__name__, reasons["ollama"])
        raise LLMUnavailableError(reasons) from exc

    result.fallback_reason = reasons["anthropic"]
    return result


async def repair_content(
    query: str,
    content_type: str,
    tone: str,
    length: str,
    pages: list[Page],
    previous: dict[str, Any],
    problems: list[str],
    provider: str,
    brief: Brief | None = None,
) -> LLMResult:
    """Ask the provider that wrote `previous` to fix only the listed problems.

    The writing rules are unchanged, so the fix cannot add unsupported claims by design;
    the caller keeps the original if the fix is not better.
    """
    settings = get_settings()
    # Model output could contain "</", so neutralise it like any other untrusted text.
    previous_json = json.dumps(previous, ensure_ascii=False).replace("</", "<\\/")
    fix_request = (
        "\n\n<fix_request>\nYour previous answer did not meet these requirements:\n"
        + "\n".join(f"- {p}" for p in problems)
        + f"\n\nYour previous answer:\n{previous_json}\n\n"
        "Return the complete corrected JSON object. Change only what is needed to meet the "
        "requirements above and keep everything else. Add no claim that the website research "
        "does not support.\n</fix_request>"
    )
    if provider == "ollama":
        prompt = _build_prompt(query, content_type, tone, length, pages, settings.ollama_max_research_chars, brief)
        return await _call_ollama(prompt + fix_request, content_type, length)
    prompt = _build_prompt(query, content_type, tone, length, pages, brief=brief)
    return await _call_anthropic(prompt + fix_request, content_type, length)


HUMANIZE_PROMPT_FILE = "content_humanize.txt"
# A little more variety than the writing step gives more natural phrasing. The guard in
# app.humanize catches the occasional rewrite that strays.
HUMANIZE_TEMPERATURE = 0.6
HUMANIZE_TEMPERATURE_LOCAL = 0.4
# The rewrite needs the research only as a reference, so keep it short for local models.
HUMANIZE_OLLAMA_RESEARCH_CHARS = 6000


async def humanize_content(
    query: str,
    content_type: str,
    tone: str,
    length: str,
    pages: list[Page],
    draft: dict[str, Any],
    provider: str,
    notes: str = "",
) -> LLMResult:
    """Rewrite `draft` to read naturally, using the provider that wrote it.

    The result is only a candidate. app.humanize decides whether it is safe to use.
    """
    settings = get_settings()
    draft_json = json.dumps(draft, ensure_ascii=False).replace("</", "<\\/")
    local = provider == "ollama"
    max_chars = min(settings.ollama_max_research_chars, HUMANIZE_OLLAMA_RESEARCH_CHARS) if local else None
    # Specific problems the application measured in this draft, so the rewrite fixes those first.
    notes_block = f"\n<editing_notes>\n{notes.replace('</', '<\\/')}\n</editing_notes>\n" if notes.strip() else ""
    prompt = f"""
{_request_block(query, content_type, tone, length)}

<original_draft>
{draft_json}
</original_draft>
{notes_block}
<website_research>
{_research_block(pages, max_chars)}
</website_research>
{_guidelines_block()}""".strip()
    system = read_prompt(HUMANIZE_PROMPT_FILE)
    if local:
        return await _call_ollama(prompt, content_type, length, system=system, generic=True, temperature=HUMANIZE_TEMPERATURE_LOCAL)
    return await _call_anthropic(prompt, content_type, length, system=system, generic=True, temperature=HUMANIZE_TEMPERATURE)
