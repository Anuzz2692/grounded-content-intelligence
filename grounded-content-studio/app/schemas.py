
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

from app.brief import Brief


class GenerateRequest(BaseModel):
    query: str = Field(min_length=3, max_length=2000)
    content_type: Literal[
        "article", "blog", "social_post", "video_script", "faq", "general"
    ] = "article"
    tone: str = Field(default="professional", min_length=2, max_length=80)
    length: Literal["concise", "standard", "detailed"] = "detailed"
    # Set false for a fast draft: skips brand validation and the human-review report.
    validate_content: bool = True
    # Rewrite the draft so it reads naturally. The rewrite is discarded if it changes facts or structure.
    humanize: bool = True
    # light: instant clean-up of stock filler phrases, no AI call. natural: an AI rewrite plus the clean-up.
    humanize_level: Literal["light", "natural"] = "natural"
    # Binding constraints for a calendar-driven, presenter-led video. Only valid for video_script.
    brief: Brief | None = None

    @model_validator(mode="after")
    def _brief_is_complete(self):
        if self.brief is None:
            return self
        if self.content_type != "video_script":
            raise ValueError("A content brief is only supported for video_script requests.")
        missing = self.brief.missing_for_video()
        if missing:
            raise ValueError("The content brief is missing required fields: " + ", ".join(missing) + ". Nothing is filled in on your behalf.")
        if self.brief.structure_problem():
            raise ValueError(self.brief.structure_problem())
        return self


class ContentSection(BaseModel):
    heading: str
    body: str


class Source(BaseModel):
    title: str
    url: HttpUrl
    relevance_score: float


class ContentPayload(BaseModel):
    title: str
    summary: str
    introduction: str
    sections: list[ContentSection]
    conclusion: str
    suggested_cta: str | None = None
    # Notes for the human reviewer (gaps, general-knowledge topics). Never part of the published text.
    reviewer_notes: list[str] = Field(default_factory=list)


class Correction(BaseModel):
    original_text: str
    suggested_text: str
    reason: str = ""


class GenerationMetadata(BaseModel):
    provider: Literal["anthropic", "ollama"]
    model: str
    cached_research: bool
    pages_considered: int
    latency_ms: int
    research_ms: int | None = None
    generation_ms: int | None = None
    # Set when the primary provider failed and Ollama produced the content.
    fallback_reason: str | None = None
    # Checks the code ran on the output (word counts, number of tags and so on).
    format_warnings: list[str] = Field(default_factory=list)
    # True when the first answer missed requirements and a second, corrected answer was used.
    format_repaired: bool = False
    content_type: str | None = None
    humanized: bool = False
    # Why the natural-writing pass was skipped or discarded, or what it did.
    humanize_note: str | None = None
    humanize_level: str | None = None
    # Counts of stock phrases and similar habits before and after the natural-writing pass.
    naturalness: dict[str, Any] | None = None


class GenerateResponse(BaseModel):
    success: bool
    query: str
    content: ContentPayload
    sources: list[Source]
    metadata: GenerationMetadata

    brand_validation: dict[str, Any] = Field(default_factory=dict)
    human_review: dict[str, Any] = Field(default_factory=dict)
    # One suggested change per risky sentence found by the code-level wording scan.
    wording_fixes: list[Correction] = Field(default_factory=list)
    # The draft before the natural-writing pass, kept so a reviewer can compare. None if nothing was rewritten.
    original_content: ContentPayload | None = None

    # Brief-driven videos only: script table, claims used, word count and the self-check report.
    brief_report: dict[str, Any] | None = None

    publication_status: Literal[
        "BLOCKED", "PENDING_REVIEW", "NOT_READY"
    ] = "NOT_READY"
