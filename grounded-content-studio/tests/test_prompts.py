import pytest

from app import llm, validation
from app.prompts import PROMPT_DIR, read_prompt

GENERATION_FILES = ["content_generation.txt", *llm.MODULE_FILES.values()]
VALIDATION_FILES = ["brand_validation.txt", "human_review.txt"]
HUMANIZE_FILE = "content_humanize.txt"


@pytest.mark.parametrize("name", GENERATION_FILES + VALIDATION_FILES + [HUMANIZE_FILE])
def test_every_prompt_is_version_1_0(name):
    assert "Version: 1.0" in read_prompt(name)


@pytest.mark.parametrize("name", GENERATION_FILES + VALIDATION_FILES + [HUMANIZE_FILE])
def test_each_prompt_file_holds_exactly_one_prompt(name):
    # Guards against pasting a second prompt below the first, which sends the model two
    # contradictory sets of rules.
    text = read_prompt(name)
    assert text.count("Version:") == 1
    assert text.count("\n# ") == 0 and text.startswith("# ")


@pytest.mark.parametrize("content_type", list(llm.CONTENT_GROUPS))
def test_system_prompt_stays_small_enough_for_local_models(content_type):
    system = llm.system_prompt(content_type)
    assert len(system) < 14000
    assert "reviewer_notes" in system and "Evidence discipline" in system


def test_every_content_type_has_a_module_and_budget():
    for content_type, group in llm.CONTENT_GROUPS.items():
        assert group in llm.MODULE_FILES and group in llm.TOKEN_BUDGETS and group in llm.LENGTH_GUIDANCE


def test_every_strict_schema_field_is_explained_in_the_prompt_the_model_receives():
    from app import structured
    for content_type, length in (("video_script", "standard"), ("social_post", "standard"), ("faq", "standard"), ("article", "detailed")):
        system = llm.system_prompt(content_type)
        for field in structured.typed_schema(content_type, length)["properties"]:
            assert field in system, f"{field} is in the {content_type} schema but not in its prompt"


def test_the_strict_formats_are_described_with_their_counts():
    video = read_prompt("content_video.txt")
    assert "exactly 3 items" in video and video.count("exactly 15") == 2 and "title_hook_options" in video
    social = read_prompt("content_social.txt")
    assert social.count("exactly 15") == 2 and "post_copy" in social
    assert "faqs" in read_prompt("content_faq.txt") and "exactly five" in read_prompt("content_website.txt")


def test_the_core_prompt_no_longer_describes_a_fixed_section_layout():
    core = read_prompt("content_generation.txt")
    assert "matches the provided schema exactly" in core and "Use only the fields of the provided schema." in core



def test_brand_prompt_matches_the_fields_and_enums_the_code_checks():
    text = read_prompt("brand_validation.txt")
    for token in ["MISLEADING_PROMISE", "GUIDELINE_GAP", "severity", "recommended_action", "KEEP"]:
        assert token in text
    assert validation.NO_GUIDELINES.split(".")[0] in text or "no separate approved guidelines" in text


def test_humanize_prompt_is_versioned_and_protects_what_the_code_protects():
    text = read_prompt(HUMANIZE_FILE)
    assert "Version: 1.0" in text
    for heading in ("Frequently Asked Questions", "People Also Ask", "Screenplay", "Title and Hook Options", "Caption", "Tags", "Hashtags"):
        assert f'"{heading}"' in text
    # Same headings the code restores verbatim.
    from app.humanize import FIXED_HEADINGS
    for fixed in FIXED_HEADINGS:
        assert fixed.lower() in text.lower()
    assert "reviewer_notes" in text and "editing_notes" in text and len(text) < 13000


def test_humanize_examples_contain_no_facts_to_copy():
    text = read_prompt(HUMANIZE_FILE)
    examples = text[text.index("## 4b."):text.index("## 5.")]
    for risky in ("%", "success", "per cycle", "guarantee"):
        assert risky.lower() not in examples.lower(), risky


def test_the_prompts_forbid_advertising_language_and_invented_human_details():
    core = read_prompt("content_generation.txt")
    assert "not like an advertisement" in core and "at most one exclamation mark" in core
    humanize = read_prompt(HUMANIZE_FILE)
    assert "Specific, not promotional" in humanize and "Do not add customer stories" in humanize
    assert "Remove it and add a short note to reviewer_notes" in humanize


def test_the_social_prompt_keeps_hashtags_out_of_the_post_copy_and_the_core_bans_invented_practice():
    assert "Do not put hashtags in it" in read_prompt("content_social.txt")
    assert "Do not describe how the company works" in read_prompt("content_generation.txt")


def test_prompts_use_placeholders_instead_of_a_hardcoded_company_name():
    core = (PROMPT_DIR / "content_generation.txt").read_text(encoding="utf-8")
    assert "{{company_name}}" in core and "{{website_url}}" in core
    for path in PROMPT_DIR.glob("*.txt"):
        text = path.read_text(encoding="utf-8")
        assert "Example Co" not in text and "example.com" not in text, path.name


def test_the_shipped_prompts_use_only_known_placeholders():
    import re
    from app.company import PLACEHOLDERS, PLACEHOLDER_RE
    for path in PROMPT_DIR.glob("*.txt"):
        assert set(PLACEHOLDER_RE.findall(path.read_text(encoding="utf-8"))) <= set(PLACEHOLDERS), path.name


def test_brief_video_prompt_is_loaded_for_brief_requests_and_explains_every_schema_field():
    from app import structured
    system = llm.system_prompt(structured.BRIEF_VIDEO)
    assert "Brief-Driven Presenter-Led Video" in system and "Brief-Driven" not in llm.system_prompt("video_script")
    for field in structured.typed_schema(structured.BRIEF_VIDEO, "standard")["properties"]:
        assert field in system, field
    for key in ("segments", "approved_hook", "approved_cta", "approved_claims", "approved_hashtags", "required_disclaimer", "spoken_word_budget"):
        assert key in system, key


def test_validator_prompts_carry_the_brief_rules():
    assert "brief_brand_rules" in read_prompt("brand_validation.txt") and "customer-count" in read_prompt("brand_validation.txt")
    assert "self_check_items" in read_prompt("human_review.txt") and "accuracy_concerns" in read_prompt("human_review.txt")
