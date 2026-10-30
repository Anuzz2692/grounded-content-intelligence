import { describe, expect, it } from "vitest";
import { applyAll, applyCorrection, correctionStatus, findText, replaceText, undoCorrection } from "../src/lib/apply.js";

const base = () => ({
  title: "Understanding battery storage",
  summary: "A short guide.",
  introduction: "Starting with batteries can feel overwhelming.\n\nThis guide explains the basics.",
  sections: [
    { heading: "The steps", body: "We use load balancing to ensure the best efficiency rates. Battery storage is reliable." },
    { heading: "Next steps", body: "Ready to learn more? Book a free consultation with Example Co today!" },
  ],
  conclusion: "Ask your specialist.",
  suggested_cta: "Book a free consultation.",
  reviewer_notes: ["We use load balancing to ensure the best efficiency rates."],
});

const fix = {
  original_text: "Ready to learn more? Book a free consultation with Example Co today!",
  suggested_text: "Ready to learn more? Book a consultation to discuss your options.",
};

describe("replaceText", () => {
  it("replaces text inside a section body and leaves the rest alone", () => {
    const { content, changed } = applyCorrection(base(), fix);
    expect(changed).toBe(true);
    expect(content.sections[1].body).toBe(fix.suggested_text);
    expect(content.sections[0]).toEqual(base().sections[0]);
  });

  it("does not mutate the input", () => {
    const original = base();
    applyCorrection(original, fix);
    expect(original).toEqual(base());
  });

  it("matches despite different case, spacing and surrounding quotes", () => {
    const loose = { original_text: '"ready to  learn more?\nbook a free consultation with example co today!"', suggested_text: "Learn more." };
    expect(applyCorrection(base(), loose).content.sections[1].body).toBe("Learn more.");
  });

  it("finds text in the title, summary, introduction, conclusion and call to action too", () => {
    for (const [text, field] of [["Understanding battery storage", "title"], ["A short guide.", "summary"], ["feel overwhelming", "introduction"],
                                 ["Ask your specialist", "conclusion"], ["Book a free consultation.", "suggested_cta"]]) {
      expect(findText(base(), text).slot.field).toBe(field);
    }
  });

  it("only replaces the first occurrence", () => {
    const c = { ...base(), sections: [{ heading: "h", body: "Same line. Same line." }] };
    expect(replaceText(c, "Same line.", "Changed.").content.sections[0].body).toBe("Changed. Same line.");
  });

  it("never touches reviewer notes", () => {
    const notes = ["only here"];
    const c = { ...base(), reviewer_notes: notes };
    expect(findText(c, "only here")).toBeNull();
    expect(applyCorrection(c, { original_text: "We use load balancing to ensure the best efficiency rates.", suggested_text: "We use load balancing." }).content.reviewer_notes).toBe(notes);
  });

  it("reports text it cannot find, and ignores trivially short quotes", () => {
    expect(replaceText(base(), "not in the draft at all", "x").reason).toBe("not-found");
    expect(findText(base(), "IV")).toBeNull();
    expect(findText(base(), "")).toBeNull();
  });

  it("treats regex characters in the quoted text literally", () => {
    // The double space forces the tolerant (regex) match, where unescaped ( . [ ? would misbehave.
    const c = { ...base(), sections: [{ heading: "h", body: "Costs (approx.)  may vary [see details]?" }] };
    expect(replaceText(c, "Costs (approx.) may vary [see details]?", "Costs vary.").content.sections[0].body).toBe("Costs vary.");
  });
});

describe("removal", () => {
  it("removes the text and tidies the gap", () => {
    const out = replaceText(base(), " Battery storage is reliable.", "");
    expect(out.content.sections[0].body).toBe("We use load balancing to ensure the best efficiency rates.");
  });

  it("removes a whole sentence without leaving a double space or stray space before punctuation", () => {
    const c = { ...base(), sections: [{ heading: "h", body: "First sentence. Remove me. Last one." }] };
    expect(replaceText(c, "Remove me.", "").content.sections[0].body).toBe("First sentence. Last one.");
  });

  it("refuses to empty a required field but allows clearing the call to action", () => {
    expect(replaceText(base(), "Understanding battery storage", "").reason).toBe("would-empty");
    const out = replaceText(base(), "Book a free consultation.", "");
    expect(out.changed).toBe(true);
    expect(out.content.suggested_cta).toBeNull();
  });
});

describe("status, undo and apply all", () => {
  it("derives pending, applied and missing from the draft itself", () => {
    expect(correctionStatus(base(), fix)).toBe("pending");
    const applied = applyCorrection(base(), fix).content;
    expect(correctionStatus(applied, fix)).toBe("applied");
    expect(correctionStatus({ ...applied, sections: [] }, fix)).toBe("missing");
  });

  it("undo restores the original wording", () => {
    const applied = applyCorrection(base(), fix).content;
    expect(undoCorrection(applied, fix).content.sections[1].body).toBe(fix.original_text);
  });

  it("cannot undo a removal", () => {
    expect(undoCorrection(base(), { original_text: "Battery storage is reliable.", suggested_text: "" }).reason).toBe("cannot-undo-removal");
  });

  it("applies every pending correction and skips ones that are missing or already applied", () => {
    const list = [
      fix,
      { original_text: "Battery storage is reliable.", suggested_text: "Flow batteries are one option." },
      { original_text: "nothing like this", suggested_text: "x" },
    ];
    const first = applyAll(base(), list);
    expect(first.applied).toBe(2);
    expect(first.content.sections[0].body).toContain("one option");
    expect(applyAll(first.content, list).applied).toBe(0);
  });

  it("a suggestion that contains the original text does not loop", () => {
    const grow = { original_text: "Ask your specialist", suggested_text: "Ask your specialist about next steps" };
    const once = applyCorrection(base(), grow).content;
    expect(correctionStatus(once, grow)).toBe("applied");
    expect(applyAll(once, [grow]).applied).toBe(0);
  });
});
