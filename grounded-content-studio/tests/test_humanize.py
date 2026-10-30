import copy

import pytest

from app.humanize import accept_rewrite

EVIDENCE = ["Our company offers battery storage and consultation. Call 011-2345-6789 or visit https://site.test/contact."]
BODY = ("Battery storage, also called energy storage, keeps charge for later use. The process involves several steps, "
        "and your specialist will explain how each one applies to your situation. Many people have questions about timing, ") * 3


def article(**kw):
    base = {"title": "Battery storage", "summary": "A short guide to battery storage.", "introduction": "Thinking about adding batteries?",
            "sections": [{"heading": "How it works", "body": BODY}], "conclusion": "Ask your specialist.",
            "suggested_cta": "Book a consultation.", "reviewer_notes": ["General knowledge used for the steps."]}
    return {**base, **kw}


def rewritten(original, **changes):
    out = copy.deepcopy(original)
    out["sections"][0]["body"] = out["sections"][0]["body"].replace("The process involves several steps", "There are a few steps")
    out.update(changes)
    return out


def run(original, candidate, content_type="article", length="concise"):
    return accept_rewrite(original, candidate, content_type, length, EVIDENCE)


def test_a_clean_rewrite_is_accepted():
    original = article()
    outcome = run(original, rewritten(original))
    assert outcome.changed and outcome.content["sections"][0]["body"] != original["sections"][0]["body"]


def test_an_unchanged_rewrite_is_reported_as_no_change():
    original = article()
    outcome = run(original, copy.deepcopy(original))
    assert not outcome.changed and outcome.content is None and "no changes" in outcome.note


@pytest.mark.parametrize("sentence", [" Success rates are 65% per cycle.", " About 3 in 5 customers succeed."])
def test_new_numbers_are_rejected(sentence):
    original = article()
    candidate = rewritten(original)
    candidate["sections"][0]["body"] += sentence
    outcome = run(original, candidate)
    assert outcome.content is None and "numbers" in outcome.note


def test_numbers_that_were_in_the_draft_may_stay():
    original = article()
    original["sections"][0]["body"] += " Storage is reviewed every 12 months."
    candidate = rewritten(original)
    assert run(original, candidate).changed


def test_new_links_and_contact_details_are_rejected():
    original = article()
    candidate = rewritten(original)
    candidate["sections"][0]["body"] += " See https://example.com/offer or mail info@example.com."
    assert "link or contact" in run(original, candidate).note


def test_new_risky_wording_is_rejected_even_when_polite():
    original = article()
    candidate = rewritten(original, conclusion="Ask your specialist about a free consultation.")
    outcome = run(original, candidate)
    assert outcome.content is None and "flagged wording" in outcome.note


def test_wording_the_research_supports_is_fine():
    evidence = ["We offer a free consultation."]
    original = article()
    outcome = accept_rewrite(original, rewritten(original, conclusion="Ask about a free consultation."), "article", "concise", evidence)
    assert outcome.changed


def test_a_different_number_of_sections_is_rejected():
    original = article()
    candidate = rewritten(original)
    candidate["sections"].append({"heading": "Extra", "body": "More."})
    assert "number of sections" in run(original, candidate).note


@pytest.mark.parametrize("keep,expected", [(0.3, "too much"), (1.6, "too much")])
def test_the_length_may_not_change_drastically(keep, expected):
    original = article()
    candidate = rewritten(original)
    words = candidate["sections"][0]["body"].split()
    candidate["sections"][0]["body"] = " ".join((words * 3)[: int(len(words) * keep)])
    assert expected in run(original, candidate).note


def test_tags_and_hashtags_are_copied_back_unchanged_and_fixed_headings_restored():
    tags = ", ".join(f"tag{i}" for i in range(15))
    hashtags = " ".join(f"#Tag{i}" for i in range(15))
    original = article(sections=[{"heading": "Caption", "body": " ".join(["Write down your questions before the visit."] * 5)},
                                 {"heading": "Tags", "body": tags}, {"heading": "Hashtags", "body": hashtags}])
    candidate = copy.deepcopy(original)
    candidate["sections"][0]["heading"] = "A lovely caption"
    candidate["sections"][0]["body"] = " ".join(["Jot down your questions before the visit."] * 5)
    candidate["sections"][1].update(heading="Keywords", body="a, b, c")
    candidate["sections"][2]["body"] = "#new"

    outcome = run(original, candidate, content_type="social_post", length="standard")

    assert outcome.changed
    sections = outcome.content["sections"]
    assert [s["heading"] for s in sections] == ["Caption", "Tags", "Hashtags"]
    assert sections[1]["body"] == tags and sections[2]["body"] == hashtags
    assert sections[0]["body"].startswith("Jot down")


def test_a_rewrite_that_breaks_the_required_format_is_rejected():
    # Caption must be 30-50 words for a social post; the rewrite cuts it to 5.
    tags = ", ".join(f"t{i}" for i in range(15))
    hashtags = " ".join(f"#t{i}" for i in range(15))
    original = article(sections=[{"heading": "Caption", "body": " ".join(["word"] * 40)}, {"heading": "Tags", "body": tags},
                                 {"heading": "Hashtags", "body": hashtags}])
    candidate = copy.deepcopy(original)
    candidate["sections"][0]["body"] = "Too short now."
    outcome = run(original, candidate, content_type="social_post", length="standard")
    assert outcome.content is None and "required format" in outcome.note and "caption" in outcome.note.lower()


def test_a_call_to_action_is_never_added_and_never_lost():
    no_cta = article(suggested_cta=None)
    added = run(no_cta, rewritten(no_cta, suggested_cta="Book now."))
    assert added.changed and added.content["suggested_cta"] is None

    original = article()
    lost = run(original, rewritten(original, suggested_cta=None))
    assert lost.content["suggested_cta"] == "Book a consultation."


def test_reviewer_notes_are_kept_and_only_a_few_new_ones_are_added():
    original = article()
    candidate = rewritten(original, reviewer_notes=["new 1", "new 2", "new 3", "new 4", "new 5"])
    notes = run(original, candidate).content["reviewer_notes"]
    assert notes[0] == "General knowledge used for the steps." and len(notes) == 4


def test_scene_timings_are_layout_and_may_be_adjusted():
    scenes = "Scene 1 (0:00-0:05)\nVISUAL: A\nVOICEOVER: Hello there and welcome.\n\nScene 2 (0:05-0:30)\nVISUAL: B\nVOICEOVER: Bring your questions."
    original = article(sections=[{"heading": "Screenplay", "body": scenes}])
    candidate = copy.deepcopy(original)
    candidate["sections"][0]["body"] = scenes.replace("Hello there and welcome.", "Welcome.").replace("0:05-0:30", "0:06-0:31")
    outcome = run(original, candidate, content_type="general", length="standard")
    assert outcome.changed and "0:06-0:31" in outcome.content["sections"][0]["body"]


def test_but_a_new_fact_hidden_in_a_scene_line_is_still_caught():
    scenes = "Scene 1 (0:00-0:05)\nVOICEOVER: Hello there and welcome."
    original = article(sections=[{"heading": "Screenplay", "body": scenes}])
    candidate = copy.deepcopy(original)
    candidate["sections"][0]["body"] = "Scene 1 (0:00-0:05)\nVOICEOVER: Hello, 80 percent of customers succeed."
    assert "numbers" in run(original, candidate, content_type="general", length="standard").note
