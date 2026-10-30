import { buildBrief } from "../lib/brief.js";

const TEXT = [
  ["slot_id", "Calendar slot", "NOV-03"], ["platform", "Platform", "Instagram Reel"], ["presenter", "Presenter", "Alex Rivera"],
  ["spoken_language", "Spoken language", "English"], ["subtitle_language", "Subtitle language", "Hindi"],
];

export default function BriefForm({ brief, setBrief, disabled }) {
  const set = (patch) => setBrief((b) => ({ ...b, ...patch }));
  const { problems } = buildBrief(brief);
  const area = (key, label, rows, placeholder, hint) => (
    <label className="field">
      <span className="field-label">{label}</span>
      <textarea rows={rows} value={brief[key]} onChange={(e) => set({ [key]: e.target.value })} placeholder={placeholder} disabled={disabled} />
      {hint && <span className="muted small">{hint}</span>}
    </label>
  );
  return (
    <fieldset className="brief" disabled={disabled}>
      <legend>Calendar brief</legend>
      <p className="muted small">The brief is binding. The hook and CTA are used word for word, and factual statements may only come from the claims below.</p>
      <label className="field">
        <span className="field-label">Topic</span>
        <input value={brief.topic} onChange={(e) => set({ topic: e.target.value })} maxLength={300} />
      </label>
      <label className="field">
        <span className="field-label">Duration in seconds *</span>
        <input type="number" min="10" max="300" value={brief.duration_seconds} onChange={(e) => set({ duration_seconds: e.target.value })} placeholder="60" />
      </label>
      {TEXT.map(([key, label, ph]) => (
        <label className="field" key={key}>
          <span className="field-label">{label}</span>
          <input value={brief[key]} onChange={(e) => set({ [key]: e.target.value })} placeholder={ph} maxLength={120} />
        </label>
      ))}
      {area("approved_hook", "Approved hook *", 2, "", "Copied exactly, including punctuation.")}
      {area("approved_cta", "Approved CTA *", 2, "", "Used exactly once.")}
      {area("claims", "Approved claims *", 5, "C21: A statement your team has approved.\nC04: ...", "One per line as ID: statement. Only these may be used.")}
      {area("approved_hashtags", "Approved hashtags", 2, "#YourTag #AnotherTag", "Used exactly as listed, no others.")}
      {area("required_disclaimer", "Required disclaimer", 2, "")}
      {area("required_title", "Required title", 1, "", "Leave empty to let the AI write one.")}
      {area("caption_requirements", "Caption requirements", 2, "")}
      {area("segments", "Segments", 5, "Hook: 4\nInsight: 10\nExplanation: 34\nTakeaway: 8\nCTA: 4", "Optional, one per line as Name: seconds. A 60 second video uses this structure when empty.")}
      {area("brand_restrictions", "Extra words to avoid", 2, "", "One per line.")}
      {area("extra_constraints", "Other constraints", 2, "", "One per line. A reviewer must confirm these.")}
      <label className="check">
        <input type="checkbox" checked={brief.continuous_talking_head} onChange={(e) => set({ continuous_talking_head: e.target.checked })} />
        <span>Continuous talking-head video (the same shot may repeat)</span>
      </label>
      {problems.length > 0 && (
        <ul className="brief-problems" role="status">
          {problems.map((p) => <li key={p}>{p}</li>)}
        </ul>
      )}
    </fieldset>
  );
}
