"""A pretend Ollama server that answers with ready-made JSON, so the whole pipeline can run without a model.

It does not understand anything: it reads the JSON schema the application asks for and returns a valid
answer of that shape, built from the request text and (for briefs) the brief itself. Use a real model for real work.
"""
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LINES = [
    "A battery backup keeps chosen circuits running when the grid goes down.",
    "The installer looks at how the household uses power before suggesting a size.",
    "Backup time depends on the battery size and on what is connected.",
    "A site visit comes first, so the design fits the home rather than a template.",
    "Warranty terms are set out in the written quote.",
]


def _topic(user: str) -> str:
    m = re.search(r"USER REQUEST: (.+)", user)
    return (m.group(1).strip() if m else "Home battery backup")[:80]


def _brief(user: str) -> dict | None:
    m = re.search(r"<content_brief>\n(.*?)\n</content_brief>", user, re.S)
    return json.loads(m.group(1).replace("<\\/", "</")) if m else None


def _section(i: int) -> dict:
    return {"heading": ["What it is", "How a site visit works", "What affects the result", "Warranty and support"][i % 4], "body": LINES[i % len(LINES)] + " " + LINES[(i + 1) % len(LINES)]}


def brief_video(brief: dict) -> dict:
    """A script that follows the brief: exact hook and CTA, approved claim ids, approved hashtags, times that add up."""
    segments = brief.get("segments") or [{"name": "Hook", "seconds": 4}, {"name": "Insight", "seconds": 10}, {"name": "Explanation", "seconds": 34}, {"name": "Takeaway", "seconds": 8}, {"name": "CTA", "seconds": 4}]
    budget = brief.get("spoken_word_budget", {})
    target = int((budget.get("minimum", 100) + budget.get("maximum", 140)) / 2)
    claims = [c["id"] for c in brief.get("approved_claims", [])]
    statements = [c["statement"] for c in brief.get("approved_claims", [])]
    hook, cta = brief["approved_hook"], brief["approved_cta"]
    fixed = len(hook.split()) + len(cta.split())
    middle = segments[1:-1]
    remaining = max(target - fixed, 12)
    middle_seconds = max(sum(m["seconds"] for m in middle), 1)
    filler = ["Think of it as one piece of a longer picture.", "Each home is different, so the plan starts with a conversation.", "Sometimes it adds useful detail.",
              "Sometimes it changes nothing about the plan.", "Questions are welcome, and nobody has to decide alone.", "A good answer begins with how the household lives.",
              "Details on paper rarely show the full day-to-day picture.", "Taking notes before the visit helps everyone.", "No single number settles the question.",
              "The installer explains each option in plain words.", "Small choices early on can save effort later.", "It helps to compare the options side by side."]
    cursor_filler = 0
    scenes, cursor = [], 0

    def clock(s: int) -> str:
        return f"{s // 60}:{s % 60:02d}"

    visuals = ["{p} looks into the camera, holding a folded spec sheet at chest height.", "{p} turns the spec sheet toward themselves, then lowers it onto the desk and leans toward the camera.",
               "A two-column text card appears beside {p}, with approved wording under two short headings.", "{p} sits back, rests one hand on the desk and nods once while speaking.",
               "Three approved keywords appear one at a time beside {p} as they smile to camera."]
    presenter = brief.get("presenter") or "The presenter"
    used = 0
    for i, seg in enumerate(segments):
        start, end = cursor, cursor + seg["seconds"]
        cursor = end
        if i == 0:
            line, ids = hook, []
        elif i == len(segments) - 1:
            line, ids = cta, []
        else:
            share = remaining * seg["seconds"] / middle_seconds
            parts = list(statements) if i == len(segments) // 2 and statements else []
            while cursor_filler < len(filler) and sum(len(p.split()) for p in parts) + len(filler[cursor_filler].split()) <= share + 4:
                parts.append(filler[cursor_filler])
                cursor_filler += 1
            if not parts:
                parts.append(filler[min(cursor_filler, len(filler) - 1)])
            line, ids = " ".join(parts), claims[:2] if i == len(segments) // 2 else claims[:1]
        scenes.append({"segment": seg["name"], "time": f"{clock(start)}-{clock(end)}", "visual": visuals[min(i, len(visuals) - 1)].format(p=presenter),
                       "spoken_line": line, "on_screen_text": " ".join(line.split()[:5]) if 0 < i < len(segments) - 1 else "", "subtitle": "(subtitle)" if brief.get("subtitle_language") else "", "claim_ids": ids})
        used += len(line.split())
    caption = "Short educational note on the topic."
    if brief.get("required_disclaimer"):
        caption += " " + brief["required_disclaimer"]
    return {"title": brief.get("required_title") or brief.get("topic") or "Video script", "hook": hook, "scenes": scenes, "caption": caption,
            "caption_claim_ids": claims[:1], "hashtags": brief.get("approved_hashtags", []), "cta": cta, "reviewer_notes": ["Demo output: canned text, not written by a model."]}


def generation(schema: dict, user: str) -> dict:
    props = schema.get("properties", {})
    topic = _topic(user)
    notes = ["Demo output: canned text, not written by a model."]
    if "spoken_line" in json.dumps(schema):
        return brief_video(_brief(user) or {"approved_hook": "Hook", "approved_cta": "CTA"})
    if "scenes" in props:
        scenes = [{"time": "0:00-0:05", "visual": "A calm shot of a home with solar panels.", "voiceover": "Thinking about a battery backup?", "on_screen_text": "Battery backup?"},
                  {"time": "0:05-0:40", "visual": "An installer checks a wall-mounted battery.", "voiceover": " ".join(LINES[:3]), "on_screen_text": ""},
                  {"time": "0:40-0:55", "visual": "Contact details on screen.", "voiceover": "Book a site visit to talk it through.", "on_screen_text": "Book a site visit"}]
        return {"title": "How a battery backup works", "summary": f"A short video about {topic}.", "hook": "Thinking about a battery backup?", "scenes": scenes,
                "title_hook_options": [{"title": "How a battery backup works", "hook": "Thinking about a battery backup?"}, {"title": "Three myths about batteries", "hook": "Think you need the biggest one?"}, {"title": "Before your site visit", "hook": "Here is what to bring."}],
                "caption": "Wondering how a battery backup fits your home? A site visit is where the design starts, so bring your questions and your recent bills. The installer explains the options and what each one means for the household. Book a site visit to talk it through.",
                "tags": [f"tag{i}" for i in range(15)], "hashtags": [f"#Tag{i}" for i in range(15)], "closing_line": "Your questions matter.", "cta": "Book a site visit.", "reviewer_notes": notes}
    if "post_copy" in props:
        return {"title": "Questions before a site visit", "summary": f"A short post about {topic}.", "post_copy": "Planning a battery backup? Write down your questions first. The installer can explain each step for your home.",
                "caption": "Planning a battery backup? Write your questions down first and bring your recent electricity bills. The installer can explain each step and what it means for your home. Book a site visit to talk it through.",
                "tags": [f"tag{i}" for i in range(15)], "hashtags": [f"#Tag{i}" for i in range(15)], "carousel_slides": [], "closing_line": "Your questions matter.", "cta": "Book a site visit.", "reviewer_notes": notes}
    if "faqs" in props:
        n = props["faqs"].get("minItems", 3)
        return {"title": "Battery backup FAQ", "summary": f"Answers about {topic}.", "introduction": "These answers use what the website says.",
                "faqs": [{"question": q, "answer": a} for q, a in zip(["What does a battery backup do?", "What happens at a site visit?", "How long does backup last?", "Is there a warranty?", "Can I add one later?", "What affects the size?", "Who installs it?", "How do I book?"][:n], (LINES * 2)[:n])],
                "conclusion": "Answers depend on your own home.", "suggested_cta": "Book a site visit.", "reviewer_notes": notes}
    n = 5 if "faq" in props else 4
    out = {"title": "How a battery backup works", "summary": f"A plain-language guide to {topic}.", "introduction": "A battery backup keeps chosen circuits running during an outage. This page explains what the website says about it.",
           "sections": [_section(i) for i in range(n)], "conclusion": "A site visit is a good way to see what suits your home.", "suggested_cta": "Book a site visit.", "reviewer_notes": notes}
    if "faqs" in props:
        out["faqs"] = [{"question": f"Question {i}?", "answer": LINES[i % len(LINES)]} for i in range(5)]
    return out


def reply(body: dict) -> dict:
    system, user = body["messages"][0]["content"], body["messages"][1]["content"]
    schema = body.get("format")
    if isinstance(schema, dict) and schema.get("properties"):
        if "<original_draft>" in user:  # the natural-writing pass: hand the draft back unchanged
            m = re.search(r"<original_draft>\n(.*?)\n</original_draft>", user, re.S)
            if m:
                return json.loads(m.group(1).replace("<\\/", "</"))
        return generation(schema, user)
    if "Brand Content Validation" in system:
        return {"validator": "brand", "status": "PASS", "summary": "Demo verdict: no brand issues found (canned).", "issues": [], "corrections": [], "requires_human_review": True, "limitations": ["Demo verdict, not a real review."]}
    return {"status": "PENDING_REVIEW", "content_purpose": "Demo content for a human reviewer.", "accuracy_concerns": [], "brand_concerns": [], "evidence_gaps": [],
            "conflicts": [], "questions_for_reviewer": ["Confirm the claims match what the company offers today."], "recommended_next_action": "REVIEW_CONTENT",
            "approval_authority": "Authorised human reviewer only", "publication_authorised": False}


class Handler(BaseHTTPRequestHandler):
    def _send(self, obj: dict, code: int = 200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send({"models": [{"name": "demo-model"}]} if self.path == "/api/tags" else {}, 200 if self.path == "/api/tags" else 404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self._send({"message": {"content": json.dumps(reply(body))}, "done_reason": "stop"})

    def log_message(self, *args):
        pass


def make_server(port: int = 0) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
