// The calendar brief the form collects. Everything is sent as typed; nothing is filled in on the user's behalf.

export const EMPTY_BRIEF = {
  slot_id: "", topic: "", platform: "", duration_seconds: "", presenter: "", spoken_language: "", subtitle_language: "",
  approved_hook: "", approved_cta: "", claims: "", approved_hashtags: "", required_title: "", required_disclaimer: "",
  caption_requirements: "", segments: "", brand_restrictions: "", extra_constraints: "", continuous_talking_head: false,
};

const lines = (text) => String(text || "").split("\n").map((l) => l.trim()).filter(Boolean);

/** "C21: statement" (also "C21 - statement" or "C21 | statement"), one per line. */
export function parseClaims(text) {
  const claims = [];
  const bad = [];
  for (const line of lines(text)) {
    const m = line.match(/^([A-Za-z0-9._-]+)\s*[:|\-–]\s*(.{3,})$/);
    if (m) claims.push({ id: m[1], statement: m[2].trim() });
    else bad.push(line);
  }
  return { claims, bad };
}

/** "Hook: 4" per line. */
export function parseSegments(text) {
  const segments = [];
  const bad = [];
  for (const line of lines(text)) {
    const m = line.match(/^(.+?)\s*[:|=]\s*(\d{1,3})\s*s?$/);
    if (m) segments.push({ name: m[1].trim(), seconds: Number(m[2]) });
    else bad.push(line);
  }
  return { segments, bad };
}

export const parseHashtags = (text) => String(text || "").split(/[\s,]+/).filter(Boolean);

/** Turns the form into the API's brief. `problems` lists what must be fixed before sending. */
export function buildBrief(form) {
  const { claims, bad: badClaims } = parseClaims(form.claims);
  const { segments, bad: badSegments } = parseSegments(form.segments);
  const duration = Number(form.duration_seconds);
  const problems = [];
  if (!Number.isInteger(duration) || duration < 10 || duration > 300) problems.push("Duration in seconds (10 to 300)");
  if (!form.approved_hook.trim()) problems.push("Approved hook");
  if (!form.approved_cta.trim()) problems.push("Approved CTA");
  if (!claims.length) problems.push("At least one approved claim, as ID: statement");
  if (badClaims.length) problems.push(`Claim lines that are not ID: statement (${badClaims.length})`);
  if (badSegments.length) problems.push(`Segment lines that are not Name: seconds (${badSegments.length})`);

  const brief = {
    slot_id: form.slot_id.trim(), topic: form.topic.trim(), platform: form.platform.trim(), duration_seconds: duration || null,
    presenter: form.presenter.trim(), spoken_language: form.spoken_language.trim(), subtitle_language: form.subtitle_language.trim(),
    approved_hook: form.approved_hook.trim(), approved_cta: form.approved_cta.trim(), approved_claims: claims,
    approved_hashtags: parseHashtags(form.approved_hashtags), required_title: form.required_title.trim(),
    required_disclaimer: form.required_disclaimer.trim(), caption_requirements: form.caption_requirements.trim(),
    segments, brand_restrictions: lines(form.brand_restrictions), extra_constraints: lines(form.extra_constraints),
    continuous_talking_head: Boolean(form.continuous_talking_head),
  };
  return { brief, problems };
}

/** The validation and self-check results describe the text as generated. True once the text has been edited. */
export function isStale(original, current) {
  return Boolean(original) && Boolean(current) && JSON.stringify(original) !== JSON.stringify(current);
}

export const CHECK_STATUS = {
  PASS: { label: "Pass", tone: "good" },
  FAIL: { label: "Fail", tone: "danger" },
  REVIEW_REQUIRED: { label: "Needs review", tone: "warn" },
  UNVERIFIED: { label: "Not verified", tone: "warn" },
  NOT_APPLICABLE: { label: "Not applicable", tone: "neutral" },
};
