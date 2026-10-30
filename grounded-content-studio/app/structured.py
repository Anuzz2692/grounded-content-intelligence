"""Strict output formats for the formats that have many required parts.

A small model told in prose to write "a Screenplay section, then three title options, then a
caption, then exactly 15 tags" often skips or reshapes parts. Here each deliverable is its own
required field, and the counts are part of the schema, so the model's decoder cannot leave one out.
`to_content` then assembles the fields into the same title/summary/introduction/sections layout the
rest of the application (checks, validators, the page) already uses.
"""
import copy
import re
from typing import Any

TAG_COUNT = 15
FAQ_COUNTS = {"concise": 3, "standard": 5, "detailed": 8}

STR = {"type": "string"}
NOTES = {"type": "array", "items": STR}
CTA = {"type": ["string", "null"]}


def _list(items: dict[str, Any], minimum: int | None = None, maximum: int | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "array", "items": items}
    if minimum is not None:
        schema["minItems"] = minimum
    if maximum is not None:
        schema["maxItems"] = maximum
    return schema


def _object(**properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def _qa() -> dict[str, Any]:
    return _object(question=STR, answer=STR)


SECTION = _object(heading=STR, body=STR)


def _top(**properties: dict[str, Any]) -> dict[str, Any]:
    return _object(**properties)


BRIEF_VIDEO = "brief_video"  # a presenter-led video written to a content brief; never set by API clients directly


def typed_schema(content_type: str, length: str) -> dict[str, Any] | None:
    """The strict schema for this request, or None when the generic content schema is right."""
    if content_type == BRIEF_VIDEO:
        # No fixed counts: the number of scenes and hashtags comes from the brief.
        return _top(
            title=STR,
            hook=STR,
            scenes=_list(_object(segment=STR, time=STR, visual=STR, spoken_line=STR, on_screen_text=STR, subtitle=STR, claim_ids=_list(STR)), minimum=3),
            caption=STR,
            caption_claim_ids=_list(STR),
            hashtags=_list(STR),
            cta=STR,
            reviewer_notes=NOTES,
        )
    if content_type == "video_script":
        return _top(
            title=STR,
            summary=STR,
            hook=STR,
            scenes=_list(_object(time=STR, visual=STR, voiceover=STR, on_screen_text=STR), minimum=2),
            title_hook_options=_list(_object(title=STR, hook=STR), 3, 3),
            caption=STR,
            tags=_list(STR, TAG_COUNT, TAG_COUNT),
            hashtags=_list(STR, TAG_COUNT, TAG_COUNT),
            closing_line=STR,
            cta=CTA,
            reviewer_notes=NOTES,
        )
    if content_type == "social_post":
        return _top(
            title=STR,
            summary=STR,
            post_copy=STR,
            caption=STR,
            tags=_list(STR, TAG_COUNT, TAG_COUNT),
            hashtags=_list(STR, TAG_COUNT, TAG_COUNT),
            carousel_slides=_list(STR),
            closing_line=STR,
            cta=CTA,
            reviewer_notes=NOTES,
        )
    if content_type == "faq":
        count = FAQ_COUNTS.get(length, 5)
        return _top(
            title=STR, summary=STR, introduction=STR, faqs=_list(_qa(), count, count),
            conclusion=STR, suggested_cta=CTA, reviewer_notes=NOTES,
        )
    if content_type in {"article", "blog"} and length == "detailed":
        return _top(
            title=STR, summary=STR, introduction=STR, sections=_list(SECTION, minimum=1),
            conclusion=STR, suggested_cta=CTA,
            faqs=_list(_qa(), 5, 5), people_also_ask=_list(STR, 5, 5), reviewer_notes=NOTES,
        )
    return None


def loosen(schema: dict[str, Any]) -> dict[str, Any]:
    """The same schema without item-count limits, for a server that rejects them."""
    loose = copy.deepcopy(schema)

    def strip(node: Any) -> None:
        if isinstance(node, dict):
            node.pop("minItems", None)
            node.pop("maxItems", None)
            for value in node.values():
                strip(value)
        elif isinstance(node, list):
            for value in node:
                strip(value)

    strip(loose)
    return loose


# --- assembling fields into sections -----------------------------------------------------------

def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dicts(value: Any) -> list[dict[str, Any]]:
    return [v for v in _items(value) if isinstance(v, dict)]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for value in values:
        key = value.lower()
        if value and key not in seen:
            seen.add(key)
            out.append(value)
    return out


def clean_tags(values: Any) -> list[str]:
    cleaned = [re.sub(r"\s+", " ", _text(v).lstrip("#")).strip(" ,") for v in _items(values)]
    return _dedupe(cleaned)[:TAG_COUNT]


def clean_hashtags(values: Any) -> list[str]:
    cleaned = []
    for v in _items(values):
        word = re.sub(r"[^\w]", "", _text(v))  # "#home battery" becomes "homebattery"
        if word:
            cleaned.append("#" + word)
    return _dedupe(cleaned)[:TAG_COUNT]


def top_up_hashtags(hashtags: list[str], tags: list[str]) -> list[str]:
    """Reach 15 hashtags using the model's own tags when duplicates were removed.

    "home battery" becomes "#HomeBattery". Only words the model already chose are used.
    """
    out = list(hashtags)
    have = {h.lower() for h in out}
    for tag in tags:
        if len(out) >= TAG_COUNT:
            break
        candidate = "#" + "".join(word.capitalize() for word in re.findall(r"\w+", tag))
        if len(candidate) > 1 and candidate.lower() not in have:
            out.append(candidate)
            have.add(candidate.lower())
    return out


def _section(heading: str, body: str) -> list[dict[str, str]]:
    return [{"heading": heading, "body": body}] if body.strip() else []


def _screenplay(scenes: list[dict[str, Any]]) -> str:
    blocks = []
    for number, scene in enumerate(scenes, start=1):
        when = _text(scene.get("time"))
        lines = [f"Scene {number} ({when})" if when else f"Scene {number}"]
        lines.append(f"VISUAL: {_text(scene.get('visual'))}")
        lines.append(f"VOICEOVER: {_text(scene.get('voiceover'))}")
        lines.append(f"ON-SCREEN TEXT: {_text(scene.get('on_screen_text')) or 'None'}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _faq_body(items: list[dict[str, Any]]) -> str:
    return "\n\n".join(f"Q: {_text(i.get('question'))}\nA: {_text(i.get('answer'))}" for i in items if _text(i.get("question")))


def to_content(content_type: str, length: str, data: dict[str, Any]) -> dict[str, Any]:
    """Assemble strict-format fields into the shared content layout. Parts the model left empty are
    simply absent, so the format checks report them and the fix pass can ask for them."""
    notes = [_text(n) for n in _items(data.get("reviewer_notes")) if _text(n)]

    if content_type == BRIEF_VIDEO:
        scenes = []
        for number, scene in enumerate(_dicts(data.get("scenes")), start=1):
            head = f"Scene {number} ({_text(scene.get('time'))})" + (f" - {_text(scene.get('segment'))}" if _text(scene.get("segment")) else "")
            lines = [head, f"VISUAL: {_text(scene.get('visual'))}", f"SPOKEN LINE: {_text(scene.get('spoken_line'))}",
                     f"ON-SCREEN TEXT: {_text(scene.get('on_screen_text')) or 'None'}"]
            if _text(scene.get("subtitle")):
                lines.append(f"SUBTITLE: {_text(scene.get('subtitle'))}")
            scenes.append("\n".join(lines))
        hashtags = [_text(h) for h in _items(data.get("hashtags")) if _text(h)]
        sections = _section("Script", "\n\n".join(scenes)) + _section("Caption", _text(data.get("caption"))) + _section("Hashtags", " ".join(hashtags))
        return {"title": _text(data.get("title")), "summary": "", "introduction": _text(data.get("hook")), "sections": sections,
                "conclusion": "", "suggested_cta": _text(data.get("cta")) or None, "reviewer_notes": notes}

    if content_type == "video_script":
        options = "\n".join(
            f"{i}. Title: {_text(o.get('title'))} | Hook: {_text(o.get('hook'))}" for i, o in enumerate(_dicts(data.get("title_hook_options")), start=1)
        )
        sections = (
            _section("Screenplay", _screenplay(_dicts(data.get("scenes"))))
            + _section("Title and Hook Options", options)
            + _section("Caption", _text(data.get("caption")))
            + _section("Tags", ", ".join(clean_tags(data.get("tags"))))
            + _section("Hashtags", " ".join(top_up_hashtags(clean_hashtags(data.get("hashtags")), clean_tags(data.get("tags")))))
        )
        return {"title": _text(data.get("title")), "summary": _text(data.get("summary")), "introduction": _text(data.get("hook")),
                "sections": sections, "conclusion": _text(data.get("closing_line")),
                "suggested_cta": _text(data.get("cta")) or None, "reviewer_notes": notes}

    if content_type == "social_post":
        slides = "\n".join(f"Slide {i}: {_text(s)}" for i, s in enumerate(_items(data.get("carousel_slides")), start=1) if _text(s))
        sections = (
            _section("Caption", _text(data.get("caption")))
            + _section("Tags", ", ".join(clean_tags(data.get("tags"))))
            + _section("Hashtags", " ".join(top_up_hashtags(clean_hashtags(data.get("hashtags")), clean_tags(data.get("tags")))))
            + _section("Carousel slides", slides)
        )
        return {"title": _text(data.get("title")), "summary": _text(data.get("summary")), "introduction": _text(data.get("post_copy")),
                "sections": sections, "conclusion": _text(data.get("closing_line")),
                "suggested_cta": _text(data.get("cta")) or None, "reviewer_notes": notes}

    if content_type == "faq":
        sections = [{"heading": _text(i.get("question")), "body": _text(i.get("answer"))} for i in _dicts(data.get("faqs")) if _text(i.get("question")) and _text(i.get("answer"))]
        return {"title": _text(data.get("title")), "summary": _text(data.get("summary")), "introduction": _text(data.get("introduction")),
                "sections": sections, "conclusion": _text(data.get("conclusion")),
                "suggested_cta": _text(data.get("suggested_cta")) or None, "reviewer_notes": notes}

    # Detailed website page: the article sections, then the FAQ and People Also Ask sections.
    sections = [
        {"heading": _text(s.get("heading")), "body": _text(s.get("body"))}
        for s in _dicts(data.get("sections")) if _text(s.get("heading")) and _text(s.get("body"))
    ]
    paa = "\n".join(f"- {_text(q)}" for q in _items(data.get("people_also_ask")) if _text(q))
    sections += _section("Frequently Asked Questions", _faq_body(_dicts(data.get("faqs")))) + _section("People Also Ask", paa)
    return {"title": _text(data.get("title")), "summary": _text(data.get("summary")), "introduction": _text(data.get("introduction")),
            "sections": sections, "conclusion": _text(data.get("conclusion")),
            "suggested_cta": _text(data.get("suggested_cta")) or None, "reviewer_notes": notes}
