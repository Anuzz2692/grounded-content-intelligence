import { describe, expect, it } from "vitest";
import { DEFAULT_PROFILE, capitalise, profileFromHealth } from "../src/lib/profile.js";

describe("profileFromHealth", () => {
  it("is neutral until the server answers or when it is offline", () => {
    expect(profileFromHealth(null)).toEqual(DEFAULT_PROFILE);
    expect(profileFromHealth("offline")).toEqual(DEFAULT_PROFILE);
    expect(DEFAULT_PROFILE.name).not.toMatch(/example|acme/i);
  });

  it("uses the company the server reports and keeps defaults for missing fields", () => {
    const profile = profileFromHealth({ company: { name: "Acme Corp", examples: ["How do refunds work?"] } });
    expect(profile.name).toBe("Acme Corp");
    expect(profile.examples).toEqual(["How do refunds work?"]);
    expect(profile.brand_check_label).toBe(DEFAULT_PROFILE.brand_check_label);
  });

  it("copes with an older server that has no company", () => expect(profileFromHealth({ status: "ok" })).toEqual(DEFAULT_PROFILE));
});

describe("capitalise", () => {
  it("capitalises the first letter only", () => expect(capitalise("brand")).toBe("Brand"));
  it("leaves empty text alone", () => expect(capitalise("")).toBe(""));
});
