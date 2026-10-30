// Plain-language labels for the statuses the API returns. Tone drives the colour of badges.

export const PUBLICATION = {
  BLOCKED: {
    label: "Blocked",
    tone: "danger",
    text: "A required check failed or could not be completed. Do not publish. A human reviewer needs to resolve the issues below first.",
  },
  PENDING_REVIEW: {
    label: "Ready for human review",
    tone: "warn",
    text: "The automated checks did not fail, but nothing is approved. An authorised reviewer must read and approve this before it is published.",
  },
  NOT_READY: {
    label: "Not ready",
    tone: "neutral",
    text: "Checks were skipped or incomplete. Treat this as an unreviewed draft.",
  },
};

export const VALIDATION = {
  PASS: { label: "No issues found", tone: "good" },
  REVIEW_REQUIRED: { label: "Needs review", tone: "warn" },
  FAIL: { label: "Failed", tone: "danger" },
  NOT_RUN: { label: "Not run", tone: "neutral" },
};

export const SEVERITY = {
  LOW: { label: "Low", tone: "neutral" },
  MEDIUM: { label: "Medium", tone: "warn" },
  HIGH: { label: "High", tone: "danger" },
};

export const CONTENT_TYPES = [
  { value: "article", label: "Website page", hint: "Product, location or article" },
  { value: "blog", label: "Blog post", hint: "Conversational article" },
  { value: "faq", label: "FAQ", hint: "Common questions" },
  { value: "social_post", label: "Social post", hint: "Copy, caption, tags" },
  { value: "video_script", label: "Video script", hint: "Screenplay, titles, caption" },
  { value: "general", label: "General", hint: "Let the AI decide" },
];

// What "length" means depends on the format. These mirror LENGTH_GUIDANCE in the backend.
const LENGTH_HINTS = {
  website: { concise: "~400–600 words", standard: "~800–1,100 words", detailed: "1,400–1,800 + FAQs" },
  social: { concise: "Up to 40 words", standard: "40–80 words", detailed: "80–150 words" },
  video: { concise: "~30 seconds", standard: "~60 seconds", detailed: "~90–120 seconds" },
  faq: { concise: "3 questions", standard: "5 questions", detailed: "8 questions" },
  general: { concise: "~300–450 words", standard: "~700–900 words", detailed: "~1,200–1,600 words" },
};
const GROUP = { article: "website", blog: "website", social_post: "social", video_script: "video", faq: "faq", general: "general" };

export function lengthsFor(contentType) {
  const hints = LENGTH_HINTS[GROUP[contentType] || "general"];
  return [
    { value: "concise", label: "Concise", hint: hints.concise },
    { value: "standard", label: "Standard", hint: hints.standard },
    { value: "detailed", label: "Detailed", hint: hints.detailed },
  ];
}

export const POLISH = [
  { value: "off", label: "Off", hint: "First draft as written" },
  { value: "light", label: "Light", hint: "Instant: removes stock phrases" },
  { value: "natural", label: "Natural", hint: "AI rewrite, fact-checked" },
];

export const TONES = ["Empathetic and clear", "Warm and reassuring", "Professional and informative", "Friendly and conversational"];

export function tone(map, key) {
  return map[key] || { label: key || "Unknown", tone: "neutral" };
}
