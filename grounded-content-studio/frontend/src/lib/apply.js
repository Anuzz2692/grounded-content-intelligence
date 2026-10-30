// Applying a reviewer suggestion means finding the quoted "current" text inside the draft and
// swapping it for the suggested text. Models quote loosely, so matching tolerates case and
// whitespace differences, and never touches reviewer_notes (those are not part of the content).

const TEXT_FIELDS = ["title", "summary", "introduction", "conclusion", "suggested_cta"];
// A draft cannot be left with one of these empty.
const REQUIRED = new Set(["title", "summary", "introduction", "conclusion"]);

function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function slots(content) {
  const list = TEXT_FIELDS.map((field) => ({ field, required: REQUIRED.has(field) }));
  content.sections.forEach((_, index) => {
    list.push({ index, field: "heading", required: true }, { index, field: "body", required: true });
  });
  return list;
}

const read = (content, slot) => (slot.index === undefined ? content[slot.field] : content.sections[slot.index][slot.field]) || "";

function write(content, slot, value) {
  if (slot.index === undefined) return { ...content, [slot.field]: value === "" && slot.field === "suggested_cta" ? null : value };
  return { ...content, sections: content.sections.map((s, i) => (i === slot.index ? { ...s, [slot.field]: value } : s)) };
}

function matchIn(haystack, needle) {
  if (!haystack || !needle) return null;
  const at = haystack.indexOf(needle);
  if (at >= 0) return { start: at, end: at + needle.length };
  const pattern = needle.split(/\s+/).filter(Boolean).map(escapeRegExp).join("\\s+");
  const m = pattern ? new RegExp(pattern, "i").exec(haystack) : null;
  return m ? { start: m.index, end: m.index + m[0].length } : null;
}

// Models often wrap the quoted text in quotation marks.
const clean = (text) => (text || "").trim().replace(/^["'“‘]+|["'”’]+$/g, "").trim();

export function findText(content, text) {
  const needle = clean(text);
  if (needle.length < 3) return null;
  for (const slot of slots(content)) {
    const m = matchIn(read(content, slot), needle);
    if (m) return { slot, ...m };
  }
  return null;
}

/** Remove a span and tidy what is left: double spaces, a space before punctuation, empty lines. */
function tidy(text) {
  return text
    .replace(/[ \t]{2,}/g, " ")
    .replace(/ +([.,;:!?])/g, "$1")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/**
 * Replace the first place `original` appears. Returns { content, changed, reason }.
 * An empty `replacement` removes the text.
 */
export function replaceText(content, original, replacement) {
  const hit = findText(content, original);
  if (!hit) return { content, changed: false, reason: "not-found" };

  const before = read(content, hit.slot);
  let after = before.slice(0, hit.start) + (replacement || "") + before.slice(hit.end);
  if (!replacement) after = tidy(after);
  if (after === before) return { content, changed: false, reason: "no-change" };
  if (!after && hit.slot.required) return { content, changed: false, reason: "would-empty" };
  return { content: write(content, hit.slot, after), changed: true };
}

/** "pending": can be applied. "applied": the suggestion is already in the draft. "missing": neither is there. */
export function correctionStatus(content, correction) {
  const suggested = clean(correction.suggested_text);
  if (suggested && findText(content, suggested)) return "applied";
  if (findText(content, correction.original_text)) return "pending";
  return "missing";
}

export function applyCorrection(content, correction) {
  return replaceText(content, correction.original_text, (correction.suggested_text || "").trim());
}

export function undoCorrection(content, correction) {
  if (!(correction.suggested_text || "").trim()) return { content, changed: false, reason: "cannot-undo-removal" };
  return replaceText(content, correction.suggested_text, correction.original_text.trim());
}

/** Apply every pending correction in order. Returns the new content and how many were applied. */
export function applyAll(content, corrections) {
  let current = content;
  let applied = 0;
  for (const correction of corrections) {
    if (correctionStatus(current, correction) !== "pending") continue;
    const result = applyCorrection(current, correction);
    if (result.changed) {
      current = result.content;
      applied += 1;
    }
  }
  return { content: current, applied };
}
