"""Checks on generated content that the model was told to satisfy but may miss.

The prompts ask for exact counts (15 hashtags, 5 FAQs) and word ranges. Models, especially small
local ones, often miss them, so the code verifies and reports. Warnings never block a response;
they tell a reviewer what to look at.
"""
import re
from functools import lru_cache
from typing import Any

# A range is allowed to be missed by this fraction before it is reported.
TOLERANCE = 0.10

WEBSITE_WORDS = {"concise": (400, 600), "standard": (800, 1100), "detailed": (1400, 1800)}
FAQ_QUESTIONS = {"concise": 3, "standard": 5, "detailed": 8}
TAG_COUNT = 15


def _words(text: str) -> int:
    return len(re.findall(r"[\w'’-]+", text))


def _norm(heading: str) -> str:
    return re.sub(r"[^a-z ]", "", heading.lower()).strip()


def _find(sections: list[dict[str, Any]], *needles: str) -> dict[str, Any] | None:
    for section in sections:
        heading = _norm(section.get("heading", ""))
        if any(n in heading for n in needles):
            return section
    return None


def _is_faq(section: dict[str, Any]) -> bool:
    heading = _norm(section.get("heading", ""))
    return "frequently asked" in heading or heading in {"faq", "faqs"}


def _is_paa(section: dict[str, Any]) -> bool:
    return "people also ask" in _norm(section.get("heading", ""))


def _list_items(body: str) -> list[str]:
    parts = re.split(r"[,\n]", body)
    return [p.strip(" -•\t") for p in parts if p.strip(" -•\t")]


def _range_warning(label: str, count: int, low: int, high: int, tolerance: float = TOLERANCE) -> str | None:
    if low * (1 - tolerance) <= count <= high * (1 + tolerance):
        return None
    return f"{label} is {count} words; the target is {low}-{high}."


def _exact(label: str, found: int, expected: int) -> str | None:
    return None if found == expected else f"Expected {expected} {label} but found {found}."


def _tags_and_hashtags(sections: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    tags = _find(sections, "tags")
    # "Hashtags" also contains "tags", so find it first and keep the two apart.
    hashtags = _find(sections, "hashtags")
    if hashtags is tags:
        tags = next((s for s in sections if _norm(s.get("heading", "")) == "tags"), None)
    if tags is None:
        out.append('Missing the "Tags" section.')
    else:
        out.append(_exact("tags", len(_list_items(tags["body"])), TAG_COUNT))
    if hashtags is None:
        out.append('Missing the "Hashtags" section.')
    else:
        out.append(_exact("hashtags", len(re.findall(r"#\w+", hashtags["body"])), TAG_COUNT))
    return out


def check_format(content_type: str, length: str, content: dict[str, Any]) -> list[str]:
    sections = content.get("sections", [])
    warnings: list[str | None] = []

    if content_type in {"article", "blog"}:
        main = [s for s in sections if not _is_faq(s) and not _is_paa(s)]
        count = _words(content.get("introduction", "")) + sum(_words(s["body"]) for s in main) + _words(content.get("conclusion", ""))
        low, high = WEBSITE_WORDS.get(length, WEBSITE_WORDS["standard"])
        warnings.append(_range_warning("The main article", count, low, high))

        if length == "detailed":
            faq = next((s for s in sections if _is_faq(s)), None)
            paa = next((s for s in sections if _is_paa(s)), None)
            if faq is None:
                warnings.append('Missing the "Frequently Asked Questions" section.')
            else:
                warnings.append(_exact("FAQs", len(re.findall(r"(?im)^\s*Q\d*\s*[:.)]", faq["body"])), 5))
            if paa is None:
                warnings.append('Missing the "People Also Ask" section.')
            else:
                warnings.append(_exact("People Also Ask questions", len(_list_items(paa["body"])), 5))

    elif content_type == "social_post":
        caption = _find(sections, "caption")
        if caption is None:
            warnings.append('Missing the "Caption" section.')
        else:
            warnings.append(_range_warning("The caption", _words(caption["body"]), 30, 50, tolerance=0))
        warnings.extend(_tags_and_hashtags(sections))

    elif content_type == "video_script":
        warnings.append(_range_warning("The video title", _words(content.get("title", "")), 5, 9, tolerance=0))

        screenplay = _find(sections, "screenplay", "script")
        if screenplay is None or not screenplay["body"].strip():
            warnings.append('Missing the "Screenplay" section.')
        else:
            body = screenplay["body"]
            scenes = len(re.findall(r"(?im)^\s*scene\s*\d+", body))
            if scenes < 2:
                warnings.append(f"The screenplay has {scenes} scene(s); it needs at least 2.")
            if not re.search(r"(?im)^\s*voice[- ]?over\s*:", body):
                warnings.append("The screenplay has no VOICEOVER lines.")

        options = _find(sections, "hook")
        if options is None:
            warnings.append('Missing the "Title and Hook Options" section.')
        else:
            warnings.append(_exact("title and hook options", len(re.findall(r"(?m)^\s*\d+\s*[.)]", options["body"])), 3))

        caption = _find(sections, "caption")
        if caption is None:
            warnings.append('Missing the "Caption" section.')
        else:
            warnings.append(_range_warning("The caption", _words(caption["body"]), 30, 60, tolerance=0))

        warnings.extend(_tags_and_hashtags(sections))
        if not (content.get("suggested_cta") or "").strip():
            warnings.append("Missing the call to action.")

    elif content_type == "faq":
        expected = FAQ_QUESTIONS.get(length, 5)
        warnings.append(_exact("questions", len(sections), expected))

    return [w for w in warnings if w]


# --- wording the model was told never to use -------------------------------------------------

_PERCENT = re.compile(r"\d{1,3}(?:\.\d+)?(?:\s?(?:-|\u2013|to)\s?\d{1,3}(?:\.\d+)?)?\s?%")
_ABSOLUTE = re.compile(r"\b(guarantee[sd]?|risk[- ]free|completely safe|totally safe|pain[- ]?free|100\s?%)", re.I)
_OFFER = re.compile(r"\b(free (?:first |initial )?(?:consultation|consult|visit|appointment|session)|discount\w*|limited[- ]time|\d+\s?% off)", re.I)
_EFFICACY = re.compile(
    r"\b(?:(?:boost|increase|improve|maximi[sz]e|enhance|raise)s?(?:\s+your)?\s+(?:chances|odds|likelihood)(?:\s+of\s+\w+)?"
    r"|safe and effective|ensur(?:e|es|ing)\s+(?:safety|success|the best)"
    r"|proven (?:to|results)|(?:highest|best) success"
    r"|maximi[sz](?:e|es|ing)\s+(?:your\s+)?(?:success|results|outcomes|savings)"
    r"|(?:improv|enhanc)(?:e|es|ing)\s+(?:your\s+)?(?:performance|outcomes|success|results))\b",
    re.I,
)
_SUPERLATIVE = re.compile(r"\b(best|number one|#1|most advanced|highest success|top[- ]rated|world[- ]class)\b", re.I)


def _visible_text(content: dict[str, Any]) -> str:
    """Everything a reader would see. reviewer_notes are for the reviewer and are excluded."""
    parts = [content.get(k) or "" for k in ("title", "summary", "introduction", "conclusion", "suggested_cta")]
    for section in content.get("sections", []):
        parts += [section.get("heading", ""), section.get("body", "")]
    return "\n".join(parts)


# --- statements about what the company does ---------------------------------------------------------

@lru_cache(maxsize=8)
def _self_reference(name: str) -> re.Pattern:
    """Words by which the text speaks about the company itself: we / our / us, or "At <company name>"."""
    return re.compile(r"\b(?:we|our|us)\b|\bat\s+" + re.escape(name).replace(r"\ ", r"\s+") + r"\b", re.I)


def _profile():
    from app.company import load_profile
    return load_profile()
_SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?]*")
# Invitations and questions say nothing about how the company works.
_IMPERATIVE = re.compile(r"^\W*(?:book|call|contact|visit|ask|speak|talk|schedule|learn|find|see|read|explore|discover|reach|get|start|take|bring|write)\b", re.I)
_STOP = frozenset("that this with from have will your about their which there these those them they been were what when where while also than then into such only over more most other some very just like make made does".split())
MIN_CLAIM_STEMS = 4
MIN_GROUNDING = 0.5


def _stems(text: str) -> frozenset[str]:
    # Five-letter stems: "tailor", "tailors", "tailored" all become "tailo".
    return frozenset(w[:5] for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in _STOP)


@lru_cache(maxsize=8)
def _evidence_stems(evidence: str) -> frozenset[str]:
    return _stems(evidence)


def ungrounded_company_claims(text: str, evidence: str) -> list[str]:
    """Sentences that say what "we" or the company do, in words the website research mostly lacks.

    This is a vocabulary check, not understanding: it cannot prove a claim true, but a sentence
    about the company's own practice that shares almost nothing with the research is not grounded.
    """
    known = _evidence_stems(evidence)
    flagged = []
    for match in _SENTENCE_RE.finditer(text):
        sentence = match.group().strip()
        if not sentence or sentence.endswith("?") or _IMPERATIVE.match(sentence) or not _self_reference(_profile().name).search(sentence):
            continue
        stems = _stems(sentence)
        if len(stems) >= MIN_CLAIM_STEMS and len(stems & known) / len(stems) < MIN_GROUNDING:
            flagged.append(sentence)
    return flagged


def risky_matches(text: str, evidence: str) -> list[tuple[str, str, str]]:
    """Every risky phrase in `text` as (kind, matched text, message). `evidence` is lower-case research text.

    A phrase that the research itself contains is allowed.
    """
    found: list[tuple[str, str, str]] = []
    for match in _PERCENT.finditer(text):
        number_forms = re.findall(r"\d+(?:\.\d+)?", match.group())
        if not any(f"{n}%" in evidence.replace(" %", "%") for n in number_forms):
            found.append(("statistic", match.group(), f'Contains a statistic ("{match.group().strip()}") that is not in the website research.'))
    for match in _ABSOLUTE.finditer(text):
        found.append(("absolute", match.group(), f'Uses absolute or guarantee wording ("{match.group()}").'))
    profile = _profile()
    for match in _OFFER.finditer(text):
        if match.group().lower() not in evidence:
            found.append(("offer", match.group(), f'Mentions an offer ("{match.group()}") that is not in the website research.'))
    for match in _EFFICACY.finditer(text):
        if match.group().lower() not in evidence:
            found.append(("efficacy", match.group(), f'Claims a benefit or result that the website research does not support ("{match.group()}").'))
    # Wording this company's profile lists as a claim that needs support from its own website.
    for label, pattern in profile.risky_terms:
        for match in re.finditer(pattern, text, re.I):
            if match.group().lower() not in evidence:
                found.append(("custom", match.group(), f'Makes a claim ("{match.group()}") that the website research does not support.'))
    for sentence in ungrounded_company_claims(text, evidence):
        short = sentence if len(sentence) <= 70 else sentence[:67].rstrip() + "..."
        found.append(("company_claim", sentence, f'Says what the company does in terms the website research does not support ("{short}").'))
    for match in _SUPERLATIVE.finditer(text):
        if match.group().lower() not in evidence:
            found.append(("superlative", match.group(), f'Uses a superlative ("{match.group()}") that the website research does not support.'))
    return found


def check_risky_claims(content: dict[str, Any], evidence_texts: list[str]) -> list[str]:
    """Flag statistics, promises, offers and superlatives that the website research does not contain.

    Small models often ignore the "no invented claims" rule, so the code checks for the most
    damaging kinds directly.
    """
    messages: list[str] = []
    for _, _, message in risky_matches(_visible_text(content), " ".join(evidence_texts).lower()):
        if message not in messages:
            messages.append(message)
    return messages[:8]


# Public names for other modules.
visible_text = _visible_text
count_words = _words
normalise_heading = _norm
