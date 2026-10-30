
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from app.agent import run_content_agent
from app.config import get_settings
from app.errors import LLMUnavailableError, ResearchError
from app.fixes import suggest_wording_fixes
from app import selfcheck
from app.company import load_profile
from app.schemas import (
    ContentPayload,
    GenerateRequest,
    GenerateResponse,
    GenerationMetadata,
    Source,
)
from app.security import require_access
from app.validation import (
    apply_self_check,
    validate_brand_content,
    prepare_human_review,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("content-agent")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if not settings.api_key_list:
        logger.warning(
            "API_KEYS is not set: the generate endpoint is unauthenticated. "
            "Set API_KEYS before exposing this service."
        )
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Grounded Content Studio",
    version="0.2.0",
    description=(
        "Generates website-grounded content with brand validation, "
        "code-level claim checks and a human-review gate."
    ),
)


async def _safe_validation(name: str, call, extra: dict) -> dict:
    """Await a validator; any failure becomes a REVIEW_REQUIRED result, never a pass."""
    try:
        return await call
    except Exception as exc:
        logger.exception("%s validation failed (%s)", name.capitalize(), type(exc).__name__)
        return {
            "validator": name,
            "status": "REVIEW_REQUIRED",
            "summary": (
                f"{name.capitalize()} validation could not be completed. "
                "Human review is required."
            ),
            **extra,
            "corrections": [],
            "requires_human_review": True,
            "validation_error": True,
        }


def _model_installed(configured: str, installed: list[str]) -> bool:
    # "mistral" means "mistral:latest" to Ollama.
    return configured in installed or (":" not in configured and f"{configured}:latest" in installed)


async def _ollama_status() -> dict:
    """Is Ollama reachable, and is the configured model pulled? Never raises."""
    settings = get_settings()
    status = {"reachable": False, "model": settings.ollama_model, "model_installed": None}
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(settings.ollama_base_url.rstrip("/") + "/api/tags")
            response.raise_for_status()
            names = [m.get("name", "") for m in response.json().get("models", [])]
    except (httpx.HTTPError, ValueError):
        return status
    status["reachable"] = True
    status["model_installed"] = _model_installed(settings.ollama_model, names)
    return status


@app.get("/health")
async def health():
    settings = get_settings()
    return {
        "status": "ok",
        "website": settings.website_base_url,
        "company": load_profile().public(),
        "llm_provider": settings.llm_provider,
        "primary_provider_configured": bool(settings.anthropic_api_key),
        "fallback": "ollama",
        "ollama": None if settings.llm_provider == "anthropic" else await _ollama_status(),
        "auth_enabled": bool(settings.api_key_list),
        "rate_limit_per_minute": settings.rate_limit_per_minute,
    }


@app.post(
    "/api/v1/content/generate",
    response_model=GenerateResponse,
    dependencies=[Depends(require_access)],
)
async def generate_content(request: GenerateRequest):
    started = time.perf_counter()

    try:
        run = await run_content_agent(
            query=request.query,
            content_type=request.content_type,
            tone=request.tone,
            length=request.length,
            humanize=request.humanize,
            humanize_level=request.humanize_level,
            **({"brief": request.brief} if request.brief is not None else {}),
        )
        result, pages, cached = run.result, run.pages, run.cached

        content = ContentPayload.model_validate(result.data)

        sources = [
            Source(
                title=page.title,
                url=page.url,
                relevance_score=page.score,
            )
            for page in pages
        ]

        content_data = content.model_dump()

        source_data = [
            {
                "title": source.title,
                "url": str(source.url),
                "relevance_score": source.relevance_score,
            }
            for source in sources
        ]

        brief_kw = {"brief": request.brief} if request.brief is not None else {}
        if request.validate_content:
            brand_result = await _safe_validation(
                "brand",
                validate_brand_content(query=request.query, content=content_data, pages=pages, **brief_kw),
                {"issues": []},
            )

            # Code-level self-check failures can only lower a validator's verdict.
            blockers, open_items = [], []
            if request.brief is not None:
                det = selfcheck.deterministic_checks(request.brief, run.result.typed or {})
                apply_self_check(brand_result, det)
                blockers = selfcheck.failures(det)
                open_items = [f"{c['name']}: {c['detail']}" for c in det if c["status"] in {"REVIEW_REQUIRED", "UNVERIFIED"}]

            # Prepare a review report; this does not approve publication.
            try:
                review_result = await prepare_human_review(
                    query=request.query,
                    content=content_data,
                    brand_result=brand_result,
                    sources=source_data,
                    **({"blockers": blockers} if blockers else {}),
                    **({"self_check_items": open_items + run.format_warnings} if (open_items or run.format_warnings) else {}),
                )
            except Exception as exc:
                logger.exception(
                    "Human-review preparation failed (%s)", type(exc).__name__
                )
                review_result = {
                    "review_preparation": "1.0",
                    "status": "NOT_READY",
                    "content_purpose": request.query,
                    "accuracy_concerns": [
                        "Review preparation could not be completed."
                    ],
                    "brand_concerns": [],
                    "evidence_gaps": [],
                    "conflicts": [],
                    "questions_for_reviewer": [
                        "Investigate the review preparation failure."
                    ],
                    "recommended_next_action": "GATHER_EVIDENCE",
                    "approval_authority": "Authorised human reviewer only",
                    "publication_authorised": False,
                }
        else:
            brand_result = {"status": "NOT_RUN", "summary": "Validation was skipped."}
            review_result = {
                "review_preparation": "1.0",
                "status": "NOT_READY",
                "content_purpose": request.query,
                "accuracy_concerns": ["Validation was skipped; this is an unreviewed draft."],
                "brand_concerns": [],
                "evidence_gaps": [],
                "conflicts": [],
                "questions_for_reviewer": [],
                "recommended_next_action": "REVIEW_CONTENT",
                "approval_authority": "Authorised human reviewer only",
                "publication_authorised": False,
            }

        review_status = review_result.get("status")

        # Never allow this generation endpoint to publish or approve content.
        if review_status == "BLOCKED":
            publication_status = "BLOCKED"
        elif review_status == "PENDING_REVIEW":
            publication_status = "PENDING_REVIEW"
        else:
            publication_status = "NOT_READY"

        review_result["publication_authorised"] = False

        brief_report = None
        if request.brief is not None:
            brief_report = selfcheck.build_report(request.brief, run.result.typed or {}, brand_result)
            if brief_report["overall"] == "FAIL":
                publication_status = "BLOCKED"

        return GenerateResponse(
            success=True,
            query=request.query,
            content=content,
            sources=sources,
            metadata=GenerationMetadata(
                provider=result.provider,
                model=result.model,
                cached_research=cached,
                pages_considered=len(pages),
                research_ms=run.research_ms,
                generation_ms=run.generation_ms,
                fallback_reason=result.fallback_reason,
                format_warnings=run.format_warnings,
                format_repaired=run.format_repaired,
                content_type=request.content_type,
                humanized=run.humanized,
                humanize_note=run.humanize_note,
                humanize_level=run.humanize_level,
                naturalness=run.naturalness,
                latency_ms=round(
                    (time.perf_counter() - started) * 1000
                ),
            ),
            brand_validation=brand_result,
            human_review=review_result,
            wording_fixes=suggest_wording_fixes(content_data, [p.text for p in pages]),
            original_content=ContentPayload.model_validate(run.original_content) if run.original_content else None,
            publication_status=publication_status,
            brief_report=brief_report,
        )

    except ResearchError as exc:
        logger.error("Website research failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="The website could not be read. Try again shortly.",
        ) from exc
    except LLMUnavailableError as exc:
        logger.error("All LLM providers failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=(
                "No LLM provider could generate content. "
                f"Reasons: {exc.reasons}"
            ),
        ) from exc
    except Exception as exc:
        logger.exception(
            "Content generation request failed (%s)", type(exc).__name__
        )
        raise HTTPException(
            status_code=502,
            detail=(
                "Content generation failed. Check server logs and confirm "
                "the website and LLM providers are available."
            ),
        ) from exc


FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def mount_frontend(application: FastAPI, dist: Path) -> bool:
    """Serve the built React app at "/". Must run after every API route is registered,
    because a mount at "/" matches anything the routes before it did not."""
    if not (dist / "index.html").is_file():
        return False
    application.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return True


if not mount_frontend(app, FRONTEND_DIST):
    logger.info("frontend/dist not found; API only. Run `npm run build` in frontend/ to serve the UI.")
