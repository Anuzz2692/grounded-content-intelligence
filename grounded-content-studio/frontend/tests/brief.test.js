import { describe, expect, it } from "vitest";
import { EMPTY_BRIEF, buildBrief, isStale, parseClaims, parseHashtags, parseSegments } from "../src/lib/brief.js";

const full = {
  ...EMPTY_BRIEF, duration_seconds: "60", approved_hook: "A spec sheet can look impressive and still not tell the whole story",
  approved_cta: "Save this and bring your questions to your next site visit",
  claims: "C21: Installers may suggest a backup battery for homes with frequent outages.\nC04 - A spec sheet is one piece of information.",
  approved_hashtags: "#One, #Two  Three", segments: "Hook: 4\nCTA: 4s",
};

describe("buildBrief", () => {
  it("accepts a complete brief and keeps the approved text exactly", () => {
    const { brief, problems } = buildBrief(full);
    expect(problems).toEqual([]);
    expect(brief.approved_hook).toBe(full.approved_hook);
    expect(brief.approved_claims.map((c) => c.id)).toEqual(["C21", "C04"]);
    expect(brief.duration_seconds).toBe(60);
    expect(brief.segments).toEqual([{ name: "Hook", seconds: 4 }, { name: "CTA", seconds: 4 }]);
  });

  it("never fills in missing mandatory fields", () => {
    const { brief, problems } = buildBrief(EMPTY_BRIEF);
    expect(problems).toHaveLength(4);
    expect(brief.approved_hook).toBe("");
    expect(brief.approved_cta).toBe("");
    expect(brief.approved_claims).toEqual([]);
    expect(brief.approved_hashtags).toEqual([]);
  });

  it("reports malformed claim and segment lines", () => {
    const { problems } = buildBrief({ ...full, claims: "no id here", segments: "oops" });
    expect(problems.join(" ")).toMatch(/Claim lines/);
    expect(problems.join(" ")).toMatch(/Segment lines/);
    expect(problems.join(" ")).toMatch(/approved claim/);
  });

  it("rejects an out-of-range duration", () => {
    expect(buildBrief({ ...full, duration_seconds: "5" }).problems[0]).toMatch(/Duration/);
    expect(buildBrief({ ...full, duration_seconds: "abc" }).problems[0]).toMatch(/Duration/);
  });
});

describe("parsers", () => {
  it("splits hashtags on spaces and commas", () => expect(parseHashtags("#a, #b  c")).toEqual(["#a", "#b", "c"]));
  it("parses claims with several separators", () => expect(parseClaims("C1: one two\nC2 | three four").claims).toHaveLength(2));
  it("parses segments", () => expect(parseSegments("Hook: 4").segments).toEqual([{ name: "Hook", seconds: 4 }]));
});

describe("isStale", () => {
  const a = { title: "t", sections: [{ heading: "h", body: "b" }] };
  it("is false for the same content and true after an edit", () => {
    expect(isStale(a, JSON.parse(JSON.stringify(a)))).toBe(false);
    expect(isStale(a, { ...a, title: "edited" })).toBe(true);
  });
  it("is false when there is nothing to compare", () => expect(isStale(null, a)).toBe(false));
});
