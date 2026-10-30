import pytest

from app.naturalness import analyse, clean, editing_notes


def page(**kw):
    base = {"title": "Understanding solar", "summary": "A short guide.", "introduction": "Plain start.", "conclusion": "Plain end.",
            "suggested_cta": None, "sections": []}
    return {**base, **kw}


def section(heading, body):
    return {"heading": heading, "body": body}


STIFF = page(
    introduction="In today's fast-paced world, many people face high bills. It's important to note that solar has several steps. Let's dive into the basics!",
    sections=[section("The steps", "When it comes to solar, the process is long. Solar involves stimulation. Solar involves retrieval. Solar involves transfer. Rest assured, your specialist will explain.")],
    conclusion="In conclusion, ask your specialist. Are you ready? Are you sure? Are you here?",
)


# --- measuring ---------------------------------------------------------------------------------

def test_stock_phrases_are_found_and_overlaps_counted_once():
    report = analyse(STIFF)
    lowered = [p.lower() for p in report.phrases]
    assert "let's dive into" in lowered and "dive into" not in lowered  # not double counted
    for expected in ("in today's fast-paced world", "it's important to note that", "when it comes to", "rest assured", "in conclusion"):
        assert expected in lowered


def test_repeated_openers_questions_and_exclamations_are_counted():
    report = analyse(STIFF)
    assert report.repeated_openers == 4  # Solar involves x3 (2 repeats) and Are you x3 (2 repeats)
    assert report.questions == 3 and report.exclamations == 1
    assert report.issues == len(report.phrases) + 4 + 1  # one question over the limit of two


def test_a_clean_draft_has_no_issues():
    clean_page = page(introduction="Starting solar can raise many questions. This guide covers the basics.",
                      sections=[section("The steps", "Treatment starts with a consultation. Your specialist explains each step and what it involves.")])
    report = analyse(clean_page)
    assert report.issues == 0 and report.phrases == []


def test_common_openers_are_not_flagged():
    text = "The first step is a consultation. The second is a scan. The third is a plan."
    assert analyse(page(sections=[section("Steps", text)])).repeated_openers == 0


def test_only_prose_is_measured_not_tags_questions_or_titles():
    content = page(title="In today's world: a guide", sections=[
        section("Tags", "journey, journey, journey, journey"), section("Hashtags", "#journey #journey #journey"),
        section("Frequently Asked Questions", "Q: When it comes to cost?\nA: It varies."),
        section("Title and Hook Options", "1. Title: Let's dive into solar | Hook: Ready?")])
    assert analyse(content).issues == 0


def test_screenplay_layout_lines_are_not_treated_as_sentences():
    body = "Scene 1 (0:00-0:05)\nVISUAL: A calm company!\nVOICEOVER: Start with questions.\nON-SCREEN TEXT: Questions!"
    report = analyse(page(summary="", introduction="", conclusion="", sections=[section("Screenplay", body)]))
    assert report.exclamations == 0 and report.sentences == 1  # only the spoken line counts


def test_the_word_journey_is_flagged_only_when_overused():
    assert analyse(page(introduction="Your journey starts here. The journey has steps.")).issues == 0
    assert analyse(page(introduction="Your journey starts here. The journey has steps. Every journey differs.")).issues >= 1


def test_uniform_sentence_rhythm_is_reported_but_not_counted_as_an_issue():
    uniform = " ".join(["This is a short sentence here."] * 8)
    report = analyse(page(sections=[section("A", uniform)]))
    assert report.rhythm is not None and report.rhythm < 0.35 and report.issues == report.repeated_openers
    assert "uniform" in editing_notes(report)


def test_rhythm_needs_enough_sentences():
    assert analyse(page(sections=[section("A", "One sentence only.")])).rhythm is None


# --- notes for the rewrite ----------------------------------------------------------------------------

def test_editing_notes_name_the_specific_problems():
    notes = editing_notes(analyse(STIFF))
    assert 'Stock phrases to rewrite or remove: "in today\'s fast-paced world"' in notes
    assert "start with the same word" in notes and "3 rhetorical questions" in notes and notes.startswith("- ")


def test_no_notes_when_there_is_nothing_to_fix():
    assert editing_notes(analyse(page())) == ""


# --- cleanup -------------------------------------------------------------------------------------------

def test_cleanup_removes_filler_and_fixes_capitalisation():
    cleaned = clean(STIFF)
    assert cleaned["introduction"] == "Many people face high bills. Solar has several steps. Let's look at the basics!"
    assert cleaned["sections"][0]["body"].endswith("Your specialist will explain.")
    assert cleaned["conclusion"].startswith("Ask your specialist.")


def test_cleanup_reduces_the_measured_issues_and_never_adds_any():
    before, after = analyse(STIFF), analyse(clean(STIFF))
    assert after.issues < before.issues and len(after.phrases) < len(before.phrases)


def test_cleanup_keeps_mid_sentence_text_in_place():
    out = clean(page(introduction="Most people ask, in today's world, many questions."))["introduction"]
    assert out == "Most people ask, many questions."


def test_cleanup_leaves_tags_hashtags_and_structure_alone():
    content = page(sections=[section("Tags", "rest assured, in conclusion"), section("Hashtags", "#restassured"),
                             section("Title and Hook Options", "1. Title: A comprehensive guide to solar | Hook: Go")])
    assert clean(content)["sections"] == content["sections"]


def test_cleanup_does_not_change_its_input():
    original = {**STIFF, "sections": [dict(s) for s in STIFF["sections"]]}
    clean(STIFF)
    assert STIFF == original


def test_cleanup_is_idempotent_and_keeps_line_breaks():
    once = clean(page(sections=[section("A", "Rest assured, line one.\nIt is important to note that line two.")]))
    assert once["sections"][0]["body"] == "Line one.\nLine two." and clean(once) == once


@pytest.mark.parametrize("text,expected", [
    ("A comprehensive guide to energy testing", "A guide to energy testing"),
    ("Navigating the complexities of treatment", "Understanding treatment"),
    ("We delve into the details.", "We look at the details."),
])
def test_simple_phrase_swaps(text, expected):
    assert clean(page(introduction=text))["introduction"] == expected


# --- advertising boilerplate ------------------------------------------------------------------

AD = page(
    summary="Learn about battery storage.",
    introduction=("Battery storage is a crucial step in solar. At the company, we tailor each protocol to your unique needs. "
                  "Book a consultation today! Ready to take the first step? Call us today!"),
)


def test_advertising_boilerplate_is_flagged():
    phrases = [p.lower() for p in analyse(AD).phrases]
    for expected in ("a crucial step in", "tailor each protocol to your", "ready to take"):  # "your unique needs" overlaps the longer match and is counted once
        assert any(expected in p for p in phrases), expected
    assert any("today" in p for p in phrases)


def test_a_trailing_today_is_dropped_from_calls_to_action_only():
    out = clean(page(introduction="Book a consultation today. We saw this today. Call the company today! Book a visit today to learn more."))["introduction"]
    assert out == "Book a consultation. We saw this today. Call the company! Book a visit to learn more."


def test_only_one_exclamation_mark_is_kept_in_the_whole_text():
    content = page(summary="Welcome!", introduction="Ask us! Really!!", sections=[section("A", "Great! Fine.")], conclusion="Done!")
    out = clean(content)
    text = " ".join([out["summary"], out["introduction"], out["sections"][0]["body"], out["conclusion"]])
    assert text.count("!") == 1 and out["summary"] == "Welcome!" and out["conclusion"] == "Done."
    assert analyse(out).exclamations == 0 or analyse(out).exclamations == 1


def test_exclamations_in_tags_and_hashtags_are_left_alone():
    content = page(sections=[section("Tags", "wow!, yes!"), section("Hashtags", "#yes!")])
    assert clean(content)["sections"] == content["sections"]


# --- unsupported "free" offers ----------------------------------------------------------------------------

def test_free_is_dropped_from_an_offer_the_website_does_not_make():
    content = page(introduction="Book a free consultation. A free first visit helps. Free parking is nearby.")
    out = clean(content, ["We offer consultations by appointment."])["introduction"]
    assert out == "Book a consultation. A first visit helps. Free parking is nearby."


def test_free_is_kept_when_the_website_says_it():
    content = page(introduction="Book a free consultation.")
    assert clean(content, ["New customers get a free consultation."])["introduction"] == "Book a free consultation."


def test_without_evidence_the_clean_up_leaves_offers_alone_by_default():
    # clean(content) with no evidence argument keeps the old behaviour of only removing filler.
    content = page(introduction="Book a free consultation.")
    assert clean(content)["introduction"] == "Book a consultation."


# --- hashtags pasted into the post copy ---------------------------------------------------------------------

def test_hashtags_at_the_end_of_prose_are_removed_when_a_hashtags_section_exists():
    content = page(introduction="Ask your questions first. #EnergyAwareness #SolarSupport",
                   sections=[section("Caption", "Bring a list. #questions"), section("Hashtags", "#EnergyAwareness #SolarSupport #questions")])
    out = clean(content)
    assert out["introduction"] == "Ask your questions first." and out["sections"][0]["body"] == "Bring a list."
    assert out["sections"][1]["body"] == "#EnergyAwareness #SolarSupport #questions"


def test_hashtags_in_the_middle_of_a_sentence_or_without_a_hashtags_section_are_left_alone():
    with_section = clean(page(introduction="Follow #solar news today.", sections=[section("Hashtags", "#solar")]))
    assert with_section["introduction"] == "Follow #solar news today."
    without = page(introduction="Ask first. #solar #Support")
    assert clean(without)["introduction"] == "Ask first. #solar #Support"


def test_a_field_that_is_only_hashtags_is_not_emptied():
    content = page(introduction="#solar #Support", sections=[section("Hashtags", "#solar #Support")])
    assert clean(content)["introduction"] == "#solar #Support"
