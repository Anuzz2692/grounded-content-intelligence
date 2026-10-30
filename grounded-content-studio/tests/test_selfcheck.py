import copy

import pytest

from app import selfcheck
from app.brief import Brief, count_words, word_budget
from tests.brief_fixture import CTA, DISCLAIMER, HOOK, make_brief, make_typed


def status(checks, id):
    return next(c for c in checks if c["id"] == id)["status"]


def run(typed=None, brief=None):
    return selfcheck.deterministic_checks(brief or make_brief(), make_typed() if typed is None else typed)


def scene(typed, n, **fields):
    typed["scenes"][n].update(fields)
    return typed


def test_a_compliant_script_passes_every_deterministic_check():
    checks = run()
    assert [c["id"] for c in checks if c["status"] != selfcheck.PASS] == []
    assert len(checks) == 19  # the 20th, contradictions, and the validators check come from build_report


def test_the_word_budget_follows_the_formula():
    target, low, high = word_budget(60)
    assert round(target) in (126, 127) and (low, high) == (114, 139)
    assert word_budget(30)[0] == 25 * 2.3


def test_word_counting_handles_contractions_and_hyphens_consistently():
    assert count_words("It's a well-known test, isn't it?") == 6
    assert count_words("") == 0


def test_only_spoken_lines_are_counted():
    typed = make_typed()
    base = selfcheck.word_count(typed)
    scene(typed, 1, visual="word " * 50, on_screen_text="extra words here", subtitle="many many many words")
    typed["caption"] += " lots of extra caption words"
    assert selfcheck.word_count(typed) == base


@pytest.mark.parametrize("extra, expected", [(" word" * 40, selfcheck.FAIL), ("", selfcheck.PASS)])
def test_a_script_over_the_range_fails(extra, expected):
    typed = make_typed()
    scene(typed, 2, spoken_line=typed["scenes"][2]["spoken_line"] + extra)
    assert status(run(typed), "word_count") == expected


def test_a_script_under_the_range_fails():
    typed = make_typed()
    scene(typed, 2, spoken_line="Installers may suggest a backup battery for homes with frequent outages.")
    check = next(c for c in run(typed) if c["id"] == "word_count")
    assert check["status"] == selfcheck.FAIL and "allowed 114-139" in check["detail"] and "not a guarantee" in check["detail"]


def test_the_word_count_boundaries_are_inclusive():
    typed = make_typed()
    for target in (114, 139):
        words = selfcheck.word_count(typed)
        scene(typed, 2, spoken_line=typed["scenes"][2]["spoken_line"] + " word" * (target - words) if target > words else " ".join(typed["scenes"][2]["spoken_line"].split()[: len(typed["scenes"][2]["spoken_line"].split()) - (words - target)]))
        assert selfcheck.word_count(typed) == target and status(run(typed), "word_count") == selfcheck.PASS


def test_segment_durations_must_add_up_to_the_target():
    assert make_brief().structure_problem() is None
    assert "add up to 59" in make_brief(segments=[{"name": "A", "seconds": 30}, {"name": "B", "seconds": 29}]).structure_problem()
    bad = run(brief=make_brief(segments=[{"name": "A", "seconds": 30}, {"name": "B", "seconds": 29}]))
    assert status(bad, "brief_compliance") == selfcheck.FAIL


@pytest.mark.parametrize("change", [
    {"time": "0:04-0:14"},                      # gap: scene 1 starts at 4 but nothing covers 0-4... overlaps with scene 2
    {"time": "garbage"},
])
def test_scene_times_must_be_continuous_and_valid(change):
    typed = scene(make_typed(), 0, **change)
    assert status(run(typed), "duration") == selfcheck.FAIL


def test_the_scenes_must_end_at_the_duration_and_follow_the_segments():
    typed = scene(make_typed(), 4, time="0:56-0:59")
    assert status(run(typed), "duration") == selfcheck.FAIL
    typed = scene(make_typed(), 1, segment="Explanation")
    assert status(run(typed), "duration") == selfcheck.FAIL


def test_a_different_duration_without_segments_only_needs_continuous_times():
    brief = make_brief(duration_seconds=30)
    typed = make_typed()
    for s, (a, b) in zip(typed["scenes"], [("0:00", "0:03"), ("0:03", "0:08"), ("0:08", "0:20"), ("0:20", "0:26"), ("0:26", "0:30")]):
        s["time"] = f"{a}-{b}"
    assert status(selfcheck.deterministic_checks(brief, typed), "duration") == selfcheck.PASS


@pytest.mark.parametrize("hook", [HOOK + ".", HOOK.lower(), "A spec sheet can look impressive but not tell the whole story"])
def test_the_hook_must_match_exactly(hook):
    typed = scene(make_typed(), 0, spoken_line=hook)
    assert status(run(typed), "hook") == selfcheck.FAIL
    assert status(run(make_typed(hook=hook)), "hook") == selfcheck.FAIL


def test_only_whitespace_differences_are_tolerated_in_the_hook_and_cta():
    typed = scene(make_typed(), 0, spoken_line="  " + HOOK.replace(" ", "  ") + " ")
    assert status(run(typed), "hook") == selfcheck.PASS


@pytest.mark.parametrize("cta", [CTA + "!", CTA.replace("Save", "Please save"), CTA.lower()])
def test_the_cta_must_match_exactly(cta):
    assert status(run(scene(make_typed(), 4, spoken_line=cta)), "cta") == selfcheck.FAIL
    assert status(run(make_typed(cta=cta)), "cta") == selfcheck.FAIL


def test_the_cta_may_appear_only_once_in_the_package():
    typed = make_typed(caption=make_typed()["caption"] + " " + CTA)
    assert status(run(typed), "cta_count") == selfcheck.FAIL
    typed = scene(make_typed(), 4, on_screen_text=CTA)
    assert status(run(typed), "cta_count") == selfcheck.FAIL


@pytest.mark.parametrize("phrase", ["Book an appointment today.", "Call us now.", "Visit our showroom.", "Link in bio.", "Click to learn more.", "DM us your questions."])
def test_another_call_to_action_fails(phrase):
    typed = make_typed(caption=make_typed()["caption"] + " " + phrase)
    assert status(run(typed), "cta_count") == selfcheck.FAIL


def test_the_disclaimer_is_not_mistaken_for_a_cta():
    assert status(run(), "cta_count") == selfcheck.PASS


# --- claims -----------------------------------------------------------------------------------------------

def test_claims_used_lists_only_cited_claims_with_the_approved_statement():
    typed = make_typed()
    for s in typed["scenes"]:
        s["claim_ids"] = [i for i in s["claim_ids"] if i != "C21"]
    typed["caption_claim_ids"] = []
    used = selfcheck.claims_used(make_brief(), typed)
    assert [u["id"] for u in used] == ["C04"] and used[0]["statement"].startswith("A spec sheet is one piece")
    assert used[0]["used_in"] == ["scene 2", "scene 3", "scene 4"]


def test_both_supplied_claims_are_listed_when_both_are_used():
    assert {u["id"] for u in selfcheck.claims_used(make_brief(), make_typed())} == {"C04", "C21"}


def test_an_unapproved_claim_id_fails():
    typed = scene(make_typed(), 2, claim_ids=["C21", "C99"])
    check = next(c for c in run(typed) if c["id"] == "claim_mapping")
    assert check["status"] == selfcheck.FAIL and "C99" in check["detail"]
    assert status(run(make_typed(caption_claim_ids=["C77"])), "claim_mapping") == selfcheck.FAIL


def test_claim_ids_are_matched_case_insensitively_but_reported_as_approved():
    typed = scene(make_typed(), 2, claim_ids=["c21", "c04"])
    assert status(run(typed), "claim_mapping") == selfcheck.PASS
    assert "C21" in [u["id"] for u in selfcheck.claims_used(make_brief(), typed)]


def test_an_explanatory_scene_without_a_claim_needs_review_and_no_claims_fails():
    typed = scene(make_typed(), 3, claim_ids=[])
    assert status(run(typed), "claim_mapping") == selfcheck.REVIEW
    typed = make_typed(caption_claim_ids=[])
    for s in typed["scenes"]:
        s["claim_ids"] = []
    assert status(run(typed), "claim_mapping") == selfcheck.FAIL


@pytest.mark.parametrize("line", [
    "About 30% of homes with this setup lose power.",
    "A rating above 25 means the battery is oversized.",
    "This battery will maximize your savings.",
    "Our company uses a special method nobody else has.",
])
def test_unsupported_numbers_outcomes_and_company_claims_fail(line):
    typed = scene(make_typed(), 3, spoken_line=make_typed()["scenes"][3]["spoken_line"] + " " + line)
    assert status(run(typed), "claim_integrity") == selfcheck.FAIL


def test_a_number_from_an_approved_claim_is_allowed():
    brief = make_brief(approved_claims=[{"id": "C21", "statement": "Installers may suggest a battery after 3 months of outages."}, {"id": "C04", "statement": "A result is one piece of information."}])
    typed = scene(make_typed(), 3, spoken_line=make_typed()["scenes"][3]["spoken_line"] + " Installers often wait 3 months.")
    assert status(selfcheck.deterministic_checks(brief, typed), "claim_integrity") == selfcheck.PASS


# --- tone, brand, hashtags ---------------------------------------------------------------------------------

@pytest.mark.parametrize("line", ["Are you worried about your power bill?", "Don't ignore these warning signs!", "This is crucial.", "You must buy now.", "It is the best battery.", "Results are guaranteed.", "Act now, it is urgent."])
def test_fear_and_hype_wording_fails(line):
    typed = scene(make_typed(), 1, spoken_line=make_typed()["scenes"][1]["spoken_line"] + " " + line)
    assert status(run(typed), "tone") == selfcheck.FAIL


def test_should_needs_review_and_normal_words_do_not_trip_tone():
    typed = scene(make_typed(), 1, spoken_line=make_typed()["scenes"][1]["spoken_line"] + " Couples should ask.")
    assert status(run(typed), "tone") == selfcheck.REVIEW
    typed = scene(make_typed(), 1, spoken_line=make_typed()["scenes"][1]["spoken_line"] + " The mustard colour is unrelated, and bestow means give.")
    assert status(run(typed), "tone") == selfcheck.PASS


def test_approved_hook_wording_is_exempt_from_the_tone_check_only():
    brief = make_brief(approved_hook="Do not ignore this crucial question")
    typed = make_typed(hook=brief.approved_hook)
    scene(typed, 0, spoken_line=brief.approved_hook)
    assert status(selfcheck.deterministic_checks(brief, typed), "tone") == selfcheck.PASS


BRAND_CASES = ["free consultation", "Free Consultation", "FREE-CONSULTATION", "a 20% offer", "20% off", "Discounts", "No cost EMI", "EMI", "a callback", "Most Trusted", "No.1", "No. 1", "number one", "#1",
               "our success rate", "5000 families", "Acme Pro", "acme-pro", "ACME   PRO", "free trial", "free quote"]


@pytest.mark.parametrize("term", BRAND_CASES)
def test_every_restricted_term_is_detected_in_every_creative_field(term):
    base = make_typed()
    for build in (
        lambda t, x: scene(t, 1, spoken_line=f"{t['scenes'][1]['spoken_line']} {x}."),
        lambda t, x: scene(t, 1, visual=f"{t['scenes'][1]['visual']} showing {x}"),
        lambda t, x: scene(t, 1, on_screen_text=x),
        lambda t, x: scene(t, 1, subtitle=x),
        lambda t, x: t.update(caption=f"{t['caption']} {x}") or t,
        lambda t, x: t.update(title=f"{x} guide") or t,
    ):
        typed = build(copy.deepcopy(base), term)
        assert status(run(typed), "brand_restrictions") == selfcheck.FAIL, (term, build)


def test_hashtags_are_checked_for_restricted_terms_too():
    typed = make_typed()
    brief = make_brief(approved_hashtags=["#Acme_Pro", "#Energy"])
    typed["hashtags"] = ["#Acme_Pro", "#Energy"]
    assert status(selfcheck.deterministic_checks(brief, typed), "brand_restrictions") == selfcheck.FAIL


@pytest.mark.parametrize("text", ["acme professional", "acme prose", "demi", "acme and pro in separate sentences", "dismiss", "no.15", "numbers one at a time"])
def test_unrelated_words_do_not_match_restricted_terms(text):
    typed = scene(make_typed(), 1, on_screen_text=text)
    assert status(run(typed), "brand_restrictions") == selfcheck.PASS


def test_brand_restrictions_from_the_brief_are_enforced():
    brief = make_brief(brand_restrictions=["Backup package"])
    typed = scene(make_typed(), 1, on_screen_text="Our Backup  package")
    assert status(selfcheck.deterministic_checks(brief, typed), "brand_restrictions") == selfcheck.FAIL


def test_reviewer_notes_may_mention_a_restricted_term_without_failing_the_creative_check():
    typed = make_typed(reviewer_notes=["Brief mentions Acme Pro; left out."])
    assert status(run(typed), "brand_restrictions") == selfcheck.PASS


def test_hashtags_must_be_exactly_the_approved_list():
    assert status(run(make_typed(hashtags=make_typed()["hashtags"][:4])), "hashtags") == selfcheck.FAIL
    assert status(run(make_typed(hashtags=make_typed()["hashtags"] + ["#Extra"])), "hashtags") == selfcheck.FAIL
    assert status(run(make_typed(hashtags=[h.lower() for h in make_typed()["hashtags"]])), "hashtags") == selfcheck.PASS
    assert status(run(make_typed(hashtags=make_typed()["hashtags"] + [make_typed()["hashtags"][0]])), "hashtags") == selfcheck.FAIL


def test_without_approved_hashtags_none_may_be_written():
    brief = make_brief(approved_hashtags=[])
    assert status(selfcheck.deterministic_checks(brief, make_typed()), "hashtags") == selfcheck.FAIL
    assert status(selfcheck.deterministic_checks(brief, make_typed(hashtags=[])), "hashtags") == selfcheck.NA


# --- writing, visuals, schema ----------------------------------------------------------------------------------

def test_repeated_phrases_and_scenes_and_template_wording_fail():
    typed = scene(make_typed(), 3, spoken_line="Installers may suggest a backup battery for homes with frequent outages, after talking with the customer. The conversation is where it becomes useful for everyone concerned.")
    assert status(run(typed), "repetition") == selfcheck.FAIL
    typed = scene(make_typed(), 1, spoken_line=make_typed()["scenes"][1]["spoken_line"] + " Remember, the key is a comprehensive assessment of your unique situation.")
    assert status(run(typed), "repetition") == selfcheck.FAIL


def test_ordinary_repeated_grammar_words_are_not_repetition():
    typed = scene(make_typed(), 3, spoken_line="So the result is the start, the talk is the next step, and the plan is the third. The conversation is where it becomes useful. Questions are welcome, and nobody has to decide alone.")
    assert status(run(typed), "repetition") == selfcheck.PASS


@pytest.mark.parametrize("visual", ["Presenter explaining on a screen.", "Presenter holding a chart.", "Show a relevant animation.", "Display product information.", "Presenter talks"])
def test_vague_visuals_fail(visual):
    assert status(run(scene(make_typed(), 1, visual=visual)), "visual_specificity") == selfcheck.FAIL


def test_a_shot_may_not_repeat_more_than_twice_unless_the_brief_allows_it():
    typed = make_typed()
    same = "Alex sits at the desk and speaks to the camera with the folded spec sheet in her hand."
    for i in (0, 1, 2):
        scene(typed, i, visual=same)
    assert status(run(typed), "shot_diversity") == selfcheck.FAIL
    assert status(selfcheck.deterministic_checks(make_brief(continuous_talking_head=True), typed), "shot_diversity") == selfcheck.NA
    scene(typed, 2, visual="A two-column text card slides in beside the presenter while she gestures to the left side.")
    assert status(run(typed), "shot_diversity") == selfcheck.PASS


def test_on_screen_text_must_echo_the_speech_and_stay_short():
    assert status(run(scene(make_typed(), 1, on_screen_text="Completely unrelated banner words")), "on_screen") == selfcheck.REVIEW
    assert status(run(scene(make_typed(), 1, on_screen_text=" ".join(["word"] * 20))), "on_screen") == selfcheck.FAIL


def test_the_schema_check_catches_missing_and_mistyped_fields():
    typed = make_typed()
    del typed["scenes"][1]["visual"]
    typed["hashtags"] = "not a list"
    typed["scenes"][2]["claim_ids"] = "C21"
    check = next(c for c in run(typed) if c["id"] == "output_schema")
    assert check["status"] == selfcheck.FAIL and "visual" in check["detail"]
    assert status(run({}), "output_schema") == selfcheck.FAIL


def test_the_disclaimer_must_be_in_the_caption_word_for_word():
    assert status(run(make_typed(caption="A spec sheet is not the whole story.")), "disclaimer") == selfcheck.FAIL
    assert status(run(make_typed(caption=make_typed()["caption"].replace("please", "kindly"))), "disclaimer") == selfcheck.FAIL
    assert status(selfcheck.deterministic_checks(make_brief(required_disclaimer=""), make_typed()), "disclaimer") == selfcheck.NA


@pytest.mark.parametrize("text", ["See https://example.com/study", "Visit www.example.org", "According to a study, it helps.", "Studies show a link.", "(Smith, 2020)", "Reference C21 says so"])
def test_invented_sources_and_leaked_claim_ids_fail(text):
    typed = scene(make_typed(), 3, on_screen_text=text)
    assert status(run(typed), "source_integrity") == selfcheck.FAIL


@pytest.mark.parametrize("text", ["Reviewed by our experts", "Legally approved", "Ready to publish", "Compliance-approved advice", "Certified by the manager"])
def test_content_may_not_claim_to_be_reviewed_or_approved(text):
    typed = make_typed(caption=make_typed()["caption"] + " " + text)
    assert status(run(typed), "review_state") == selfcheck.FAIL


def test_required_title_and_subtitles_are_enforced():
    assert status(run(brief=make_brief(required_title="Exact Title")), "brief_compliance") == selfcheck.FAIL
    typed = make_typed()
    typed["scenes"][2]["subtitle"] = ""
    assert status(run(typed), "brief_compliance") == selfcheck.FAIL
    assert status(run(brief=make_brief(caption_requirements="Start with the hook")), "brief_compliance") == selfcheck.REVIEW


# --- the report ------------------------------------------------------------------------------------------------------

def test_without_validation_the_report_is_never_a_clean_pass():
    report = selfcheck.build_report(make_brief(), make_typed())
    assert report["overall"] == selfcheck.REVIEW and report["publication_authorised"] is False
    assert {c["id"]: c["status"] for c in report["checks"]}["validators"] == selfcheck.UNVERIFIED
    assert len(report["checks"]) == 20 and "not brand approval" in report["note"]


def test_a_clean_pass_needs_the_brand_validator_to_pass():
    ok = {"status": "PASS"}
    assert selfcheck.build_report(make_brief(), make_typed(), ok)["overall"] == selfcheck.PASS
    for brand in ({"status": "REVIEW_REQUIRED"}, {"status": "FAIL"}, {"status": "PASS", "validation_error": True}, {"status": "NOT_RUN"}, None):
        assert selfcheck.build_report(make_brief(), make_typed(), brand)["overall"] != selfcheck.PASS


def test_a_validator_pass_cannot_hide_a_code_failure():
    typed = make_typed(hashtags=["#Made", "#Up"])
    assert selfcheck.build_report(make_brief(), typed, {"status": "PASS"})["overall"] == selfcheck.FAIL


def test_the_report_contains_the_four_column_table_and_claims():
    report = selfcheck.build_report(make_brief(), make_typed())
    assert list(report["script_table"][0]) == ["time", "visual", "spoken line", "on-screen text"]
    assert len(report["script_table"]) == 5 and {c["id"] for c in report["claims_used"]} == {"C21", "C04"}
    assert report["word_count"]["minimum"] == 114


def test_failures_lists_only_failed_checks():
    typed = make_typed(hashtags=["#X"])
    assert [f.split(":")[0] for f in selfcheck.failures(run(typed))] == ["Approved hashtags"]
