import pytest

from app import agent
from app.config import get_settings
from app.llm import LLMResult
from app.research import Page

PAGES = [Page("T", "https://site.test/a", "x" * 300, 1.0)]
HASHTAGS = " ".join(f"#t{i}" for i in range(15))
TAGS = ", ".join(f"t{i}" for i in range(15))
CAPTION = " ".join(["word"] * 40)


def social(tags=TAGS, hashtags=HASHTAGS):
    return {"title": "t", "summary": "s", "introduction": "i", "conclusion": "c", "suggested_cta": None,
            "reviewer_notes": [], "sections": [{"heading": "Caption", "body": CAPTION},
                                               {"heading": "Tags", "body": tags},
                                               {"heading": "Hashtags", "body": hashtags}]}


BAD = social(tags="a, b, c", hashtags="#a #b")  # 2 warnings
BETTER = social(tags=TAGS, hashtags="#a #b")  # 1 warning
GOOD = social()


@pytest.fixture
def calls(monkeypatch):
    log = {"generate": 0, "repair": [], "replies": []}

    async def research(query):
        return PAGES, False

    async def generate(*a):
        log["generate"] += 1
        return LLMResult(BAD, "ollama", "m", fallback_reason="not_configured")

    async def repair(query, content_type, tone, length, pages, previous, problems, provider):
        log["repair"].append({"previous": previous, "problems": problems, "provider": provider})
        reply = log["replies"].pop(0)
        if isinstance(reply, Exception):
            raise reply
        return LLMResult(reply, provider, "m")

    monkeypatch.setattr(agent, "research_website", research)
    monkeypatch.setattr(agent, "generate_grounded_content", generate)
    monkeypatch.setattr(agent, "repair_content", repair)
    return log


async def run():
    return await agent.run_content_agent("q", "social_post", "warm", "standard")


async def test_misses_trigger_one_fix_that_is_kept_when_better(calls):
    calls["replies"] = [GOOD]
    out = await run()
    assert out.format_repaired and out.format_warnings == [] and out.result.data == GOOD
    assert len(calls["repair"]) == 1
    sent = calls["repair"][0]
    assert sent["previous"] == BAD and sent["provider"] == "ollama"
    assert "Expected 15 tags but found 3." in sent["problems"]
    assert out.result.fallback_reason == "not_configured"  # the original provider story is preserved


async def test_a_partial_improvement_is_kept_and_remaining_misses_reported(calls):
    calls["replies"] = [BETTER]
    out = await run()
    assert out.format_repaired and out.format_warnings == ["Expected 15 hashtags but found 2."]


@pytest.mark.parametrize("reply", [BAD, social(tags="a", hashtags="#a")])
async def test_a_fix_that_is_not_better_is_discarded(calls, reply):
    calls["replies"] = [reply]
    out = await run()
    assert not out.format_repaired and out.result.data == BAD and len(out.format_warnings) == 2


async def test_a_failing_fix_never_breaks_the_request(calls):
    calls["replies"] = [RuntimeError("model down")]
    out = await run()
    assert not out.format_repaired and out.result.data == BAD and out.format_warnings


async def test_only_one_fix_is_attempted(calls):
    calls["replies"] = [BETTER, GOOD]
    await run()
    assert len(calls["repair"]) == 1 and len(calls["replies"]) == 1


async def test_no_fix_when_output_is_already_fine(calls, monkeypatch):
    async def generate(*a):
        return LLMResult(GOOD, "anthropic", "m")

    monkeypatch.setattr(agent, "generate_grounded_content", generate)
    out = await run()
    assert calls["repair"] == [] and out.format_warnings == [] and not out.format_repaired


async def test_fix_can_be_switched_off(calls, monkeypatch):
    monkeypatch.setenv("FORMAT_REPAIR", "false")
    get_settings.cache_clear()
    out = await run()
    assert calls["repair"] == [] and len(out.format_warnings) == 2 and not out.format_repaired


async def test_invented_claims_also_trigger_the_one_fix(calls, monkeypatch):
    risky = social()
    risky["introduction"] = "Save money with 60-80% success rates. Book a free consultation."
    clean = social()

    async def generate(*a):
        return LLMResult(risky, "ollama", "m")

    monkeypatch.setattr(agent, "generate_grounded_content", generate)
    calls["replies"] = [clean]
    out = await run()

    problems = " ".join(calls["repair"][0]["problems"])
    assert "statistic" in problems and "free consultation" in problems
    assert out.format_repaired and out.format_warnings == []


# --- natural-writing pass ---------------------------------------------------------

import copy

import httpx


@pytest.fixture
def humanizing(calls, monkeypatch):
    """`calls` plus a recording humanize step. The first draft is already fine, so no fix pass runs."""
    monkeypatch.setenv("HUMANIZE_ENABLED", "true")
    get_settings.cache_clear()
    log = {"calls": [], "reply": None}

    async def generate(*a):
        return LLMResult(copy.deepcopy(GOOD), "anthropic", "claude")

    async def humanize(query, content_type, tone, length, pages, draft, provider, notes=""):
        log["calls"].append({"draft": copy.deepcopy(draft), "provider": provider, "notes": notes})
        replies = log["reply"] if isinstance(log["reply"], list) else [log["reply"]]
        reply = replies[min(len(log["calls"]) - 1, len(replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        return LLMResult(copy.deepcopy(reply), provider, "m")

    monkeypatch.setattr(agent, "generate_grounded_content", generate)
    monkeypatch.setattr(agent, "humanize_content", humanize)
    return log


def smoother(**caption_change):
    out = copy.deepcopy(GOOD)
    out["introduction"] = "A smoother opening."
    out["sections"][0]["body"] = " ".join(["words"] * 40)
    out["sections"][1]["body"] = "ignored, the model may not touch this"
    return out


async def test_a_good_rewrite_is_used_and_the_draft_is_kept_for_comparison(humanizing):
    humanizing["reply"] = smoother()
    out = await run()
    assert out.humanized and out.original_content == GOOD
    assert out.result.data["introduction"] == "A smoother opening."
    assert out.result.data["sections"][1]["body"] == TAGS  # tags are restored, not trusted to the model
    assert out.format_warnings == []


async def test_a_rewrite_that_adds_a_statistic_is_discarded_with_a_reason(humanizing):
    bad = smoother()
    bad["introduction"] = "Most people, about 70 in 100, succeed."
    humanizing["reply"] = bad
    out = await run()
    assert not out.humanized and out.original_content is None and out.result.data == GOOD
    assert "numbers" in out.humanize_note


async def test_a_failing_rewrite_never_breaks_the_request(humanizing):
    humanizing["reply"] = httpx.ConnectError("down")
    out = await run()
    assert not out.humanized and out.result.data == GOOD
    assert "failed (connection)" in out.humanize_note


async def test_the_rewrite_goes_to_the_provider_that_wrote_the_draft(humanizing, monkeypatch):
    async def generate(*a):
        return LLMResult(copy.deepcopy(GOOD), "ollama", "qwen", fallback_reason="not_configured")

    monkeypatch.setattr(agent, "generate_grounded_content", generate)
    humanizing["reply"] = smoother()
    out = await run()
    assert humanizing["calls"][0]["provider"] == "ollama"
    assert out.result.provider == "ollama" and out.result.fallback_reason == "not_configured"


async def test_format_is_fixed_before_the_rewrite_so_it_works_on_a_correct_draft(humanizing, calls, monkeypatch):
    async def generate(*a):
        return LLMResult(copy.deepcopy(BAD), "ollama", "m")

    monkeypatch.setattr(agent, "generate_grounded_content", generate)
    calls["replies"] = [GOOD]
    humanizing["reply"] = smoother()
    out = await run()
    assert humanizing["calls"][0]["draft"] == GOOD  # the rewrite saw the already-fixed draft
    assert out.humanized and out.format_repaired


async def test_it_can_be_switched_off_per_request_or_in_settings(humanizing, monkeypatch):
    humanizing["reply"] = smoother()
    out = await agent.run_content_agent("q", "social_post", "warm", "standard", humanize=False)
    assert humanizing["calls"] == [] and not out.humanized and out.humanize_note is None

    monkeypatch.setenv("HUMANIZE_ENABLED", "false")
    get_settings.cache_clear()
    await run()
    assert humanizing["calls"] == []


async def test_the_fix_pass_receives_the_strict_format_fields_when_there_are_some(calls, monkeypatch):
    typed = {"hook": "strict-format fields", "tags": ["a"]}

    async def generate(*a):
        return LLMResult(BAD, "ollama", "m", typed=typed)

    monkeypatch.setattr(agent, "generate_grounded_content", generate)
    calls["replies"] = [GOOD]
    await run()
    assert calls["repair"][0]["previous"] == typed


async def test_the_ai_rewrite_waits_when_a_whole_part_is_missing_but_the_free_cleanup_does_not(humanizing, calls, monkeypatch):
    broken = copy.deepcopy(BAD)
    broken["introduction"] = "Rest assured, it is important to note that questions help."
    broken["sections"] = [sec for sec in broken["sections"] if sec["heading"] != "Caption"]  # a whole part is missing

    async def generate(*a):
        return LLMResult(copy.deepcopy(broken), "ollama", "m")

    monkeypatch.setattr(agent, "generate_grounded_content", generate)
    calls["replies"] = [broken]  # the format fix does not help
    humanizing["reply"] = smoother()
    out = await run()
    assert humanizing["calls"] == []  # no AI rewrite of a draft that still misses its format
    assert out.humanized and out.result.data["introduction"] == "Questions help."
    assert "AI rewrite was skipped" in out.humanize_note and "Stock filler phrases removed" in out.humanize_note
    assert out.format_warnings  # still reported: the format is not fixed, only the filler


# --- levels, targeted notes, second pass and clean-up -----------------------------------------------

FILLER = "It's important to note that questions help. Rest assured, bring yours. In today's fast-paced world, time is short."


def stiff(**over):
    out = copy.deepcopy(GOOD)
    out["introduction"] = FILLER
    out.update(over)
    return out


@pytest.fixture
def stiff_draft(humanizing, monkeypatch):
    async def generate(*a):
        return LLMResult(stiff(), "anthropic", "claude")

    monkeypatch.setattr(agent, "generate_grounded_content", generate)
    return humanizing


async def polish(level="natural"):
    return await agent.run_content_agent("q", "social_post", "warm", "standard", humanize=True, humanize_level=level)


async def test_light_level_cleans_stock_filler_without_any_ai_call(stiff_draft):
    out = await polish("light")
    assert stiff_draft["calls"] == [] and out.humanized
    assert out.result.data["introduction"] == "Questions help. Bring yours. Time is short."
    assert out.original_content["introduction"] == FILLER
    assert out.naturalness["before"]["phrases"] == 3 and out.naturalness["after"]["phrases"] == 0
    assert out.humanize_level == "light" and "Stock filler phrases removed" in out.humanize_note


async def test_the_rewrite_is_told_what_exactly_to_fix(stiff_draft):
    stiff_draft["reply"] = stiff(introduction="Questions help, so bring yours along.")
    await polish()
    notes = stiff_draft["calls"][0]["notes"]
    assert "Stock phrases to rewrite or remove" in notes and "it's important to note that" in notes and "rest assured" in notes


async def test_a_good_rewrite_is_measured_before_and_after(stiff_draft):
    stiff_draft["reply"] = stiff(introduction="Questions help, so bring yours along.")
    out = await polish()
    assert out.humanized and out.humanize_level == "natural"
    assert out.naturalness["before"]["issues"] > out.naturalness["after"]["issues"] == 0
    assert "Rewritten for natural flow" in out.humanize_note


async def test_cleanup_still_runs_when_the_ai_rewrite_is_rejected(stiff_draft):
    bad = stiff(introduction="About 70 in 100 people benefit, so bring questions.")
    stiff_draft["reply"] = bad
    out = await polish()
    assert out.humanized and out.result.data["introduction"] == "Questions help. Bring yours. Time is short."
    assert "numbers" in out.humanize_note and "Stock filler phrases removed" in out.humanize_note


async def test_cleanup_still_runs_when_the_ai_rewrite_fails(stiff_draft):
    stiff_draft["reply"] = httpx.ConnectError("down")
    out = await polish()
    assert out.humanized and "failed (connection)" in out.humanize_note and "Stock filler" in out.humanize_note


async def test_a_rewrite_with_more_stock_phrasing_than_the_draft_is_rejected(humanizing, monkeypatch):
    async def generate(*a):
        return LLMResult(stiff(introduction="Questions help, so bring yours along."), "anthropic", "claude")

    monkeypatch.setattr(agent, "generate_grounded_content", generate)
    humanizing["reply"] = stiff(introduction="Rest assured, it's important to note that questions help.")
    out = await polish()
    assert not out.humanized and "more stock phrasing" in out.humanize_note


async def test_a_second_targeted_pass_runs_only_when_enough_remains(stiff_draft):
    # The first rewrite keeps three stock phrases (not removed by the free clean-up: "when it comes to").
    leftover = stiff(introduction="When it comes to visits, when it comes to forms, when it comes to costs, ask.")
    fixed = stiff(introduction="Ask about visits, forms and costs.")
    stiff_draft["reply"] = [leftover, fixed]
    out = await polish()
    assert len(stiff_draft["calls"]) == 2 and "second pass" in out.humanize_note
    assert "when it comes to" in stiff_draft["calls"][1]["notes"]
    assert out.result.data["introduction"] == "Ask about visits, forms and costs."


async def test_no_second_pass_when_little_remains_or_when_switched_off(stiff_draft, monkeypatch):
    stiff_draft["reply"] = [stiff(introduction="When it comes to visits, ask."), stiff(introduction="Never used.")]
    await polish()
    assert len(stiff_draft["calls"]) == 1

    stiff_draft["calls"].clear()
    monkeypatch.setenv("HUMANIZE_SECOND_PASS", "false")
    get_settings.cache_clear()
    stiff_draft["reply"] = [stiff(introduction="When it comes to a, when it comes to b, when it comes to c."), stiff(introduction="Never used.")]
    await polish()
    assert len(stiff_draft["calls"]) == 1


async def test_a_draft_that_already_reads_naturally_is_left_alone(humanizing):
    humanizing["reply"] = copy.deepcopy(GOOD)
    out = await polish()
    assert not out.humanized and out.naturalness is None and "already read naturally" in out.humanize_note


async def test_a_rewrite_that_cannot_help_but_changes_nothing_important_is_reported_honestly(humanizing):
    humanizing["reply"] = {**copy.deepcopy(GOOD), "introduction": "A calmer opening line."}
    out = await polish()
    assert out.humanized and out.naturalness["after"]["issues"] == 0


# --- unsupported claims do not block the polish; they are what it is for ---------------------------------

CLAIMS = "Our team tailors each plan. Book a free consultation today to learn more."


@pytest.fixture
def calls_log(calls):
    return calls


@pytest.fixture
def claims_draft(humanizing, calls_log, monkeypatch):
    """A draft with correct format but an invented offer in its introduction."""
    async def generate(*a):
        return LLMResult(stiff(introduction=CLAIMS), "anthropic", "claude")

    monkeypatch.setattr(agent, "generate_grounded_content", generate)
    humanizing["calls_log"] = calls_log
    calls_log["replies"] = [stiff(introduction=CLAIMS)]  # the format-fix pass gets nothing better
    return humanizing


async def test_an_unsupported_claim_does_not_stop_the_polish_and_is_passed_to_the_rewrite(claims_draft):
    claims_draft["reply"] = stiff(introduction="Our team tailors each plan. Ask about a consultation.")
    out = await polish()
    assert len(claims_draft["calls"]) == 1 and out.humanized
    notes = claims_draft["calls"][0]["notes"]
    assert "Unsupported claims. Remove them rather than softening them" in notes and "free consultation" in notes
    assert "free consultation" not in out.result.data["introduction"]


async def test_light_polish_removes_an_unsupported_free_offer_without_any_ai_call(claims_draft):
    out = await polish("light")
    assert claims_draft["calls"] == [] and out.humanized
    assert out.result.data["introduction"] == "Our team tailors each plan. Book a consultation to learn more."


async def test_a_free_offer_the_website_states_is_left_alone(claims_draft, monkeypatch):
    async def research(query):
        return [Page("T", "https://site.test/a", "We offer a free consultation to new customers.", 1.0)], False

    monkeypatch.setattr(agent, "research_website", research)
    out = await polish("light")
    assert "free consultation" in out.result.data["introduction"]


async def test_a_wrong_count_does_not_stop_the_rewrite_or_the_cleanup(humanizing, calls, monkeypatch):
    short = copy.deepcopy(BAD)  # three tags instead of fifteen: a soft problem
    short["introduction"] = "Book a free consultation today to learn more!"

    async def generate(*a):
        return LLMResult(copy.deepcopy(short), "ollama", "m")

    monkeypatch.setattr(agent, "generate_grounded_content", generate)
    calls["replies"] = [short]
    humanizing["reply"] = {**copy.deepcopy(short), "introduction": "Ask about a consultation to learn more."}
    out = await run()
    assert len(humanizing["calls"]) == 1 and out.humanized
    assert out.result.data["introduction"] == "Ask about a consultation to learn more."


async def test_a_rewrite_that_makes_a_soft_problem_worse_is_still_rejected(humanizing, calls, monkeypatch):
    short = copy.deepcopy(BAD)  # a good 40-word caption, but only three tags

    async def generate(*a):
        return LLMResult(copy.deepcopy(short), "ollama", "m")

    monkeypatch.setattr(agent, "generate_grounded_content", generate)
    calls["replies"] = [short]
    worse = copy.deepcopy(short)
    worse["introduction"] = "Better words here."
    worse["sections"][0]["body"] = "Tiny."  # breaks the 30-50 word caption rule: one more problem than before
    humanizing["reply"] = worse
    out = await run()
    assert not out.humanized and "required format" in out.humanize_note
    assert out.result.data["sections"][0]["body"] == short["sections"][0]["body"]