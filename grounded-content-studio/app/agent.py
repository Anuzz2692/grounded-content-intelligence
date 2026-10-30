import logging
import time
from dataclasses import dataclass, field

from app.config import get_settings
from app.format_checks import check_format, check_risky_claims
from app.humanize import accept_rewrite
from app.llm import LLMResult, classify_error, generate_grounded_content, humanize_content, repair_content
from app.naturalness import analyse, clean, editing_notes
from app import selfcheck
from app.brief import Brief
from app.structured import BRIEF_VIDEO
from app.research import Page, research_website

logger = logging.getLogger("content-agent")

# A second, targeted rewrite runs only if the first leaves at least this many flagged habits.
SECOND_PASS_MIN_ISSUES = 3


def site_texts(pages: list[Page]) -> list[str]:
    """Text of the website pages: the only evidence for claims about the company."""
    return [p.text for p in pages]


@dataclass
class AgentRun:
    result: LLMResult
    pages: list[Page]
    cached: bool
    research_ms: int
    generation_ms: int
    format_warnings: list[str] = field(default_factory=list)
    format_repaired: bool = False
    original_content: dict | None = None
    humanized: bool = False
    humanize_note: str | None = None
    humanize_level: str | None = None
    naturalness: dict | None = None
    brief: Brief | None = None


@dataclass
class Polish:
    content: dict
    changed: bool
    note: str
    naturalness: dict | None = None


def _with_claims(notes: str, claims: list[str]) -> str:
    """Add the unsupported claims found in the draft to the editing notes."""
    if not claims:
        return notes
    listed = "\n".join(f"  - {c}" for c in claims)
    return "\n".join(filter(None, [notes, f"- Unsupported claims. Remove them rather than softening them, and say so in reviewer_notes:\n{listed}"]))


async def _polish(
    query: str, content_type: str, tone: str, length: str, pages: list[Page], result: LLMResult, level: str,
    allow_rewrite: bool = True,
) -> Polish:
    """Make the writing read naturally. Every step is optional and every result is checked.

    natural: an AI rewrite (guarded by app.humanize), a second targeted rewrite if formulaic wording
    remains, then a deterministic clean-up of stock filler. light: the clean-up only, no AI call.
    Whatever goes wrong, the draft that came in is what comes out.
    """
    settings = get_settings()
    evidence = site_texts(pages)
    original = result.data
    current = original
    steps: list[str] = []

    if level == "natural" and not allow_rewrite:
        steps.append("The AI rewrite was skipped because a required part is missing from the draft, and polishing it would not fix that")
    elif level == "natural":
        passes = 2 if settings.humanize_second_pass else 1
        for attempt in range(passes):
            report = analyse(current)
            claims_left = check_risky_claims(current, evidence)
            if attempt == 1 and report.issues + len(claims_left) < SECOND_PASS_MIN_ISSUES:
                break
            try:
                notes = _with_claims(editing_notes(report), claims_left)
                candidate = await humanize_content(
                    query, content_type, tone, length, pages, current, result.provider, notes=notes
                )
            except Exception as exc:
                reason = classify_error(exc)
                logger.warning("Humanize failed (%s: %s)", type(exc).__name__, reason)
                steps.append(f"The AI rewrite failed ({reason})")
                break
            outcome = accept_rewrite(current, candidate.data, content_type, length, evidence)
            if outcome.content is None:
                steps.append(outcome.note.rstrip(".") if attempt == 0 else "A second pass was discarded")
                break
            current = outcome.content
            steps.append("Rewritten for natural flow" if attempt == 0 else "A second pass fixed the remaining stock phrasing")

    # Free and instant: delete the most common filler. Judged like any other rewrite.
    tidy = clean(current, evidence)
    if tidy != current:
        verdict = accept_rewrite(current, tidy, content_type, length, evidence)
        if verdict.content is not None:
            current = verdict.content
            steps.append("Stock filler phrases removed")

    changed = current != original
    if not changed and not steps:
        steps.append("The draft already read naturally, so no changes were made")
    note = ". ".join(steps) + "."
    naturalness = {"before": analyse(original).as_dict(), "after": analyse(current).as_dict()} if changed else None
    return Polish(current, changed, note, naturalness)


async def _run_brief_agent(query: str, tone: str, length: str, brief: Brief) -> AgentRun:
    """A presenter-led video written to a brief. The brief's own checks replace the generic format checks, and the
    natural-writing pass is skipped: a rewrite could alter the approved hook, CTA or claim wording."""
    started = time.perf_counter()
    # Website pages give company context only. Factual statements may come
    # only from the brief's approved claims.
    pages, cached = await research_website(query)
    researched = time.perf_counter()
    result = await generate_grounded_content(query, BRIEF_VIDEO, tone, length, pages, brief=brief)

    def review(typed: dict | None) -> list[str]:
        return selfcheck.failures(selfcheck.deterministic_checks(brief, typed or {}))

    warnings = review(result.typed)
    repaired = False
    if warnings and get_settings().format_repair:
        # One bounded correction pass, kept only if strictly better.
        try:
            candidate = await repair_content(query, BRIEF_VIDEO, tone, length, pages, result.typed or result.data, warnings, result.provider, brief=brief)
            remaining = review(candidate.typed)
            if len(remaining) < len(warnings):
                candidate.fallback_reason = result.fallback_reason
                result, warnings, repaired = candidate, remaining, True
        except Exception as exc:
            logger.warning("Brief repair failed (%s: %s); keeping the first answer", type(exc).__name__, classify_error(exc))

    finished = time.perf_counter()
    return AgentRun(
        result=result, pages=pages, cached=cached,
        research_ms=round((researched - started) * 1000), generation_ms=round((finished - researched) * 1000),
        format_warnings=warnings, format_repaired=repaired,
        humanize_note="Not applied to brief-driven scripts: a rewrite could change the approved hook, CTA or claim wording.",
        brief=brief,
    )


async def run_content_agent(
    query: str, content_type: str, tone: str, length: str, humanize: bool = True, humanize_level: str = "natural",
    brief: Brief | None = None,
) -> AgentRun:
    if brief is not None:
        return await _run_brief_agent(query, tone, length, brief)
    started = time.perf_counter()
    pages, cached = await research_website(query)
    researched = time.perf_counter()
    result = await generate_grounded_content(query, content_type, tone, length, pages)

    def review(data: dict) -> list[str]:
        return check_format(content_type, length, data) + check_risky_claims(data, site_texts(pages))

    warnings = review(result.data)
    repaired = False
    if warnings and get_settings().format_repair:
        # One correction pass. Keep it only if it is strictly better, and never let a failed
        # fix turn a usable answer into an error.
        try:
            candidate = await repair_content(
                query, content_type, tone, length, pages, result.typed or result.data, warnings, result.provider
            )
            remaining = review(candidate.data)
            if len(remaining) < len(warnings):
                candidate.fallback_reason = result.fallback_reason
                result, warnings, repaired = candidate, remaining, True
        except Exception as exc:
            logger.warning("Format repair failed (%s: %s); keeping the first answer", type(exc).__name__, classify_error(exc))

    # Last step: the natural-writing pass. Checks and repairs run first, so the rewrite is judged
    # against a draft that already meets the format. A draft that still misses requirements is not polished.
    original_content = None
    humanized = False
    humanize_note = None
    naturalness = None
    if humanize and get_settings().humanize_enabled:
        # A broken format blocks only the AI rewrite, which would be judged against a bad draft. The free
        # clean-up of stock filler and unsupported offers does not depend on the format, so it always runs.
        polish = await _polish(
            query, content_type, tone, length, pages, result, humanize_level,
            # A wrong count or length is a soft problem (the rewrite is rejected if it makes it worse);
            # a whole missing part is structural.
            allow_rewrite=not any(w.startswith("Missing") or "scene(s)" in w or "no VOICEOVER" in w for w in check_format(content_type, length, result.data)),
        )
        humanize_note, naturalness = polish.note, polish.naturalness
        if polish.changed:
            original_content = result.data
            result = LLMResult(polish.content, result.provider, result.model, result.fallback_reason)
            humanized = True
            warnings = review(result.data)

    finished = time.perf_counter()
    return AgentRun(
        result=result,
        pages=pages,
        cached=cached,
        research_ms=round((researched - started) * 1000),
        generation_ms=round((finished - researched) * 1000),
        format_warnings=warnings,
        format_repaired=repaired,
        original_content=original_content,
        humanized=humanized,
        humanize_note=humanize_note,
        humanize_level=humanize_level if humanize and get_settings().humanize_enabled else None,
        naturalness=naturalness,
    )
