"""The content brief: binding constraints for a calendar-driven, presenter-led video.

Everything here comes from the request. Nothing is defaulted to an approved hook, CTA, claim or
hashtag: if the brief does not supply one, the request is rejected before any model is called.
"""
import json
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

# Word budget for spoken delivery: (duration - 5) * 2.3, tolerance +/-10%. An estimate, not a timer.
WORDS_PER_SECOND = 2.3
WORD_BUDGET_LEAD_SECONDS = 5
WORD_TOLERANCE = 0.10
# Default structure for a 60 second Reel; a brief can supply its own segments.
DEFAULT_60S_SEGMENTS = [("Hook", 4), ("Insight", 10), ("Explanation", 34), ("Takeaway", 8), ("CTA", 4)]


class Claim(BaseModel):
    id: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9._-]+$")
    statement: str = Field(min_length=3, max_length=600)


class Segment(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    seconds: int = Field(gt=0, le=300)


class Brief(BaseModel):
    slot_id: str = Field(default="", max_length=40)
    topic: str = Field(default="", max_length=300)
    objective: str = Field(default="", max_length=400)
    platform: str = Field(default="", max_length=80)
    duration_seconds: int | None = Field(default=None, ge=10, le=300)
    presenter: str = Field(default="", max_length=120)
    spoken_language: str = Field(default="", max_length=60)
    subtitle_language: str = Field(default="", max_length=60)
    approved_hook: str = Field(default="", max_length=300)
    approved_cta: str = Field(default="", max_length=300)
    approved_claims: list[Claim] = Field(default_factory=list, max_length=40)
    approved_hashtags: list[str] = Field(default_factory=list, max_length=30)
    required_title: str = Field(default="", max_length=200)
    caption_requirements: str = Field(default="", max_length=500)
    required_disclaimer: str = Field(default="", max_length=300)
    segments: list[Segment] = Field(default_factory=list, max_length=12)
    brand_restrictions: list[str] = Field(default_factory=list, max_length=30)
    extra_constraints: list[str] = Field(default_factory=list, max_length=20)
    # A continuous talking-head video may repeat one shot; otherwise a shot is used at most twice.
    continuous_talking_head: bool = False

    @field_validator("approved_hashtags")
    @classmethod
    def _hashtags(cls, values: list[str]) -> list[str]:
        out = []
        for value in values:
            tag = value.strip()
            if tag and not tag.startswith("#"):
                tag = "#" + tag
            if tag:
                out.append(tag)
        return out

    @field_validator("brand_restrictions", "extra_constraints")
    @classmethod
    def _strip(cls, values: list[str]) -> list[str]:
        return [v.strip() for v in values if v.strip()]

    def missing_for_video(self) -> list[str]:
        """Fields a presenter-led video cannot be written without. Nothing is invented to fill them."""
        missing = []
        if not self.duration_seconds:
            missing.append("duration_seconds")
        if not self.approved_hook.strip():
            missing.append("approved_hook")
        if not self.approved_cta.strip():
            missing.append("approved_cta")
        if not self.approved_claims:
            missing.append("approved_claims")
        ids = [c.id.lower() for c in self.approved_claims]
        if len(ids) != len(set(ids)):
            missing.append("approved_claims (duplicate ids)")
        return missing

    def structure(self) -> list[tuple[str, int]]:
        """The segment template: the brief's own, else the 60-second default, else none."""
        if self.segments:
            return [(s.name, s.seconds) for s in self.segments]
        if self.duration_seconds == 60:
            return list(DEFAULT_60S_SEGMENTS)
        return []

    def structure_problem(self) -> str | None:
        structure = self.structure()
        if structure and self.duration_seconds and sum(s for _, s in structure) != self.duration_seconds:
            return f"The segment durations add up to {sum(s for _, s in structure)} seconds, not {self.duration_seconds}."
        return None

    def claim_map(self) -> dict[str, str]:
        return {c.id.lower(): c.statement for c in self.approved_claims}


def word_budget(duration_seconds: int) -> tuple[float, int, int]:
    """(target, minimum, maximum) spoken words for a duration."""
    target = max(duration_seconds - WORD_BUDGET_LEAD_SECONDS, 0) * WORDS_PER_SECOND
    return target, round(target * (1 - WORD_TOLERANCE)), round(target * (1 + WORD_TOLERANCE))


def count_words(text: str) -> int:
    """Spoken words: runs of letters/digits, with apostrophes and hyphens kept inside a word."""
    return len(re.findall(r"[^\W_]+(?:['’\-][^\W_]+)*", text))


def normalise(text: str) -> str:
    """The only normalisation allowed when comparing approved text: surrounding and repeated whitespace."""
    return re.sub(r"\s+", " ", text).strip()


def brief_block(brief: Brief) -> str:
    """The brief as data for the prompt. The model sees the approved text verbatim."""
    data: dict[str, Any] = brief.model_dump(exclude_defaults=True)
    data["segments"] = [{"name": n, "seconds": s} for n, s in brief.structure()]
    if brief.duration_seconds:
        target, low, high = word_budget(brief.duration_seconds)
        data["spoken_word_budget"] = {"target": round(target), "minimum": low, "maximum": high}
    text = json.dumps(data, ensure_ascii=False, indent=1).replace("</", "<\\/")
    return f"\n<content_brief>\n{text}\n</content_brief>"
