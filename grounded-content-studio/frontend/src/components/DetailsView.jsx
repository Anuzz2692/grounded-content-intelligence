import { Badge, Card } from "./ui.jsx";
import { reasonText } from "../lib/api.js";

function Row({ label, children }) {
  return (
    <div className="kv">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

const seconds = (ms) => (ms == null ? "n/a" : `${(ms / 1000).toFixed(1)}s`);

export default function DetailsView({ metadata }) {
  const m = metadata;
  const checks = m.research_ms != null && m.generation_ms != null ? Math.max(0, m.latency_ms - m.research_ms - m.generation_ms) : null;
  const parts = [
    { label: "Reading website", ms: m.research_ms, cls: "t1" },
    { label: "Writing", ms: m.generation_ms, cls: "t2" },
    { label: "Checks", ms: checks, cls: "t3" },
  ].filter((p) => p.ms != null && p.ms > 0);
  const total = parts.reduce((a, p) => a + p.ms, 0) || 1;
  const fallback = m.provider === "ollama";

  return (
    <div className="details">
      {fallback && (
        <div className="banner banner-warn">
          <div className="banner-body">
            <strong>{m.fallback_reason ? "Written by the local fallback model" : "Written by a local model (Ollama)"}</strong>
            <p>
              {m.fallback_reason ? `The main AI service wasn't used: ${reasonText(m.fallback_reason)}. ` : ""}
              Local models are usually less careful than the main service, so review this draft closely.
            </p>
          </div>
        </div>
      )}
      <Card title="Time taken" aside={<strong>{seconds(m.latency_ms)}</strong>}>
        <div className="timeline" role="img" aria-label={parts.map((p) => `${p.label} ${seconds(p.ms)}`).join(", ")}>
          {parts.map((p) => (
            <span key={p.label} className={p.cls} style={{ flexGrow: p.ms / total }} />
          ))}
        </div>
        <ul className="legend">
          {parts.map((p) => (
            <li key={p.label}>
              <span className={`swatch ${p.cls}`} /> {p.label} <strong>{seconds(p.ms)}</strong>
            </li>
          ))}
        </ul>
      </Card>
      <Card title="How it was made">
        <dl className="kvs">
          <Row label="Written by">
            <Badge tone={fallback ? "warn" : "good"}>{fallback ? (m.fallback_reason ? "Local fallback" : "Local model") : "Main AI service"}</Badge> <span className="muted">{m.model}</span>
          </Row>
          <Row label="Website pages used">{m.pages_considered}</Row>
          <Row label="Format check">
            {m.format_warnings?.length ? `${m.format_warnings.length} issue${m.format_warnings.length > 1 ? "s" : ""} left` : "Passed"}
            {m.format_repaired ? " (corrected automatically, one extra pass)" : ""}
          </Row>
          {m.naturalness && (
            <Row label="Stock phrasing">
              {m.naturalness.before.issues} flagged, now {m.naturalness.after.issues}
              <span className="muted"> ({m.naturalness.before.phrases} stock phrases, {m.naturalness.before.repeated_openers} repeated openings and {m.naturalness.before.questions} questions in the first draft)</span>
            </Row>
          )}
          <Row label="Writing polish">
            {m.humanized ? (m.humanize_level === "light" ? "Light edit" : "Applied") : "Not applied"}
            {m.humanize_note ? <span className="muted"> ({m.humanize_note})</span> : null}
          </Row>
          <Row label="Website lookup">{m.cached_research ? "Reused a recent lookup (faster)" : "Read fresh from the website"}</Row>
        </dl>
      </Card>
    </div>
  );
}
