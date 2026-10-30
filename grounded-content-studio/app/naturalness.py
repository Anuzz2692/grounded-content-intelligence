"""Measuring and tidying stiff, formulaic writing.

These are editorial measurements, not an AI-detector score and not a claim that text "passes as
human". They count specific, fixable habits: stock phrases, repeated sentence openers, stacked
questions, exclamation marks. Counting them before and after a rewrite shows whether it helped, and
listing them tells the rewrite what to fix. The cleanup only deletes or simplifies filler; it never
adds information.
"""
import re
import statistics
from dataclasses import dataclass, field
from typing import Any

# Stock phrases that usually add nothing. Not a banned-word list: they are flagged, and removed
# only where the cleanup below can do it without changing meaning.
PHRASES = [
    r"in today(?:'|’)s (?:fast-paced |digital |modern |ever-changing )?(?:world|age|era|landscape)",
    r"let(?:'|’)s (?:dive|delve) (?:into|in)\b",
    r"\b(?:dive|delve) (?:deep )?into\b",
    r"it(?:'|’)?s (?:important|worth|crucial) (?:to note|noting|to remember|to understand)(?: that)?",
    r"it is (?:important|worth|crucial) (?:to note|noting|to remember|to understand)(?: that)?",
    r"it goes without saying",
    r"in conclusion",
    r"when it comes to",
    r"embark(?:ing)? on (?:your|this|a|the) (?:\w+ )?journey",
    r"navigat(?:e|ing) the complexit(?:y|ies) of",
    r"unlock(?:ing)? the power of",
    r"a comprehensive guide",
    r"rest assured",
    r"every journey is unique",
    r"at the end of the day",
    r"plays? a (?:crucial|vital|pivotal|key) role",
    r"a testament to",
    r"in the realm of",
    r"ever-evolving",
    r"game[- ]changer",
    r"cutting[- ]edge",
    r"state[- ]of[- ]the[- ]art",
    r"\bwhether you(?:'|’)re\b",
    r"you(?:'|’)re not alone",
    r"take the (?:first|next) step",
    # Advertising language that reads as boilerplate.
    r"(?:your|their) unique needs",
    r"tailor(?:s|ed)? (?:each|every|your|a|an)? ?[\w ]{0,20}to your",
    r"a (?:crucial|key|vital|essential) (?:step|process|part|component) (?:in|of)",
    r"(?:book|call|contact|schedule|visit)\b[^.!?\n]{0,40}\btoday\b",
    r"(?:ready|looking) to (?:take|learn|start|begin|explore)\b",
    r"your dream of (?:parenthood|becoming|having)",
    r"don(?:'|’)t wait",
    r"learn more!",
]
_PHRASE_RES = [re.compile(p, re.I) for p in PHRASES]

# Openers that repeat naturally and are not worth flagging.
_COMMON_OPENERS = {"the", "a", "an", "this", "it", "and", "but", "in", "on", "for", "to", "of", "you", "your", "we", "our", "if", "there"}
# Headings whose text is metadata, not prose.
_NOT_PROSE = {"tags", "hashtags", "title and hook options", "frequently asked questions", "people also ask", "carousel slides"}

_SENTENCE = re.compile(r"[^.!?\n]+[.!?]*")
JOURNEY_LIMIT = 2
MAX_QUESTIONS = 2
MAX_EXCLAMATIONS = 1
UNIFORM_RHYTHM = 0.35  # variation of sentence length below this reads as monotone


@dataclass
class Report:
    phrases: list[str] = field(default_factory=list)  # each stock phrase found, in order
    repeated_openers: int = 0
    questions: int = 0
    exclamations: int = 0
    journey: int = 0
    sentences: int = 0
    rhythm: float | None = None  # coefficient of variation of sentence length
    issues: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "issues": self.issues,
            "phrases": len(self.phrases),
            "repeated_openers": self.repeated_openers,
            "questions": self.questions,
            "exclamations": self.exclamations,
            "rhythm": None if self.rhythm is None else round(self.rhythm, 2),
        }


def _norm(heading: str) -> str:
    return re.sub(r"[^a-z ]", "", heading.lower()).strip()


def prose_parts(content: dict[str, Any]) -> list[str]:
    """The pieces of text a reader would read as writing."""
    parts = [content.get(k) or "" for k in ("summary", "introduction", "conclusion")]
    for section in content.get("sections", []):
        if _norm(section.get("heading", "")) not in _NOT_PROSE:
            parts.append(section.get("body", ""))
    return [p for p in parts if p.strip()]


def _sentences(text: str) -> list[str]:
    # Scene labels and similar prefixes are layout, not sentences.
    text = re.sub(r"(?im)^\s*(?:scene\s*\d+[^\n]*|visual\s*:[^\n]*|on[- ]screen text\s*:[^\n]*)$", "", text)
    text = re.sub(r"(?im)^\s*voice[- ]?over\s*:\s*", "", text)
    return [s.strip() for s in _SENTENCE.findall(text) if len(s.strip()) > 2]


def _phrase_matches(text: str) -> list[str]:
    """Stock phrases in `text`, counting overlapping matches once (the longest wins)."""
    spans = sorted(((m.start(), m.end()) for rx in _PHRASE_RES for m in rx.finditer(text)), key=lambda s: (s[0], -(s[1] - s[0])))
    kept: list[tuple[int, int]] = []
    for start, end in spans:
        if kept and start < kept[-1][1]:
            continue
        kept.append((start, end))
    return [text[a:b].strip() for a, b in kept]


def analyse(content: dict[str, Any]) -> Report:
    report = Report()
    lengths: list[int] = []

    for part in prose_parts(content):
        report.phrases += _phrase_matches(part)
        report.journey += len(re.findall(r"\bjourney\b", part, re.I))
        previous = ""
        for sentence in _sentences(part):
            report.sentences += 1
            lengths.append(len(sentence.split()))
            first = re.sub(r"[^a-z']", "", sentence.split()[0].lower()) if sentence.split() else ""
            if first and first == previous and first not in _COMMON_OPENERS:
                report.repeated_openers += 1
            previous = first
            report.questions += sentence.endswith("?")
            report.exclamations += sentence.count("!")

    if len(lengths) >= 6 and statistics.mean(lengths):
        report.rhythm = statistics.pstdev(lengths) / statistics.mean(lengths)

    report.issues = (
        len(report.phrases)
        + report.repeated_openers
        + max(0, report.questions - MAX_QUESTIONS)
        + max(0, report.exclamations - MAX_EXCLAMATIONS)
        + (1 if report.journey > JOURNEY_LIMIT else 0)
    )
    return report


def editing_notes(report: Report) -> str:
    """Specific problems for the rewrite to fix, as short lines. Empty if there is nothing to say."""
    notes = []
    if report.phrases:
        counts: dict[str, int] = {}
        for phrase in report.phrases:
            counts[phrase.lower()] = counts.get(phrase.lower(), 0) + 1
        listed = ", ".join(f'"{p}"' + (f" (x{n})" if n > 1 else "") for p, n in list(counts.items())[:8])
        notes.append(f"Stock phrases to rewrite or remove: {listed}.")
    if report.repeated_openers:
        notes.append(f"{report.repeated_openers} sentence(s) start with the same word as the sentence before. Vary the openings.")
    if report.questions > MAX_QUESTIONS:
        notes.append(f"{report.questions} rhetorical questions. Keep at most {MAX_QUESTIONS}.")
    if report.exclamations > MAX_EXCLAMATIONS:
        notes.append(f"{report.exclamations} exclamation marks. Keep at most {MAX_EXCLAMATIONS}.")
    if report.journey > JOURNEY_LIMIT:
        notes.append(f'The word "journey" appears {report.journey} times. Use it once at most.')
    if report.rhythm is not None and report.rhythm < UNIFORM_RHYTHM:
        notes.append("Sentence lengths are very uniform. Mix short and longer sentences.")
    return "\n".join(f"- {n}" for n in notes)


# --- deterministic cleanup -----------------------------------------------------------------------

# (pattern, replacement). An empty replacement deletes the phrase, and the next letter is capitalised
# when the phrase started a sentence.
_CLEANUPS = [
    (r"in today(?:'|’)s (?:fast-paced |digital |modern |ever-changing )?(?:world|age|era|landscape),?\s*", ""),
    (r"it(?:'|’)?s (?:important|worth|crucial) (?:to note|noting|to remember|to understand)(?: that)?\s*", ""),
    (r"it is (?:important|worth|crucial) (?:to note|noting|to remember|to understand)(?: that)?\s*", ""),
    (r"it goes without saying(?: that)?,?\s*", ""),
    (r"rest assured,?\s*", ""),
    (r"in conclusion,?\s*", ""),
    (r"at the end of the day,?\s*", ""),
    (r"let(?:'|’)s (?:dive|delve) (?:in|into)\b", "let's look at"),
    (r"(?:dive|delve) (?:deep )?into\b", "look at"),
    (r"a comprehensive guide to\b", "a guide to"),
    (r"navigat(?:e|ing) the complexit(?:y|ies) of\b", "understanding"),
    (r"\bevery journey is unique,?\s*", ""),
]
# "free consultation" is an offer. Unless the website itself says it, it is an invented claim, and
# deleting the word "free" leaves a sentence that is still true.
_FREE_OFFER = re.compile(r"\bfree\s+((?:first\s+|initial\s+)?(?:consultation|consult|visit|appointment|session))\b", re.I)


def _drop_unsupported_free(text: str, evidence: str) -> str:
    return _FREE_OFFER.sub(lambda m: m.group(0) if m.group(0).lower() in evidence else m.group(1), text)


# "Book a consultation today" pressures without informing; the sentence works without "today".
_TODAY = re.compile(r"(?i)\b((?:book|call|contact|schedule|visit)\b[^.!?\n]*?)\s+today(?=[.!?]|\s+to\b)")
_CLEANUP_RES = [(re.compile(p, re.I), r) for p, r in _CLEANUPS]
_AT_START = re.compile(r"(?:^|[.!?]\s+|\n\s*)$")


def _clean_text(text: str) -> str:
    for rx, replacement in _CLEANUP_RES:
        position = 0
        pieces = []
        for m in rx.finditer(text):
            pieces.append(text[position : m.start()])
            before = "".join(pieces)
            if replacement:
                word = replacement.capitalize() if _AT_START.search(before) or not before.strip() else replacement
                pieces.append(word)
                position = m.end()
            else:
                pieces.append("")
                position = m.end()
                # Capitalise the letter that now starts the sentence.
                if (_AT_START.search(before) or not before.strip()) and position < len(text):
                    pieces.append(text[position].upper())
                    position += 1
        pieces.append(text[position:])
        text = "".join(pieces)
    return re.sub(r"[ \t]{2,}", " ", text).strip() if text.strip() else text


# Models sometimes end the post copy with its hashtags. They belong in the Hashtags section.
_TRAILING_HASHTAGS = re.compile(r"(?:[ \t]+#\w+)+[ \t]*$")


def _tidy_line(text: str, evidence: str) -> str:
    return _TODAY.sub(r"\1", _drop_unsupported_free(_clean_text(text), evidence))


def clean(content: dict[str, Any], evidence_texts: list[str] | None = None) -> dict[str, Any]:
    """The content with stock filler removed or simplified. Tags, hashtags and structure are untouched.

    Also keeps at most one exclamation mark in the whole text (customer-facing copy should not shout)
    and removes "free" from "free consultation" and similar when the website research does not say it.
    """
    evidence = " ".join(evidence_texts or []).lower()
    out = {**content, "sections": [dict(s) for s in content.get("sections", [])]}
    has_hashtags = any(_norm(s.get("heading", "")) == "hashtags" for s in out["sections"])

    def untag(text: str) -> str:
        stripped = "\n".join(_TRAILING_HASHTAGS.sub("", line) for line in text.split("\n"))
        # Leave a field alone if nothing but hashtags would remain.
        only_tags = re.fullmatch(r"(?:\s*#\w+)+", stripped.strip() or "x") is not None
        return stripped if has_hashtags and stripped.strip() and not only_tags else text

    for key in ("summary", "introduction", "conclusion"):
        if out.get(key):
            out[key] = untag(_tidy_line(out[key], evidence))
    for section in out["sections"]:
        if _norm(section.get("heading", "")) not in _NOT_PROSE:
            section["body"] = untag("\n".join(_tidy_line(line, evidence) for line in section["body"].split("\n")))

    seen = 0

    def calm(text: str) -> str:
        nonlocal seen

        def replace(m: re.Match) -> str:
            nonlocal seen
            seen += 1
            return m.group()[0] if seen <= MAX_EXCLAMATIONS else "."

        return re.sub(r"!+", replace, text)

    for key in ("summary", "introduction"):
        if out.get(key):
            out[key] = calm(out[key])
    for section in out["sections"]:
        if _norm(section.get("heading", "")) not in _NOT_PROSE:
            section["body"] = calm(section["body"])
    if out.get("conclusion"):
        out["conclusion"] = calm(out["conclusion"])
    return out
