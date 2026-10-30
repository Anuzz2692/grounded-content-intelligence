"""The safety net around the natural-writing pass.

A model asked to make text read more naturally can also change what it says. So its rewrite is
only a candidate: it is used only if it keeps the draft's facts and structure, and otherwise the
original wording is kept. Anything the application depends on (the Tags and Hashtags text, exact
section names) is restored from the original instead of being trusted to the model.
"""
import copy
import re
from dataclasses import dataclass
from typing import Any

from app.naturalness import analyse
from app.format_checks import (
    check_format,
    check_risky_claims,
    count_words,
    normalise_heading,
    visible_text,
)

# Section bodies that are copied back unchanged.
VERBATIM_HEADINGS = {"tags", "hashtags"}
# Section headings the checks and the page look for; they keep their exact original wording.
FIXED_HEADINGS = VERBATIM_HEADINGS | {
    "frequently asked questions",
    "people also ask",
    "screenplay",
    "title and hook options",
    "caption",
    "carousel slides",
}
# A rewrite is allowed to tighten text, but not to gut it or pad it.
MIN_WORD_RATIO = 0.6
MAX_WORD_RATIO = 1.3
MAX_NEW_NOTES = 3

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_SCENE_LINE = re.compile(r"(?im)^\s*scene\s*\d+.*$")
_CONTACT = re.compile(r"https?://\S+|\b[\w.+-]+@[\w-]+\.[\w.]+\b|www\.\S+", re.I)


@dataclass
class Outcome:
    content: dict[str, Any] | None  # the rewrite to use, or None to keep the original
    note: str  # a plain-language explanation for the reviewer
    changed: bool = False
    before: dict[str, Any] | None = None  # naturalness measurements of the draft
    after: dict[str, Any] | None = None  # ... and of the accepted rewrite


def _numbers(content: dict[str, Any]) -> set[str]:
    # Scene time ranges are layout, not facts, so they do not count.
    return set(_NUMBER.findall(_SCENE_LINE.sub("", visible_text(content))))


def _contacts(content: dict[str, Any]) -> set[str]:
    return {m.lower().rstrip(".,)") for m in _CONTACT.findall(visible_text(content))}


def _prose_words(content: dict[str, Any]) -> int:
    kept = {**content, "sections": [s for s in content.get("sections", []) if normalise_heading(s.get("heading", "")) not in VERBATIM_HEADINGS]}
    return count_words(visible_text(kept))


def _restore(original: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Put back everything the model is not allowed to change."""
    fixed = copy.deepcopy(candidate)
    for original_section, section in zip(original["sections"], fixed["sections"]):
        heading = normalise_heading(original_section["heading"])
        if heading in FIXED_HEADINGS:
            section["heading"] = original_section["heading"]
        if heading in VERBATIM_HEADINGS:
            section["body"] = original_section["body"]

    if not (original.get("suggested_cta") or "").strip():
        fixed["suggested_cta"] = None  # never add a call to action
    elif not (fixed.get("suggested_cta") or "").strip():
        fixed["suggested_cta"] = original["suggested_cta"]

    notes = list(original.get("reviewer_notes") or [])
    new = [n for n in (fixed.get("reviewer_notes") or []) if n not in notes]
    fixed["reviewer_notes"] = notes + new[:MAX_NEW_NOTES]
    return fixed


def accept_rewrite(
    original: dict[str, Any],
    candidate: dict[str, Any],
    content_type: str,
    length: str,
    evidence_texts: list[str],
) -> Outcome:
    if len(candidate.get("sections", [])) != len(original.get("sections", [])):
        return Outcome(None, "Kept the original wording: the rewrite changed the number of sections.")

    fixed = _restore(original, candidate)
    if fixed == original:
        return Outcome(None, "The draft already read naturally, so no changes were made.")

    new_numbers = sorted(_numbers(fixed) - _numbers(original))
    if new_numbers:
        return Outcome(None, f"Kept the original wording: the rewrite introduced numbers that were not in the draft ({', '.join(new_numbers[:4])}).")

    if _contacts(fixed) - _contacts(original):
        return Outcome(None, "Kept the original wording: the rewrite added a link or contact detail.")

    new_risks = [m for m in check_risky_claims(fixed, evidence_texts) if m not in check_risky_claims(original, evidence_texts)]
    if new_risks:
        return Outcome(None, f"Kept the original wording: the rewrite introduced flagged wording. {new_risks[0]}")

    before, after = check_format(content_type, length, original), check_format(content_type, length, fixed)
    if len(after) > len(before):
        worse = [w for w in after if w not in before]
        return Outcome(None, f"Kept the original wording: the rewrite broke the required format. {worse[0] if worse else ''}".strip())

    before_report, after_report = analyse(original), analyse(fixed)
    if after_report.issues > before_report.issues:
        return Outcome(None, "Kept the original wording: the rewrite used more stock phrasing than the draft had.")

    original_words = _prose_words(original)
    if original_words >= 80:
        ratio = _prose_words(fixed) / original_words
        if not MIN_WORD_RATIO <= ratio <= MAX_WORD_RATIO:
            return Outcome(None, f"Kept the original wording: the rewrite changed the length too much ({round(ratio * 100)}% of the draft).")

    return Outcome(fixed, "Rewritten for natural flow. Check the original draft if a meaning looks changed.", changed=True,
                   before=before_report.as_dict(), after=after_report.as_dict())
