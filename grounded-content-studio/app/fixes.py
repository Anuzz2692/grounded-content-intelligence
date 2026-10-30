"""One concrete, reviewable suggestion per risky sentence.

The brand checker and the claim scanner sometimes return a single suggestion for several problems. The
risky-wording scan already knows exactly which sentences are the problem, so this turns each one
into its own "current text -> suggested text" pair that a reviewer can apply separately.

Suggestions only ever remove or weaken wording. They never add a claim.
"""
import re
from typing import Any

from app.format_checks import risky_matches

# Sections that hold metadata, not prose.
_SKIP_HEADINGS = {"tags", "hashtags"}
_FREE = re.compile(r"\bfree\s+(?=(?:first\s+|initial\s+)?(?:consultation|consult|visit|appointment|session)\b)", re.I)
_SENTENCE = re.compile(r"[^.!?]+(?:[.!?]+|$)")

_REASONS = {
    "statistic": "Removes a statistic that is not in the website research.",
    "absolute": "Removes a guarantee or absolute claim.",
    "superlative": "Removes a superlative the website research does not support.",
    "efficacy": "Removes a benefit or safety claim the website research does not support.",
    "custom": "Removes a claim that this company's profile marks as needing support, which the website research does not give.",
    "company_claim": "Removes a statement about what the company does that the website research does not support.",
    "offer": "Removes an offer that is not in the website research.",
    "free": "Removes \"free\": the website research does not mention a free offer.",
}


_CLAUSE_REASON = "Cuts the trailing clause that makes a claim the website research does not support."
_MIN_HEAD_WORDS = 4


def _trim_trailing_clause(sentence: str, risky_texts: list[str]) -> str | None:
    """If the earliest risky phrase sits in a clause after a comma, the sentence without that clause.

    "Learn about X, a key process that helps increase your chances." becomes "Learn about X."
    That keeps the part that is fine and works even when the sentence is the whole field.
    """
    start = min((sentence.lower().find(t.lower()) for t in risky_texts if t.lower() in sentence.lower()), default=-1)
    if start <= 0:
        return None
    comma = sentence.rfind(",", 0, start)
    if comma <= 0:
        return None
    head = sentence[:comma].rstrip()
    if len(head.split()) < _MIN_HEAD_WORDS:
        return None
    end = sentence.rstrip()[-1] if sentence.rstrip()[-1] in ".!?" else "."
    return head + end


def _sentences(text: str):
    """Yield each sentence as an exact substring of `text`."""
    for line in text.split("\n"):
        for m in _SENTENCE.finditer(line):
            sentence = m.group().strip()
            if sentence:
                yield sentence


def _slots(content: dict[str, Any]):
    for field in ("title", "summary", "introduction", "conclusion", "suggested_cta"):
        yield content.get(field) or ""
    for section in content.get("sections", []):
        if re.sub(r"[^a-z ]", "", section.get("heading", "").lower()).strip() in _SKIP_HEADINGS:
            continue
        yield section.get("body", "")


def suggest_wording_fixes(content: dict[str, Any], evidence_texts: list[str], limit: int = 12) -> list[dict[str, str]]:
    evidence = " ".join(evidence_texts).lower()
    fixes: list[dict[str, str]] = []
    seen: set[str] = set()

    for text in _slots(content):
        sentences = list(_sentences(text))
        for sentence in sentences:
            if sentence in seen:
                continue
            matches = risky_matches(sentence, evidence)
            if not matches:
                continue

            kinds = {kind for kind, _, _ in matches}
            only_free_offer = kinds == {"offer"} and all(_FREE.search(m) for _, m, _ in matches)
            if only_free_offer:
                suggested, reason = _FREE.sub("", sentence), _REASONS["free"]
            else:
                suggested = ""
                reason = _REASONS[sorted(kinds, key=("statistic", "absolute", "efficacy", "custom", "company_claim", "offer", "superlative").index)[0]]

            if not suggested:
                trimmed = _trim_trailing_clause(sentence, [m for _, m, _ in matches])
                if trimmed:
                    suggested, reason = trimmed, _CLAUSE_REASON

            # A change that would empty the whole field cannot be applied, so do not offer it.
            if not suggested and len(sentences) == 1:
                continue
            seen.add(sentence)
            fixes.append({"original_text": sentence, "suggested_text": suggested, "reason": reason})
            if len(fixes) >= limit:
                return fixes
    return fixes
