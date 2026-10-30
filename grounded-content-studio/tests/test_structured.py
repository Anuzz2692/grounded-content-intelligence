import json

import pytest

from app import structured
from app.format_checks import check_format
from app.llm import _validate_content

TAGS = [f"tag {i}" for i in range(15)]
HASHTAGS = [f"#Tag{i}" for i in range(15)]
CAPTION = " ".join(["word"] * 40)


def video(**over):
    data = {
        "title": "What to ask at your first visit", "summary": "A short video on preparing for a first consultation.",
        "hook": "Nervous about your first energy visit?",
        "scenes": [
            {"time": "0:00-0:05", "visual": "A calm reception.", "voiceover": "Nervous about your first visit?", "on_screen_text": "First visit?"},
            {"time": "0:05-0:40", "visual": "A notebook.", "voiceover": "Write your questions down first.", "on_screen_text": ""},
            {"time": "0:40-0:55", "visual": "Contact details.", "voiceover": "Book a consultation.", "on_screen_text": "Book a consultation"},
        ],
        "title_hook_options": [{"title": f"Option title number {i} for visit", "hook": f"Hook {i}?"} for i in (1, 2, 3)],
        "caption": CAPTION, "tags": TAGS, "hashtags": HASHTAGS, "closing_line": "Your questions matter.",
        "cta": "Book a consultation.", "reviewer_notes": ["General knowledge used."],
    }
    return {**data, **over}


def social(**over):
    data = {"title": "Questions before solar", "summary": "A post about preparing questions.", "post_copy": "Thinking about solar? Bring your questions.",
            "caption": CAPTION, "tags": TAGS, "hashtags": HASHTAGS, "carousel_slides": [], "closing_line": "Ask away.",
            "cta": "Book a consultation.", "reviewer_notes": []}
    return {**data, **over}


def page(**over):
    data = {"title": "Battery storage", "summary": "A guide.", "introduction": "Intro.", "sections": [{"heading": "How it works", "body": " ".join(["word"] * 1500)}],
            "conclusion": "Done.", "suggested_cta": "Book a consultation.",
            "faqs": [{"question": f"Question {i}?", "answer": f"Answer {i}."} for i in range(5)],
            "people_also_ask": [f"Related question {i}?" for i in range(5)], "reviewer_notes": []}
    return {**data, **over}


# --- the schemas ------------------------------------------------------------------------------

def test_which_requests_get_a_strict_schema():
    assert structured.typed_schema("video_script", "standard") and structured.typed_schema("social_post", "concise")
    assert structured.typed_schema("faq", "detailed") and structured.typed_schema("article", "detailed") and structured.typed_schema("blog", "detailed")
    for generic in (("article", "standard"), ("article", "concise"), ("blog", "standard"), ("general", "detailed")):
        assert structured.typed_schema(*generic) is None


def test_the_counts_are_part_of_the_schema():
    v = structured.typed_schema("video_script", "standard")["properties"]
    assert (v["tags"]["minItems"], v["tags"]["maxItems"]) == (15, 15) and (v["hashtags"]["minItems"], v["hashtags"]["maxItems"]) == (15, 15)
    assert (v["title_hook_options"]["minItems"], v["title_hook_options"]["maxItems"]) == (3, 3) and v["scenes"]["minItems"] == 2
    page_schema = structured.typed_schema("article", "detailed")["properties"]
    assert page_schema["faqs"]["minItems"] == page_schema["faqs"]["maxItems"] == 5 == page_schema["people_also_ask"]["maxItems"]
    for length, count in (("concise", 3), ("standard", 5), ("detailed", 8)):
        assert structured.typed_schema("faq", length)["properties"]["faqs"]["maxItems"] == count


@pytest.mark.parametrize("content_type,length", [("video_script", "standard"), ("social_post", "standard"), ("faq", "detailed"), ("article", "detailed")])
def test_every_field_is_required_and_nothing_else_is_allowed(content_type, length):
    schema = structured.typed_schema(content_type, length)
    assert set(schema["required"]) == set(schema["properties"]) and schema["additionalProperties"] is False


def test_loosen_drops_only_the_count_limits():
    schema = structured.typed_schema("video_script", "standard")
    loose = structured.loosen(schema)
    assert "minItems" not in json.dumps(loose) and "maxItems" not in json.dumps(loose)
    assert "minItems" in json.dumps(schema)  # the original is untouched
    assert set(loose["required"]) == set(schema["required"])


# --- assembling the fields ------------------------------------------------------------------------

def test_a_complete_video_assembles_into_a_layout_that_passes_every_format_check():
    content = structured.to_content("video_script", "standard", video())
    assert [s["heading"] for s in content["sections"]] == ["Screenplay", "Title and Hook Options", "Caption", "Tags", "Hashtags"]
    assert content["introduction"] == "Nervous about your first energy visit?" and content["conclusion"] == "Your questions matter."
    assert check_format("video_script", "standard", content) == []
    _validate_content(dict(content))  # also valid for the shared content model


def test_the_screenplay_is_laid_out_as_scenes():
    body = structured.to_content("video_script", "standard", video())["sections"][0]["body"]
    assert body.startswith("Scene 1 (0:00-0:05)\nVISUAL: A calm reception.\nVOICEOVER: Nervous about your first visit?\nON-SCREEN TEXT: First visit?")
    assert "Scene 2 (0:05-0:40)" in body and "ON-SCREEN TEXT: None" in body  # empty text becomes None


def test_title_and_hook_options_are_numbered_lines():
    body = structured.to_content("video_script", "standard", video())["sections"][1]["body"]
    assert body.split("\n")[0] == "1. Title: Option title number 1 for visit | Hook: Hook 1?" and len(body.split("\n")) == 3


def test_a_complete_social_post_passes_every_check_and_carousel_slides_are_optional():
    content = structured.to_content("social_post", "standard", social())
    assert [s["heading"] for s in content["sections"]] == ["Caption", "Tags", "Hashtags"]
    assert content["introduction"] == "Thinking about solar? Bring your questions." and check_format("social_post", "standard", content) == []
    with_slides = structured.to_content("social_post", "standard", social(carousel_slides=["One", "Two"]))
    assert with_slides["sections"][-1] == {"heading": "Carousel slides", "body": "Slide 1: One\nSlide 2: Two"}


def test_a_complete_detailed_page_passes_every_check():
    content = structured.to_content("article", "detailed", page())
    assert [s["heading"] for s in content["sections"]] == ["How it works", "Frequently Asked Questions", "People Also Ask"]
    assert check_format("article", "detailed", content) == []
    assert content["sections"][1]["body"].startswith("Q: Question 0?\nA: Answer 0.\n\nQ: Question 1?")


def test_faq_questions_become_sections():
    data = {"title": "FAQ", "summary": "s", "introduction": "i", "conclusion": "c", "suggested_cta": None, "reviewer_notes": [],
            "faqs": [{"question": f"Q{i}?", "answer": f"A{i}."} for i in range(5)]}
    content = structured.to_content("faq", "standard", data)
    assert [s["heading"] for s in content["sections"]] == [f"Q{i}?" for i in range(5)] and check_format("faq", "standard", content) == []


# --- cleaning and leniency -------------------------------------------------------------------------

def test_tags_and_hashtags_are_cleaned_deduplicated_and_capped():
    assert structured.clean_tags(["#Energy ", "energy", "solar  care", "", 7]) == ["Energy", "solar care"]
    assert structured.clean_hashtags(["energy", "#solar care", "#energy", "!!"]) == ["#energy", "#solarcare"]
    assert len(structured.clean_tags([f"t{i}" for i in range(40)])) == 15 and len(structured.clean_hashtags([f"h{i}" for i in range(40)])) == 15


def test_hashtags_always_start_with_one_hash_in_the_assembled_text():
    sections = structured.to_content("social_post", "standard", social(hashtags=["solar", "#solar", "Energy Care"], tags=[]))["sections"]
    body = next(sec["body"] for sec in sections if sec["heading"] == "Hashtags")
    assert body == "#solar #EnergyCare"


def test_missing_parts_are_left_out_so_the_checks_can_name_them():
    content = structured.to_content("video_script", "standard", video(caption="", title_hook_options=[], scenes=[], tags=TAGS[:9]))
    headings = [s["heading"] for s in content["sections"]]
    assert "Caption" not in headings and "Screenplay" not in headings and "Title and Hook Options" not in headings
    warnings = check_format("video_script", "standard", content)
    assert 'Missing the "Screenplay" section.' in warnings and 'Missing the "Caption" section.' in warnings
    assert "Expected 15 tags but found 9." in warnings


@pytest.mark.parametrize("garbage", [None, "text", 7, [1, 2], {"x": 1}])
def test_malformed_values_never_crash_the_assembly(garbage):
    data = video(scenes=garbage, title_hook_options=garbage, tags=garbage, hashtags=garbage, reviewer_notes=garbage, cta=garbage)
    content = structured.to_content("video_script", "standard", data)
    assert content["sections"] == [{"heading": "Caption", "body": CAPTION}] and content["reviewer_notes"] == []


def test_hashtags_that_lose_a_duplicate_are_topped_up_from_the_models_own_tags():
    tags = [f"topic {i}" for i in range(15)]
    hashtags = [f"#Tag{i}" for i in range(13)] + ["#tag0", "#TAG1"]  # 15 given, only 13 distinct
    body = structured.to_content("social_post", "standard", social(tags=tags, hashtags=hashtags))["sections"][2]["body"].split()
    assert len(body) == 15 and len({h.lower() for h in body}) == 15
    assert body[:13] == [f"#Tag{i}" for i in range(13)] and body[13] == "#Topic0"


def test_topping_up_never_invents_words_or_repeats_and_stops_when_tags_run_out():
    assert structured.top_up_hashtags([], ["energy care", "solar"]) == ["#EnergyCare", "#Solar"]
    assert structured.top_up_hashtags(["#solar"], ["solar", "solar"]) == ["#solar"]
    assert structured.top_up_hashtags([f"#h{i}" for i in range(15)], ["extra"]) == [f"#h{i}" for i in range(15)]


def test_a_complete_hashtag_set_is_left_exactly_as_the_model_wrote_it():
    content = structured.to_content("video_script", "standard", video())
    assert content["sections"][4]["body"] == " ".join(HASHTAGS)
