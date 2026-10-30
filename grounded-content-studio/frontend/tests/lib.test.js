import { describe, expect, it } from "vitest";
import { describeHttpError, reasonText } from "../src/lib/api.js";
import { slugify, toMarkdown, toPlainText, toProseText, wordCount } from "../src/lib/export.js";

const content = {
  title: "Understanding battery backup",
  summary: "A short summary.",
  introduction: "Intro text.",
  sections: [{ heading: "What it is", body: "Body one." }],
  conclusion: "Wrap up.",
  suggested_cta: "Book a consultation.",
};

describe("describeHttpError", () => {
  const headers = (h) => ({ get: (k) => h[k] ?? null });

  it("tells people to add a key on 401", () => {
    const e = describeHttpError(401, { detail: "x" }, headers({}));
    expect(e.kind).toBe("auth");
    expect(e.message).toMatch(/API key/);
  });

  it("reads Retry-After on 429", () => {
    const e = describeHttpError(429, {}, headers({ "Retry-After": "42" }));
    expect(e.kind).toBe("rate_limit");
    expect(e.retryAfter).toBe(42);
    expect(e.message).toMatch(/42 seconds/);
  });

  it("maps 503, 502 and 422", () => {
    expect(describeHttpError(503, { detail: "No LLM provider" }, headers({})).kind).toBe("unavailable");
    expect(describeHttpError(502, { detail: "site down" }, headers({})).message).toBe("site down");
    const invalid = describeHttpError(422, { detail: [{ msg: "too short" }, { msg: "bad" }] }, headers({}));
    expect(invalid.message).toBe("too short; bad");
    const nested = describeHttpError(422, { detail: [{ loc: ["body", "brief", "approved_claims", 0, "id"], msg: "String should match pattern" }] }, headers({}));
    expect(nested.message).toBe("brief.approved_claims.0.id: String should match pattern");
  });
});

describe("reasonText", () => {
  it("explains known and http codes", () => {
    expect(reasonText("rate_limit")).toMatch(/rate limit/);
    expect(reasonText("model_not_found")).toMatch(/not installed/);
    expect(reasonText("http_529")).toBe("the provider returned HTTP 529");
    expect(reasonText(null)).toBe("");
  });
});

describe("export helpers", () => {
  it("builds markdown and plain text", () => {
    const md = toMarkdown(content);
    expect(md).toContain("# Understanding battery backup");
    expect(md).toContain("## What it is");
    expect(md).toContain("> Book a consultation.");
    expect(toPlainText(content)).toContain("WHAT IT IS");
  });

  it("omits the call to action when absent", () => {
    expect(toMarkdown({ ...content, suggested_cta: null })).not.toContain(">");
  });

  it("slugifies and counts words", () => {
    expect(slugify("  What is battery backup? ")).toBe("what-is-battery-backup");
    expect(slugify("")).toBe("content");
    expect(wordCount(content)).toBeGreaterThan(5);
  });
});

describe("per-format helpers", async () => {
  const { lengthsFor } = await import("../src/lib/labels.js");

  it("describes length differently for each format", () => {
    expect(lengthsFor("article")[2].hint).toMatch(/1,400/);
    expect(lengthsFor("video_script")[0].hint).toMatch(/30 seconds/);
    expect(lengthsFor("social_post")[0].hint).toMatch(/40 words/);
    expect(lengthsFor("faq").map((l) => l.hint)).toEqual(["3 questions", "5 questions", "8 questions"]);
    expect(lengthsFor("unknown")).toHaveLength(3);
  });

  it("keeps reviewer notes out of exported content", () => {
    const md = toMarkdown({ ...content, reviewer_notes: ["secret reviewer note"] });
    expect(md).not.toContain("secret reviewer note");
    expect(toPlainText({ ...content, reviewer_notes: ["secret reviewer note"] })).not.toContain("secret");
  });
});


describe("toProseText", () => {
  const social = {
    title: "Questions before a visit", summary: "A post about preparing.", introduction: "Write your questions down before the visit.",
    sections: [
      { heading: "Caption", body: "Bring a list so nothing is forgotten." },
      { heading: "Tags", body: "energy, questions, consultation" },
      { heading: "Hashtags", body: "#energy #questions" },
    ],
    conclusion: "Ask away.",
  };

  it("keeps the writing and drops labels, tags, hashtags, title and summary", () => {
    const text = toProseText(social);
    expect(text).toBe("Write your questions down before the visit.\n\nBring a list so nothing is forgotten.\n\nAsk away.\n");
    for (const left of ["Caption", "Tags", "#energy", "Questions before a visit", "A post about"]) expect(text).not.toContain(left);
  });

  it("uses only the spoken lines of a screenplay, and does not repeat the hook or closing line", () => {
    const video = {
      title: "t", summary: "s", introduction: "Nervous about your first visit?",
      sections: [
        { heading: "Screenplay", body: "Scene 1 (0:00-0:05)\nVISUAL: A reception.\nVOICEOVER: Nervous about your first visit?\nON-SCREEN TEXT: First visit?\n\nScene 2 (0:05-0:20)\nVISUAL: A notebook.\nVOICEOVER: Write your questions down.\nON-SCREEN TEXT: None" },
        { heading: "Title and Hook Options", body: "1. Title: A | Hook: B" },
        { heading: "Caption", body: "Heading to a first visit? Bring questions." },
        { heading: "Tags", body: "a, b" }, { heading: "Hashtags", body: "#a" },
      ],
      conclusion: "Write your questions down.",
    };
    const text = toProseText(video);
    expect(text).toBe("Nervous about your first visit? Write your questions down.\n\nHeading to a first visit? Bring questions.\n");
    for (const left of ["VISUAL", "Scene", "ON-SCREEN", "Hook", "#a"]) expect(text).not.toContain(left);
  });
});
