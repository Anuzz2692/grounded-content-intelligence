"""A compliant NOV-03 style brief and script for tests. The claim statements are made-up test text."""
import copy

from app.brief import Brief

HOOK = "A spec sheet can look impressive and still not tell the whole story"
CTA = "Save this and bring your questions to your next site visit"
DISCLAIMER = "For general information - please check details with the company"
TAGS = ["#HomeEnergy", "#SolarTips", "#BatteryBackup", "#EnergyChoices", "#AskYourInstaller"]


def make_brief(**over):
    data = dict(
        slot_id="NOV-03", topic="Home battery sizing: when a backup makes sense (and when it doesn't)",
        platform="Instagram Reel", duration_seconds=60, presenter="Alex Rivera", spoken_language="English",
        subtitle_language="Hindi", approved_hook=HOOK, approved_cta=CTA, approved_hashtags=TAGS,
        required_disclaimer=DISCLAIMER,
        approved_claims=[
            {"id": "C21", "statement": "Installers may suggest a backup battery for homes with frequent outages, after talking with the customer."},
            {"id": "C04", "statement": "A spec sheet is one piece of information and is read together with the household's usage and the installer's survey."},
        ],
    )
    data.update(over)
    return Brief(**data)


SCENES = [
    ("Hook", "0:00-0:04", HOOK, "Alex Rivera looks into the camera, holding a folded spec sheet at chest height.", "A spec sheet is not the whole story", []),
    ("Insight", "0:04-0:14", "Think of a spec sheet as one page of a longer story. It can look tidy and still leave questions open.",
     "She turns the spec sheet toward herself, then lowers it onto the desk and leans slightly toward the camera.", "One page of a longer story", ["C04"]),
    ("Explanation", "0:14-0:48",
     "Installers may suggest a backup battery for homes with frequent outages, after talking with the customer. They read the spec sheet together with the household's usage and the survey. "
     "Sometimes it adds useful information. Sometimes it changes nothing about the plan. That is why the decision starts with a conversation, not with the product itself.",
     "A two-column text card appears beside her, with approved wording under 'When it may suit' and 'When it may not'.", "Frequent outages, then a conversation", ["C21", "C04"]),
    ("Takeaway", "0:48-0:56", "So a single spec sheet is a starting point. The conversation is where it becomes useful. Questions are welcome, and nobody has to decide alone.",
     "She sits back, rests one hand on the desk and nods once while speaking.", "A spec sheet is a starting point", ["C04"]),
    ("CTA", "0:56-1:00", CTA, "Three approved keywords appear one at a time beside the presenter as she smiles to camera.", "Save this", []),
]


def make_typed(**over):
    typed = {
        "title": "Home battery sizing: when a backup makes sense", "hook": HOOK,
        "scenes": [{"segment": seg, "time": t, "visual": v, "spoken_line": line, "on_screen_text": osd,
                    "subtitle": "हिंदी उपशीर्षक", "claim_ids": ids} for seg, t, line, v, osd, ids in SCENES],
        "caption": f"A spec sheet is not the whole story. Installers may suggest a backup battery for homes with frequent outages. {DISCLAIMER}",
        "caption_claim_ids": ["C21"], "hashtags": list(TAGS), "cta": CTA, "reviewer_notes": [],
    }
    typed.update(over)
    return copy.deepcopy(typed)
