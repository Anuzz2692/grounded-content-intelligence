import pytest

from app.format_checks import check_format


def section(heading, body):
    return {"heading": heading, "body": body}


def content(sections=None, title="Understanding energy testing basics today", summary="s", intro="i", conclusion="c"):
    return {"title": title, "summary": summary, "introduction": intro, "sections": sections or [], "conclusion": conclusion}


def words(n):
    return " ".join(["word"] * n)


HASHTAGS = " ".join(f"#tag{i}" for i in range(15))
TAGS = ", ".join(f"tag {i}" for i in range(15))


# --- website ----------------------------------------------------------------

def faq_body(n):
    return "\n\n".join(f"Q: Question {i}?\nA: Answer {i}." for i in range(n))


def paa_body(n):
    return "\n".join(f"- Question {i}?" for i in range(n))


def full_page(article_words=1500, faqs=5, paa=5):
    return content(
        [section("Body", words(article_words)), section("Frequently Asked Questions", faq_body(faqs)),
         section("People Also Ask", paa_body(paa))],
        intro="", conclusion="",
    )


def test_complete_detailed_page_has_no_warnings():
    assert check_format("article", "detailed", full_page()) == []


def test_faq_and_paa_words_do_not_count_towards_the_article():
    # 1,500 article words plus long FAQ answers must not push it over the range.
    page = full_page()
    page["sections"][1]["body"] = "\n\n".join(f"Q: Q{i}?\nA: {words(200)}" for i in range(5))
    assert check_format("article", "detailed", page) == []


def test_word_range_has_a_ten_percent_tolerance():
    assert check_format("article", "detailed", full_page(1300)) == []
    assert "main article is 1000 words" in check_format("article", "detailed", full_page(1000))[0].lower()
    assert check_format("article", "detailed", full_page(2200))[0].endswith("target is 1400-1800.")


def test_wrong_faq_and_paa_counts_and_missing_sections_are_reported():
    warnings = check_format("blog", "detailed", full_page(faqs=4, paa=6))
    assert "Expected 5 FAQs but found 4." in warnings
    assert "Expected 5 People Also Ask questions but found 6." in warnings
    missing = check_format("article", "detailed", content([section("Body", words(1500))], intro="", conclusion=""))
    assert 'Missing the "Frequently Asked Questions" section.' in missing
    assert 'Missing the "People Also Ask" section.' in missing


def test_shorter_lengths_do_not_require_faqs():
    assert check_format("article", "standard", content([section("Body", words(950))], intro="", conclusion="")) == []
    assert check_format("article", "concise", content([section("Body", words(500))], intro="", conclusion="")) == []


# --- social ------------------------------------------------------------------

def social(caption=words(40), tags=TAGS, hashtags=HASHTAGS):
    return content([section("Caption", caption), section("Tags", tags), section("Hashtags", hashtags)])


def test_good_social_post_has_no_warnings():
    assert check_format("social_post", "standard", social()) == []


def test_social_post_counts_are_checked():
    warnings = check_format("social_post", "standard", social(caption=words(60), tags="a, b", hashtags="#one #two"))
    assert "The caption is 60 words; the target is 30-50." in warnings
    assert "Expected 15 tags but found 2." in warnings
    assert "Expected 15 hashtags but found 2." in warnings


def test_tags_and_hashtags_sections_are_not_confused():
    # "Hashtags" contains the word "tags"; it must not be read as the Tags section.
    warnings = check_format("social_post", "standard", social(hashtags="#a #b #c"))
    assert warnings == ["Expected 15 hashtags but found 3."]


def test_missing_social_sections_are_reported():
    warnings = check_format("social_post", "standard", content([]))
    assert {'Missing the "Caption" section.', 'Missing the "Tags" section.', 'Missing the "Hashtags" section.'} <= set(warnings)


# --- video -------------------------------------------------------------------

SCREENPLAY = (
    "Scene 1 (0:00-0:05)\nVISUAL: A calm company reception, illustrative.\nVOICEOVER: Nervous about your first visit?\n"
    "ON-SCREEN TEXT: First visit?\n\n"
    "Scene 2 (0:05-0:40)\nVISUAL: Notebook with questions.\nVOICEOVER: Write down your questions first.\nON-SCREEN TEXT: None\n\n"
    "Scene 3 (0:40-0:55)\nVISUAL: Contact screen.\nVOICEOVER: Book a consultation to talk it through.\nON-SCREEN TEXT: Book a consultation"
)
OPTIONS = ("1. Title: What to ask at your first visit | Hook: Nervous about your first energy visit?\n"
           "2. Title: Three myths about first appointments | Hook: Think you need all the answers?\n"
           "3. Title: Prepare for your first consultation | Hook: Here is what to bring with you.")


def video(title="What to ask at your first visit", screenplay=SCREENPLAY, options=OPTIONS, caption=words(45), cta="Book a consultation."):
    sections = [section("Screenplay", screenplay), section("Title and Hook Options", options), section("Caption", caption),
                section("Tags", TAGS), section("Hashtags", HASHTAGS)]
    page = content(sections, title=title)
    page["suggested_cta"] = cta
    return page


def test_good_video_has_no_warnings():
    assert check_format("video_script", "standard", video()) == []


def test_video_title_and_caption_lengths():
    warnings = check_format("video_script", "standard", video(title="Too short", caption=words(20)))
    assert "The video title is 2 words; the target is 5-9." in warnings
    assert "The caption is 20 words; the target is 30-60." in warnings


def test_screenplay_needs_scenes_and_voiceover():
    one_scene = "Scene 1 (0:00-0:05)\nVISUAL: x\nVOICEOVER: hello"
    assert "The screenplay has 1 scene(s); it needs at least 2." in check_format("video_script", "standard", video(screenplay=one_scene))
    no_voice = "Scene 1\nVISUAL: x\n\nScene 2\nVISUAL: y"
    assert "The screenplay has no VOICEOVER lines." in check_format("video_script", "standard", video(screenplay=no_voice))


def test_exactly_three_title_and_hook_options():
    two = "\n".join(OPTIONS.split("\n")[:2])
    assert "Expected 3 title and hook options but found 2." in check_format("video_script", "standard", video(options=two))


def test_video_requires_a_cta_and_all_sections():
    assert "Missing the call to action." in check_format("video_script", "standard", video(cta=""))
    warnings = check_format("video_script", "standard", content([], title="What to ask at your first visit"))
    for expected in ('Missing the "Screenplay" section.', 'Missing the "Title and Hook Options" section.',
                     'Missing the "Caption" section.', 'Missing the "Tags" section.', 'Missing the "Hashtags" section.'):
        assert expected in warnings


# --- faq / other ---------------------------------------------------------------

def test_faq_question_count_follows_length():
    five = content([section(f"Q{i}?", "A.") for i in range(5)])
    assert check_format("faq", "standard", five) == []
    assert check_format("faq", "detailed", five) == ["Expected 8 questions but found 5."]


def test_general_content_is_not_checked():
    assert check_format("general", "detailed", content([section("x", "y")])) == []


# --- risky wording ---------------------------------------------------------------

from app.format_checks import check_risky_claims


def risky(**fields):
    base = {"title": "t", "summary": "s", "introduction": "i", "conclusion": "c", "sections": []}
    return {**base, **fields}


def test_statistics_offers_and_unsupported_claims_are_all_caught():
    page = risky(
        summary="Learn how we can help you save money. Book a free consultation today!",
        sections=[section("Video script", "Our batteries reach efficiency rates of 60-80% per cycle.")],
    )
    warnings = check_risky_claims(page, ["Our company offers batteries and consultation."])
    joined = " ".join(warnings)
    assert 'statistic ("60-80%")' in joined
    assert 'offer ("free consultation")' in joined


def test_wording_that_is_in_the_website_research_is_allowed():
    evidence = ["We offer a free consultation. Our company reports a 45% reduction in bills (2023). We are the best known."]
    page = risky(introduction="Book a free consultation.", conclusion="About 45% of bills... and we are the best.")
    assert check_risky_claims(page, evidence) == []


def test_absolutes_and_superlatives_are_reported_unless_supported():
    page = risky(introduction="A guaranteed, risk-free installation from the best company.")
    warnings = " ".join(check_risky_claims(page, ["nothing relevant"]))
    assert "guaranteed" in warnings and "risk-free" in warnings and '"best"' in warnings


def test_reviewer_notes_are_not_scanned():
    page = risky(reviewer_notes=["No 100% claim was made; success rates were left out."])
    assert check_risky_claims(page, ["x"]) == []


def test_clean_cautious_wording_is_not_flagged():
    page = risky(introduction="Savings depend on many individual factors. The installer can explain what to expect.",
                 sections=[section("Next step", "Ask about the survey and what the results mean.")])
    assert check_risky_claims(page, ["x"]) == []


def test_each_problem_is_reported_once():
    page = risky(introduction="Guaranteed. Guaranteed. Guaranteed.")
    assert len(check_risky_claims(page, ["x"])) == 1


# --- benefit and result claims ---------------------------------------------------------------

SHOUTY_POST = risky(
    summary="Learn about battery storage, a key part of a solar system that helps increase your chances of saving.",
    introduction=("Battery storage is a crucial step in going solar, using a stored charge to cover evening demand. "
                  "At Example Co, we tailor each design to your unique needs, ensuring success and efficiency. "
                  "Book a free consultation today to learn more!"),
    sections=[section("Caption", "Boost your chances of saving with battery storage. Book a free consultation at Example Co today!")],
    conclusion="Ready to take the first step? Book a free consultation today!",
)


def test_benefit_and_result_claims_are_flagged():
    messages = " ".join(check_risky_claims(SHOUTY_POST, ["Battery storage holds charge for later use."]))
    assert '"increase your chances of saving"' in messages
    assert '"ensuring success"' in messages
    assert '"Boost your chances of saving"' in messages
    assert 'offer ("free consultation")' in messages


@pytest.mark.parametrize("phrase", [
    "This improves your chances.", "A safe and effective option.", "Proven to work.", "We maximise your odds.",
    "The highest success in the region.", "It ensures success for most people.",
])
def test_other_efficacy_wording_is_flagged(phrase):
    assert check_risky_claims(risky(introduction=phrase), ["x"])


def test_careful_wording_about_chances_is_not_flagged():
    page = risky(introduction="Your installer can explain what affects the savings in your situation.",
                 sections=[section("A", "Warranty terms are discussed at the consultation.")])
    assert check_risky_claims(page, ["x"]) == []


def test_efficacy_wording_the_website_itself_uses_is_allowed():
    assert check_risky_claims(risky(introduction="We aim to improve your chances."), ["Our aim is to improve your chances."]) == []


def test_each_flagged_sentence_in_that_post_gets_its_own_suggested_removal():
    from app.fixes import suggest_wording_fixes
    fixes = suggest_wording_fixes(SHOUTY_POST, ["Battery storage holds charge for later use."])
    originals = [f["original_text"] for f in fixes]
    assert "At Example Co, we tailor each design to your unique needs, ensuring success and efficiency." in originals
    assert "Boost your chances of saving with battery storage." in originals
    assert any("consultation" in o for o in originals)
    removals = {f["original_text"]: f["suggested_text"] for f in fixes}
    assert removals["Boost your chances of saving with battery storage."] == ""


# --- invented details ----------------------------------------------------------------------------------

THIN = ["Battery storage holds charge for later use. Consultations are available by appointment."]
INVENTED = risky(introduction=("Battery storage holds charge for later use. "
                               "At Example Co, we tailor designs based on your roof angle, tariff, and usage data. "
                               "This design maximizes savings."))


def test_invented_company_practice_and_efficacy_wording_is_flagged():
    messages = check_risky_claims(INVENTED, THIN)
    joined = " ".join(messages)
    assert "what the company does" in joined and "we tailor designs based on your roof angle" in joined
    assert 'benefit or result' in joined and '"maximizes savings"' in joined


@pytest.mark.parametrize("phrase", ["It improves performance.", "We maximise your chances.", "Enhances outcomes for most."])
def test_more_benefit_wording_is_flagged(phrase):
    assert check_risky_claims(risky(introduction=phrase), ["x"])


def test_a_statement_about_the_company_that_the_research_supports_is_not_flagged():
    evidence = ["At Example Co our specialists tailor each design to the customer after reviewing roof angle, tariff and usage data."]
    assert check_risky_claims(risky(introduction="At Example Co, we tailor designs based on your roof angle, tariff and usage data."), evidence) == []


def test_invitations_questions_and_general_statements_are_not_treated_as_company_claims():
    page = risky(introduction="Book a consultation at Example Co. Would you like to ask us a question? Battery storage holds charge.",
                 conclusion="Contact our team to talk through your options.")
    assert check_risky_claims(page, ["Completely unrelated text about parking and opening hours."]) == []


def test_short_company_sentences_are_not_judged():
    assert check_risky_claims(risky(introduction="We are here to help."), ["unrelated"]) == []
