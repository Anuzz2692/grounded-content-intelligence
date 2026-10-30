"""The self-check for brief-driven videos: every rule that code can decide, decided by code.

The model never grades itself. Each check returns PASS, FAIL, REVIEW_REQUIRED, NOT_APPLICABLE or
UNVERIFIED. Anything the code cannot decide (such as tone and brand fit) comes from the independent
brand validator and is never better than its verdict.
A passing self-check is not brand, accuracy or human approval.
"""
import re
from collections import Counter
from typing import Any

from app.brief import Brief, count_words, normalise, word_budget
from app.format_checks import risky_matches

PASS, FAIL, REVIEW, NA, UNVERIFIED = "PASS", "FAIL", "REVIEW_REQUIRED", "NOT_APPLICABLE", "UNVERIFIED"

# Wording the brand policy forbids in any creative text. Boundary-aware so unrelated words never match.
_SEP = r"[\s\-_]+"
_OPT = r"(?:[\s\-_]+)?"
BRAND_TERMS: list[tuple[str, str]] = [
    ("free consultation or trial", rf"free{_SEP}(?:initial{_SEP})?(?:consultations?|trials?|quotes?)"),
    ("discount", r"(?<!\w)(?:discounts?|discounted)(?!\w)"),
    ("percentage offer", r"\b\d+\s*%\s*(?:off|offer|discount)\b|\b\d+\s*%\s+offer"),
    ("offer", rf"\b(?:special|limited{_SEP}time|exclusive|festive)\s+offers?\b|\bpackage\s+deals?\b|\bfree{_SEP}(?:tests?|scans?|check{_OPT}ups?|screenings?|sessions?)\b"),
    ("EMI", r"(?<!\w)EMI(?!\w)"),
    ("callback promise", rf"(?<!\w)call{_OPT}back(?!\w)|\bwe(?:'ll|\s+will)\s+call\s+you\b"),
    ("Most Trusted", rf"\bmost{_SEP}trusted\b"),
    ("No.1", r"(?<!\w)no\.?\s*1(?!\w)|\bnumber\s+(?:one|1)\b|(?<!\w)#\s*1(?!\w)"),
    ("success rate", rf"\bsuccess{_SEP}rates?\b|\bsuccess(?:ful)?\s+(?:stories|cases)\b"),
    ("customer or user count", r"\b\d[\d,]*\+?\s+(?:happy\s+)?(?:customers|users|clients|families|homes|installations|orders)\b"),
]
# Tone: promotional or fear wording. Approved hook, CTA and disclaimer text is exempt (it was approved as written).
TONE_FAIL = [
    ("crucial", r"\bcrucial\b"), ("must", r"\bmust\b"), ("best", r"\bbest\b"), ("guaranteed", r"\bguarantee[ds]?\b"),
    ("fear opener", r"\bare\s+you\s+(?:worried|scared|afraid|anxious|concerned)\b"), ("don't ignore", r"\bdon'?t\s+ignore\b"),
    ("warning signs", r"\bwarning\s+signs?\b"), ("fear wording", r"\b(?:scary|terrifying|terrified|panic|devastating|dangerous)\b"),
    ("false urgency", r"\b(?:urgent(?:ly)?|hurry|last\s+chance|don'?t\s+wait)\b"),
]
TONE_REVIEW = [("should", r"\bshould\b")]
# Any call to action other than the approved one.
OTHER_CTA = re.compile(
    r"\b(?:book(?:ing)?\s+(?:a|an|your|now|today)|call\s+(?:us|now|today)|contact\s+us|visit\s+(?:us|our)|schedule\s+(?:a|an|your)|"
    r"sign\s+up|click|link\s+in\s+(?:bio|description)|dm\s+us|whats\s?app|enqui?re|inquire|register|get\s+in\s+touch|reach\s+out|"
    r"make\s+an\s+appointment|appointment)\b", re.I)
TEMPLATE_PHRASES = ["comprehensive assessment", "unique situation", "remember, the key is", "the key is to"]
VAGUE_VISUALS = [
    r"^(?:the\s+)?(?:presenter|host|speaker)\s+(?:is\s+)?(?:explaining|talking|speaking)\s+(?:on|to|at|with)\s+(?:a\s+|the\s+)?(?:screen|camera)\.?$",
    r"^(?:the\s+)?(?:presenter|host|speaker)\s+(?:is\s+)?holding\s+(?:a\s+)?(?:chart|report|paper)\.?$",
    r"^(?:show|display)\s+(?:a\s+)?(?:relevant\s+)?(?:animation|graphic|visual|image|information|product information)s?\.?$",
]
CITATION = re.compile(
    r"https?://|www\.|\b[\w-]+\.(?:com|in|org|net|gov|edu)\b|\baccording\s+to\s+(?:a|the|recent)\s+(?:study|studies|research|survey|paper|trial)\b|"
    r"\bstudies\s+(?:show|have\s+shown|suggest)\b|\bresearch\s+(?:shows|has\s+shown|suggests)\b|\bet\s+al\b|\(\s*[A-Z][a-z]+,?\s+\d{4}\s*\)", re.I)
STATE_CLAIM = re.compile(
    r"\b(?:expert|legally|legal|compliance|editor|manager)[\s-]+(?:reviewed|approved|verified|certified)\b|\b(?:reviewed|approved|verified|certified)\s+by\b|"
    r"\bpublication[\s-]ready\b|\bready\s+to\s+(?:publish|post)\b", re.I)
_STOP = set("this that with from have been your what when they them then than will into about also more some such only just like very".split())
SCENE_KEYS = ("segment", "time", "visual", "spoken_line", "on_screen_text", "subtitle")
NOT_APPROVAL = "A passing self-check is not brand approval, accuracy approval or permission to publish."


def _check(id: str, name: str, status: str, detail: str) -> dict[str, str]:
    return {"id": id, "name": name, "status": status, "detail": detail}


def _scenes(typed: dict[str, Any]) -> list[dict[str, Any]]:
    return [s for s in typed.get("scenes", []) if isinstance(s, dict)] if isinstance(typed.get("scenes"), list) else []


def _t(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _ids(value: Any) -> list[str]:
    return [_t(v) for v in value if _t(v)] if isinstance(value, list) else []


def creative_fields(typed: dict[str, Any]) -> list[tuple[str, str]]:
    """Every piece of publishable text, labelled. reviewer_notes and the claim library are internal and excluded."""
    out = [("title", _t(typed.get("title"))), ("hook", _t(typed.get("hook")))]
    for n, s in enumerate(_scenes(typed), start=1):
        out += [(f"scene {n} visual", _t(s.get("visual"))), (f"scene {n} spoken line", _t(s.get("spoken_line"))),
                (f"scene {n} on-screen text", _t(s.get("on_screen_text"))), (f"scene {n} subtitle", _t(s.get("subtitle")))]
    out += [("caption", _t(typed.get("caption"))), ("hashtags", " ".join(_t(h) for h in typed.get("hashtags", []) if isinstance(h, str))),
            ("cta", _t(typed.get("cta")))]
    return [(label, text) for label, text in out if text]


def _without(text: str, approved: list[str]) -> str:
    for item in approved:
        if item.strip():
            text = re.sub(re.escape(normalise(item)).replace(r"\ ", r"\s+"), " ", normalise(text), flags=re.I)
    return text


def _brand_patterns(brief: Brief) -> list[tuple[str, re.Pattern]]:
    from app.company import load_profile
    # The universal list, then this company's own restricted wording from its profile, then the brief's.
    patterns = [(label, re.compile(rx, re.I)) for label, rx in [*BRAND_TERMS, *load_profile().restricted_terms]]
    for term in brief.brand_restrictions:
        rx = r"(?<!\w)" + _SEP.join(re.escape(p) for p in term.split()) + r"(?!\w)"
        patterns.append((term, re.compile(rx, re.I)))
    return patterns


def _time_range(value: str) -> tuple[int, int] | None:
    clock = re.fullmatch(r"\s*(\d+):(\d{2})\s*[-–—]+\s*(\d+):(\d{2})\s*", value)
    if clock:
        a, b, c, d = map(int, clock.groups())
        return a * 60 + b, c * 60 + d
    plain = re.fullmatch(r"\s*(\d+)\s*s?\s*[-–—]+\s*(\d+)\s*s?\s*", value)
    return (int(plain.group(1)), int(plain.group(2))) if plain else None


def _stems(text: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= 4 and w not in _STOP}


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def spoken_lines(typed: dict[str, Any]) -> list[str]:
    return [_t(s.get("spoken_line")) for s in _scenes(typed)]


def word_count(typed: dict[str, Any]) -> int:
    """Spoken words only: the spoken lines. Visuals, on-screen text, subtitles, caption, hashtags and notes are excluded."""
    return sum(count_words(line) for line in spoken_lines(typed))


def claims_used(brief: Brief, typed: dict[str, Any]) -> list[dict[str, Any]]:
    """Approved claims the content actually cites, with the approved statement (from the brief, not the model)."""
    library = brief.claim_map()
    where: dict[str, list[str]] = {}
    for n, scene in enumerate(_scenes(typed), start=1):
        for cid in _ids(scene.get("claim_ids")):
            where.setdefault(cid.lower(), []).append(f"scene {n}")
    for cid in _ids(typed.get("caption_claim_ids")):
        where.setdefault(cid.lower(), []).append("caption")
    original = {c.id.lower(): c.id for c in brief.approved_claims}
    return [{"id": original[k], "statement": library[k], "used_in": sorted(set(v))} for k, v in where.items() if k in library]


def script_table(typed: dict[str, Any]) -> list[dict[str, str]]:
    """Exactly the four columns of the required script table."""
    return [{"time": _t(s.get("time")), "visual": _t(s.get("visual")), "spoken line": _t(s.get("spoken_line")),
             "on-screen text": _t(s.get("on_screen_text"))} for s in _scenes(typed)]


# --- individual checks --------------------------------------------------------------------------------

def _schema(typed: dict[str, Any]) -> list[str]:
    problems = [f"{k} is missing or not text" for k in ("title", "hook", "caption", "cta") if not isinstance(typed.get(k), str) or not _t(typed.get(k))]
    if not isinstance(typed.get("hashtags"), list) or not all(isinstance(h, str) for h in typed.get("hashtags", [])):
        problems.append("hashtags must be a list of text")
    if not isinstance(typed.get("caption_claim_ids"), list):
        problems.append("caption_claim_ids must be a list")
    scenes = typed.get("scenes")
    if not isinstance(scenes, list) or len(scenes) < 3:
        return problems + ["scenes must be a list of at least 3"]
    for n, s in enumerate(scenes, start=1):
        if not isinstance(s, dict):
            problems.append(f"scene {n} is not an object")
            continue
        problems += [f"scene {n} {k} is missing or not text" for k in SCENE_KEYS if not isinstance(s.get(k), str)]
        if not isinstance(s.get("claim_ids"), list):
            problems.append(f"scene {n} claim_ids must be a list")
        for k in ("segment", "time", "visual", "spoken_line"):
            if isinstance(s.get(k), str) and not s[k].strip():
                problems.append(f"scene {n} {k} is empty")
    return problems


def deterministic_checks(brief: Brief, typed: dict[str, Any]) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    add = lambda *a: checks.append(_check(*a))  # noqa: E731
    scenes = _scenes(typed)
    schema_problems = _schema(typed)
    spoken = spoken_lines(typed)
    approved_text = [brief.approved_hook, brief.approved_cta, brief.required_disclaimer]
    fields = creative_fields(typed)
    duration = brief.duration_seconds or 0

    # 1 brief compliance
    problems = [f"brief is missing {m}" for m in brief.missing_for_video()]
    if brief.structure_problem():
        problems.append(brief.structure_problem())
    if brief.required_title and normalise(_t(typed.get("title"))) != normalise(brief.required_title):
        problems.append("title is not the required title")
    if brief.subtitle_language and any(not _t(s.get("subtitle")) for s in scenes):
        problems.append(f"a scene has no {brief.subtitle_language} subtitle")
    if not brief.subtitle_language and any(_t(s.get("subtitle")) for s in scenes):
        problems.append("subtitles were written but the brief requests none")
    if problems:
        add("brief_compliance", "Brief compliance", FAIL, "; ".join(problems) + ".")
    elif brief.caption_requirements or brief.extra_constraints:
        add("brief_compliance", "Brief compliance", REVIEW, "Fields are respected. The caption requirements and extra constraints are free text; a reviewer must confirm them.")
    else:
        add("brief_compliance", "Brief compliance", PASS, "Every supplied brief field was applied.")

    # 2 duration and structure
    if schema_problems and not scenes:
        add("duration", "Duration and segments", FAIL, "No scenes to measure.")
    else:
        issues, cursor = [], 0
        for n, s in enumerate(scenes, start=1):
            r = _time_range(_t(s.get("time")))
            if not r or r[1] <= r[0]:
                issues.append(f"scene {n} time '{_t(s.get('time'))}' is not a valid range")
                continue
            if r[0] != cursor:
                issues.append(f"scene {n} starts at {r[0]}s but the previous scene ended at {cursor}s")
            cursor = r[1]
        if not issues and cursor != duration:
            issues.append(f"the scenes end at {cursor}s, not {duration}s")
        structure = brief.structure()
        if structure and not issues:
            if len(scenes) != len(structure):
                issues.append(f"expected {len(structure)} scenes for the segments, found {len(scenes)}")
            else:
                for n, ((name, secs), s) in enumerate(zip(structure, scenes), start=1):
                    a, b = _time_range(_t(s.get("time"))) or (0, 0)
                    if normalise(_t(s.get("segment"))).lower() != name.lower() or b - a != secs:
                        issues.append(f"scene {n} should be {name} for {secs}s")
        add("duration", "Duration and segments", FAIL if issues else PASS,
            "; ".join(issues) + "." if issues else f"{len(scenes)} continuous scenes add up to {duration} seconds" + (" and follow the segment structure." if structure else "."))

    # 3 word count
    if duration:
        target, low, high = word_budget(duration)
        words = word_count(typed)
        ok = low <= words <= high
        add("word_count", "Spoken word count", PASS if ok else FAIL,
            f"{words} spoken words; allowed {low}-{high} (target {round(target)}). This is an estimate of delivery time, not a guarantee of {duration} seconds.")
    else:
        add("word_count", "Spoken word count", UNVERIFIED, "No duration in the brief.")

    # 4 hook, 5 CTA exact, 6 CTA count
    hook = normalise(brief.approved_hook)
    problems = []
    if normalise(_t(typed.get("hook"))) != hook:
        problems.append("the hook field differs from the approved hook")
    if not spoken or normalise(spoken[0]) != hook:
        problems.append("the opening spoken line is not exactly the approved hook")
    add("hook", "Approved hook", FAIL if problems else PASS, "; ".join(problems) + "." if problems else "The opening line matches the approved hook exactly.")
    cta = normalise(brief.approved_cta)
    problems = []
    if normalise(_t(typed.get("cta"))) != cta:
        problems.append("the cta field differs from the approved CTA")
    if not spoken or normalise(spoken[-1]) != cta:
        problems.append("the final spoken line is not exactly the approved CTA")
    add("cta", "Approved CTA", FAIL if problems else PASS, "; ".join(problems) + "." if problems else "The closing line matches the approved CTA exactly.")

    shown = [(l, t) for l, t in fields if l not in {"hook", "cta", "hashtags"} and not l.endswith("visual") and not l.endswith("subtitle")]
    occurrences = sum(len(re.findall(re.escape(cta).replace(r"\ ", r"\s+"), normalise(t), flags=re.I)) for _, t in shown)
    others = []
    for label, text in shown:
        for m in OTHER_CTA.finditer(_without(text, [brief.approved_cta, brief.required_disclaimer])):
            others.append(f'{label}: "{m.group()}"')
    problems = ([f"the approved CTA appears {occurrences} times in the package, not once"] if occurrences != 1 else []) + ([f"another call to action: {', '.join(others[:3])}"] if others else [])
    add("cta_count", "Single CTA", FAIL if problems else PASS, "; ".join(problems) + "." if problems else "The approved CTA appears once and no other call to action was found.")

    # 7 claim mapping, 8 claim integrity
    library = brief.claim_map()
    unknown, uncited = [], []
    for n, s in enumerate(scenes, start=1):
        ids = _ids(s.get("claim_ids"))
        unknown += [f"scene {n}: {i}" for i in ids if i.lower() not in library]
        if n not in (1, len(scenes)) and not [i for i in ids if i.lower() in library]:
            uncited.append(f"scene {n}")
    unknown += [f"caption: {i}" for i in _ids(typed.get("caption_claim_ids")) if i.lower() not in library]
    used = claims_used(brief, typed)
    if unknown:
        add("claim_mapping", "Approved claim IDs", FAIL, "Unapproved claim ids: " + ", ".join(unknown) + ".")
    elif not used:
        add("claim_mapping", "Approved claim IDs", FAIL, "No approved claim is cited.")
    elif uncited:
        add("claim_mapping", "Approved claim IDs", REVIEW, "Explanatory scenes that cite no approved claim: " + ", ".join(uncited) + ". A reviewer must confirm they state no unsupported fact.")
    else:
        add("claim_mapping", "Approved claim IDs", PASS, "Every explanatory scene cites approved claims: " + ", ".join(u["id"] for u in used) + ". Whether the wording stays inside each claim is for the reviewer to confirm.")

    evidence = " ".join([*library.values(), *approved_text, brief.topic, brief.objective]).lower()
    flagged = []
    for label, text in fields:
        if label in {"hook", "cta", "hashtags"} or label.endswith("subtitle"):
            continue
        for kind, _, message in risky_matches(_without(text, approved_text), evidence):
            flagged.append(f"{label}: {message}")
    # Numbers must come from an approved claim or the brief; time ranges are not figures.
    allowed = set(re.findall(r"\d+(?:\.\d+)?", evidence))
    for label, text in fields:
        if label in {"hook", "cta", "hashtags"} or label.endswith("subtitle") or "visual" in label:
            continue
        for n in re.findall(r"\d+(?:\.\d+)?", _without(text, approved_text)):
            if n not in allowed:
                flagged.append(f'{label}: the number "{n}" is not in an approved claim')
    add("claim_integrity", "No unsupported detail", FAIL if flagged else PASS,
        "; ".join(dict.fromkeys(flagged[:4])) + "." if flagged else "No unsupported statistic, outcome promise, efficacy claim or number was found.")

    # 9 contradictions are decided by the validators (build_report)

    # 10 tone
    tone_hits, tone_review = [], []
    for label, text in fields:
        if label in {"hook", "cta", "hashtags"}:
            continue
        clean = _without(text, approved_text)
        tone_hits += [f'{label}: "{m.group()}"' for _, rx in TONE_FAIL for m in [re.search(rx, clean, re.I)] if m]
        tone_review += [f'{label}: "{m.group()}"' for _, rx in TONE_REVIEW for m in [re.search(rx, clean, re.I)] if m]
    if tone_hits:
        add("tone", "Tone", FAIL, "Fear, hype or directive wording: " + "; ".join(tone_hits[:4]) + ".")
    elif tone_review:
        add("tone", "Tone", REVIEW, '"should" may be direct advice: ' + "; ".join(tone_review[:3]) + ".")
    else:
        add("tone", "Tone", PASS, "No fear opener, hype word or directive wording was found.")

    # 11 brand
    hits = []
    for label, text in fields:
        for term, rx in _brand_patterns(brief):
            if rx.search(text):
                hits.append(f'{label}: "{term}"')
    add("brand_restrictions", "Brand restrictions", FAIL if hits else PASS,
        "Restricted wording: " + "; ".join(hits[:5]) + "." if hits else "No restricted term, offer or promotional claim was found in any creative field.")

    # 12 hashtags
    tags = [h for h in typed.get("hashtags", []) if isinstance(h, str)] if isinstance(typed.get("hashtags"), list) else []
    if brief.approved_hashtags:
        want = [h.lower() for h in brief.approved_hashtags]
        got = [h.strip().lower() for h in tags]
        extra, missing = sorted(set(got) - set(want)), sorted(set(want) - set(got))
        problems = ([f"not approved: {', '.join(extra)}"] if extra else []) + ([f"missing: {', '.join(missing)}"] if missing else []) + (["duplicates"] if len(got) != len(set(got)) else [])
        add("hashtags", "Approved hashtags", FAIL if problems else PASS, "; ".join(problems) + "." if problems else f"The {len(want)} approved hashtags are used and no others.")
    elif tags:
        add("hashtags", "Approved hashtags", FAIL, "Hashtags were written but the brief supplies none; they would be invented.")
    else:
        add("hashtags", "Approved hashtags", NA, "The brief supplies no hashtags and none were written.")

    # 13 repetition
    repeated = []
    lines = [_without(line, approved_text) for line in spoken]
    grams = Counter(g for line in lines for g in {tuple(w) for w in _ngrams(re.findall(r"[\w']+", line.lower()), 4)})
    repeated += [f'"{" ".join(g)}"' for g, c in grams.items() if c >= 2][:3]
    for a in range(len(lines)):
        for b in range(a + 1, len(lines)):
            if len(lines[a].split()) >= 5 and _jaccard(_stems(lines[a]), _stems(lines[b])) >= 0.7:
                repeated.append(f"scenes {a + 1} and {b + 1} say the same thing")
    prose = " ".join(t.lower() for l, t in fields if l.endswith("spoken line") or l == "caption")
    repeated += [f'template phrase "{p}"' for p in TEMPLATE_PHRASES if p in prose]
    add("repetition", "Repetition and template phrases", FAIL if repeated else PASS,
        "Repeated: " + "; ".join(dict.fromkeys(repeated)) + "." if repeated else "No repeated phrase, repeated scene or template phrase was found.")

    # 14 visuals, 15 shot diversity
    weak = []
    for n, s in enumerate(scenes, start=1):
        v = _t(s.get("visual"))
        if len(v.split()) < 8 or any(re.match(rx, v.strip(), re.I) for rx in VAGUE_VISUALS):
            weak.append(f"scene {n}")
    add("visual_specificity", "Filmable visuals", FAIL if weak or not scenes else PASS,
        "Too vague or too short: " + ", ".join(weak) + "." if weak else "Every scene's visual is described in enough detail to film. (Length and known vague phrases are checked by code; a reviewer judges the rest.)")
    if brief.continuous_talking_head:
        add("shot_diversity", "Shot diversity", NA, "The brief asks for a continuous talking-head format.")
    else:
        sets = [_stems(_t(s.get("visual"))) for s in scenes]
        bad = [n + 1 for n, a in enumerate(sets) if sum(_jaccard(a, b) >= 0.8 for b in sets) > 2]
        add("shot_diversity", "Shot diversity", FAIL if bad else PASS, f"The same shot is used more than twice (scenes {', '.join(map(str, bad))})." if bad else "No shot is used more than twice.")

    # 16 on-screen consistency
    issues, review = [], []
    for n, s in enumerate(scenes, start=1):
        text = _t(s.get("on_screen_text"))
        if not text:
            continue
        if len(text.split()) > 15:
            issues.append(f"scene {n} on-screen text is {len(text.split())} words")
        said = _stems(_t(s.get("spoken_line")) + " " + _t(s.get("subtitle")))
        mine = _stems(text)
        if mine and len(mine & said) / len(mine) < 0.5:
            review.append(f"scene {n}")
    add("on_screen", "On-screen text matches speech", FAIL if issues else REVIEW if review else PASS,
        "; ".join(issues) + "." if issues else ("On-screen text that does not clearly echo the spoken line: " + ", ".join(review) + "." if review else "On-screen text is short and echoes the spoken line."))

    # 17 schema
    add("output_schema", "Output structure", FAIL if schema_problems else PASS, "; ".join(schema_problems[:5]) + "." if schema_problems else "All required fields are present with the right types.")

    # 18 disclaimer
    if brief.required_disclaimer:
        present = normalise(brief.required_disclaimer).lower() in normalise(_t(typed.get("caption"))).lower()
        add("disclaimer", "Required disclaimer", PASS if present else FAIL, "The disclaimer is in the caption word for word." if present else "The required disclaimer is not in the caption word for word.")
    else:
        add("disclaimer", "Required disclaimer", NA, "The brief requires no disclaimer.")

    # 19 source integrity
    leaks = [f'{l}: "{m.group()}"' for l, t in fields for m in [CITATION.search(t)] if m]
    leaks += [f'{l}: claim id "{c.id}"' for l, t in fields for c in brief.approved_claims if len(c.id) >= 2 and re.search(rf"(?<![\w-]){re.escape(c.id)}(?![\w-])", t, re.I)]
    add("source_integrity", "No invented sources", FAIL if leaks else PASS,
        "; ".join(leaks[:4]) + "." if leaks else "No URL, citation, study reference or internal claim id appears in the creative text.")

    # 20 review state
    states = [f'{l}: "{m.group()}"' for l, t in fields for m in [STATE_CLAIM.search(t)] if m]
    add("review_state", "No approval claimed", FAIL if states else PASS,
        "Claims approval: " + "; ".join(states[:3]) + "." if states else "The content does not claim to be reviewed, approved or ready to publish.")
    return checks


def _ngrams(words: list[str], n: int):
    return [words[i:i + n] for i in range(len(words) - n + 1)]


def overall(checks: list[dict[str, str]]) -> str:
    statuses = {c["status"] for c in checks}
    if FAIL in statuses:
        return FAIL
    if statuses & {REVIEW, UNVERIFIED}:
        return REVIEW
    return PASS


def failures(checks: list[dict[str, str]]) -> list[str]:
    return [f"{c['name']}: {c['detail']}" for c in checks if c["status"] == FAIL]


def build_report(brief: Brief, typed: dict[str, Any], brand: dict[str, Any] | None = None) -> dict[str, Any]:
    """Deterministic checks plus the check that depends on the independent brand validator."""
    checks = deterministic_checks(brief, typed)
    if brand is None or brand.get("status") == "NOT_RUN":
        checks.append(_check("validators", "Independent brand validator", UNVERIFIED, "Brand validation did not run."))
    else:
        status = brand.get("status")
        if status == FAIL:
            result, detail = FAIL, "Brand validation failed."
        elif status == "PASS" and not brand.get("validation_error"):
            result, detail = PASS, "The brand validator passed. This is not human approval."
        else:
            result, detail = REVIEW, f"Brand validation is {status}."
        checks.append(_check("validators", "Independent brand validator", result, detail))
    target, low, high = word_budget(brief.duration_seconds or 0)
    return {
        "overall": overall(checks), "checks": checks, "note": NOT_APPROVAL,
        "word_count": {"actual": word_count(typed), "minimum": low, "maximum": high, "target": round(target)},
        "script_table": script_table(typed), "claims_used": claims_used(brief, typed),
        "publication_authorised": False,
    }
