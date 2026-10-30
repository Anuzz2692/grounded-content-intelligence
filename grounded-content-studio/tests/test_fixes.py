from app.fixes import suggest_wording_fixes


def page(**kw):
    base = {"title": "Battery storage", "summary": "A short guide.", "introduction": "Thinking about adding batteries?",
            "conclusion": "Your specialist can explain what to expect.", "suggested_cta": None, "sections": []}
    return {**base, **kw}


def section(heading, body):
    return {"heading": heading, "body": body}


def test_each_risky_sentence_gets_its_own_suggestion():
    content = page(sections=[
        section("How it works", "We use load balancing to ensure the best efficiency rates. Cells are installed carefully. "
                                "Our success rate is 60-80% per cycle."),
        section("Next steps", "Ready to learn more? Book a free consultation with Example Co today!"),
    ])
    fixes = suggest_wording_fixes(content, ["Our company offers battery storage."])
    by_original = {f["original_text"]: f for f in fixes}

    assert len(fixes) == 3
    assert by_original["We use load balancing to ensure the best efficiency rates."]["suggested_text"] == ""
    assert by_original["Our success rate is 60-80% per cycle."]["suggested_text"] == ""
    assert "statistic" in by_original["Our success rate is 60-80% per cycle."]["reason"]
    free = by_original["Book a free consultation with Example Co today!"]
    assert free["suggested_text"] == "Book a consultation with Example Co today!"


def test_original_text_is_always_an_exact_piece_of_the_draft():
    body = "Intro line.\nWe guarantee results.   Second  sentence stays."
    content = page(sections=[section("A", body)])
    for fix in suggest_wording_fixes(content, ["x"]):
        assert fix["original_text"] in body


def test_wording_that_the_website_supports_is_not_suggested_for_removal():
    evidence = ["We offer a free consultation. Success rates: 45% in 2023. The best option for many."]
    content = page(sections=[section("A", "Book a free consultation. About 45% of cycles. The best option for many.")])
    assert suggest_wording_fixes(content, evidence) == []


def test_a_fix_that_would_empty_the_whole_field_is_not_offered():
    content = page(conclusion="This treatment is guaranteed.", sections=[section("A", "Calm text here.")])
    assert suggest_wording_fixes(content, ["x"]) == []


def test_tags_hashtags_and_reviewer_notes_are_left_alone():
    content = page(sections=[section("Tags", "best, guaranteed, 100%"), section("Hashtags", "#1 #best"), section("A", "Plain.")],
                   reviewer_notes=["Removed the 100% claim."])
    assert suggest_wording_fixes(content, ["x"]) == []


def test_the_call_to_action_can_be_fixed_when_other_text_remains():
    content = page(suggested_cta="Claim your free consultation today.")
    fixes = suggest_wording_fixes(content, ["x"])
    assert fixes == [{"original_text": "Claim your free consultation today.",
                      "suggested_text": "Claim your consultation today.", "reason": fixes[0]["reason"]}]


def test_offers_other_than_free_visits_are_removed_not_edited():
    content = page(sections=[section("A", "Energy care explained. Enjoy a limited-time discount. More follows.")])
    fix = suggest_wording_fixes(content, ["x"])[0]
    assert fix["original_text"] == "Enjoy a limited-time discount." and fix["suggested_text"] == ""


def test_repeated_sentences_and_the_cap():
    content = page(sections=[section("A", "Guaranteed. " + "Keep going. " * 2 + "Guaranteed.")])
    assert len(suggest_wording_fixes(content, ["x"])) == 1
    many = page(sections=[section("A", " ".join(f"Result {i} is guaranteed to work." for i in range(30)) + " Fine.")])
    assert len(suggest_wording_fixes(many, ["x"], limit=5)) == 5


def test_a_trailing_claim_clause_is_trimmed_so_a_one_sentence_summary_still_gets_a_fix():
    content = page(summary="Learn about battery storage, a key part of solar that helps increase your chances of saving.")
    fixes = suggest_wording_fixes(content, ["Battery storage holds charge."])
    assert fixes == [{"original_text": "Learn about battery storage, a key part of solar that helps increase your chances of saving.",
                      "suggested_text": "Learn about battery storage.", "reason": fixes[0]["reason"]}]
    assert "trailing clause" in fixes[0]["reason"]


def test_only_the_clause_with_the_claim_is_cut():
    content = page(sections=[section("A", "At Example Co, we tailor each protocol to your unique needs, ensuring safety and effectiveness. Fine sentence.")])
    evidence = ["At Example Co we tailor each protocol to your unique needs."]  # the company claim itself is supported
    fix = suggest_wording_fixes(content, evidence)[0]
    assert fix["suggested_text"] == "At Example Co, we tailor each protocol to your unique needs."


def test_a_sentence_with_no_clause_to_cut_is_still_removed_whole():
    content = page(sections=[section("A", "Boost your chances of saving with battery storage. Fine sentence.")])
    assert suggest_wording_fixes(content, ["x"])[0]["suggested_text"] == ""


def test_a_clause_cut_that_would_leave_too_little_is_not_used():
    content = page(sections=[section("A", "Yes, we guarantee results. Fine sentence.")])
    assert suggest_wording_fixes(content, ["x"])[0]["suggested_text"] == ""


def test_an_ungrounded_statement_about_how_the_company_works_is_removed_whole():
    content = page(sections=[section("A", "At Example Co, we tailor protocols based on your roof angle, tariff, and usage. Fine sentence here.")])
    fix = suggest_wording_fixes(content, ["Battery storage holds charge for later use."])[0]
    assert fix["suggested_text"] == "" and "what the company does" in fix["reason"]
