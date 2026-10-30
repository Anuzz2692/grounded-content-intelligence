import { CONTENT_TYPES, POLISH, TONES, lengthsFor } from "../lib/labels.js";
import { useProfile } from "../lib/profile.js";
import BriefForm from "./BriefForm.jsx";
import { buildBrief } from "../lib/brief.js";
import { Icon, Segmented, Toggle } from "./ui.jsx";

const MAX_QUERY = 2000;

export default function Composer({ form, setForm, onSubmit, onCancel, loading, cooldown }) {
  const profile = useProfile();
  const set = (patch) => setForm((f) => ({ ...f, ...patch }));
  const tooShort = form.query.trim().length < 3;
  const briefOn = form.content_type === "video_script" && form.use_brief;
  const briefProblems = briefOn ? buildBrief(form.brief).problems : [];
  const blocked = loading || tooShort || cooldown > 0 || briefProblems.length > 0;

  return (
    <form
      className="card composer"
      onSubmit={(e) => {
        e.preventDefault();
        if (!blocked) onSubmit();
      }}
    >
      <label className="field">
        <span className="field-label">What should we write about?</span>
        <textarea
          value={form.query}
          onChange={(e) => set({ query: e.target.value })}
          onKeyDown={(e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && !blocked) {
              e.preventDefault();
              onSubmit();
            }
          }}
          rows={5}
          maxLength={MAX_QUERY}
          placeholder={profile.placeholder}
          disabled={loading}
        />
        <span className="field-foot">
          <span className="muted">Ctrl/⌘ + Enter to generate</span>
          <span className="muted">
            {form.query.length}/{MAX_QUERY}
          </span>
        </span>
      </label>

      <div className="chips" aria-label="Example topics">
        {profile.examples.map((ex) => (
          <button key={ex} type="button" className="chip" onClick={() => set({ query: ex })} disabled={loading}>
            {ex}
          </button>
        ))}
      </div>

      <Segmented label="Format" name="content_type" options={CONTENT_TYPES} value={form.content_type} onChange={(v) => set({ content_type: v })} />
      <Segmented label="Length" name="length" options={lengthsFor(form.content_type)} value={form.length} onChange={(v) => set({ length: v })} />

      {form.content_type === "video_script" && (
        <Toggle
          checked={Boolean(form.use_brief)}
          onChange={(v) => set({ use_brief: v })}
          label="Use a calendar brief"
          description="Approved hook, CTA, claims and hashtags are binding. Nothing is invented to fill a gap."
        />
      )}
      {briefOn && <BriefForm brief={form.brief} setBrief={(fn) => setForm((f) => ({ ...f, brief: typeof fn === "function" ? fn(f.brief) : fn }))} disabled={loading} />}

      <label className="field">
        <span className="field-label">Tone</span>
        <input list="tone-options" value={form.tone} onChange={(e) => set({ tone: e.target.value })} minLength={2} maxLength={80} disabled={loading} />
        <datalist id="tone-options">
          {TONES.map((t) => (
            <option key={t} value={t} />
          ))}
        </datalist>
      </label>

      <Segmented label="Writing polish" name="polish" options={POLISH} value={form.polish} onChange={(v) => set({ polish: v })} />

      <Toggle
        checked={form.validate_content}
        onChange={(v) => set({ validate_content: v })}
        label="Run the brand check and claim scan"
        description={form.validate_content ? "Slower, but flags brand issues and unsupported claims for a human reviewer." : "Fast draft. It will be marked as unreviewed."}
      />

      <div className="composer-actions">
        {loading ? (
          <button type="button" className="btn btn-secondary btn-block" onClick={onCancel}>
            <Icon name="x" size={16} /> Cancel
          </button>
        ) : (
          <button type="submit" className="btn btn-primary btn-block" disabled={blocked}>
            <Icon name="sparkle" size={16} />
            {cooldown > 0 ? `Wait ${cooldown}s` : "Generate content"}
          </button>
        )}
      </div>
    </form>
  );
}
