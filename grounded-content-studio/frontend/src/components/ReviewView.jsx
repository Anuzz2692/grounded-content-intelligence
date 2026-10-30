import { useState } from "react";
import { applyAll, applyCorrection, correctionStatus, undoCorrection } from "../lib/apply.js";
import { Badge, Card, Icon, List } from "./ui.jsx";
import { PUBLICATION, SEVERITY, VALIDATION, tone } from "../lib/labels.js";
import { reasonText } from "../lib/api.js";
import { useProfile } from "../lib/profile.js";

const NEXT_STEP = {
  BLOCK: "Do not publish. Resolve the issues above first.",
  REQUEST_CORRECTIONS: "Send back for the corrections listed above.",
  REVIEW_CONTENT: "A reviewer can read the content and decide.",
  GATHER_EVIDENCE: "Gather more website sources or expert input first.",
};

function CheckedBy({ v }) {
  if (!v?.provider) return null;
  const fallback = v.provider === "ollama";
  return (
    <span className="muted small">
      Checked by {fallback ? (v.fallback_reason ? "the local fallback model" : "the local model") : "the main AI service"}
      {fallback && v.fallback_reason ? ` (${reasonText(v.fallback_reason)})` : ""}
      {fallback ? ". Treat its verdict with extra care." : "."}
    </span>
  );
}

const WHY_NOT = {
  "not-found": "Not found in the draft",
  "would-empty": "Removing this would leave a required part empty",
  "no-change": "No change",
};

function Corrections({ items, content, onChange, title = "Suggested changes" }) {
  const [note, setNote] = useState("");
  if (!items?.length) return null;
  const editable = Boolean(content && onChange);
  const rows = items.map((c) => ({ c, status: editable ? correctionStatus(content, c) : "missing" }));
  const pending = rows.filter((r) => r.status === "pending").length;

  const apply = (c) => {
    const out = applyCorrection(content, c);
    if (out.changed) {
      onChange(out.content);
      setNote("");
    } else setNote(WHY_NOT[out.reason] || "Could not apply this change");
  };
  const undo = (c) => {
    const out = undoCorrection(content, c);
    if (out.changed) {
      onChange(out.content);
      setNote("");
    } else setNote("Could not undo this change. Use Reset on the Content tab.");
  };

  return (
    <div className="corrections">
      <div className="corrections-head">
        <h4>{title}</h4>
        {editable && pending > 1 && (
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => onChange(applyAll(content, items).content)}>
            Apply all ({pending})
          </button>
        )}
      </div>
      {note && <p className="muted small" role="status">{note}</p>}
      {rows.map(({ c, status }, i) => (
        <div key={i} className={`correction correction-${status}`}>
          <div className="was">
            <span>Current</span>
            <p>{c.original_text}</p>
          </div>
          <div className="now">
            <span>Suggested</span>
            <p>{c.suggested_text ? c.suggested_text : <em>Remove this text</em>}</p>
          </div>
          {c.reason && <p className="muted small">{c.reason}</p>}
          {editable && (
            <div className="correction-actions">
              {status === "pending" && (
                <button type="button" className="btn btn-primary btn-sm" onClick={() => apply(c)} title="Replaces the text in your draft. Undo it here, or use Reset on the Content tab.">
                  <Icon name="check" size={15} /> {c.suggested_text ? "Apply this change" : "Remove this text"}
                </button>
              )}
              {status === "applied" && (
                <>
                  <Badge tone="good">Applied to your draft</Badge>
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => undo(c)}>
                    Undo
                  </button>
                </>
              )}
              {status === "missing" && <span className="muted small">{c.suggested_text ? "Not found in the draft (already changed?)" : "Not in the draft any more"}</span>}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function CodeChecks({ items }) {
  if (!items?.length) return null;
  return (
    <div className="code-checks">
      <h4>Automatic safety checks adjusted this result</h4>
      <List items={items} />
    </div>
  );
}

function Validator({ title, v, children, content, onChange }) {
  const st = tone(VALIDATION, v?.status);
  return (
    <Card title={title} aside={<Badge tone={st.tone}>{st.label}</Badge>}>
      {v?.status_overridden ? (
        <p>
          The checker reported "{tone(VALIDATION, v.model_status).label.toLowerCase()}", but the automatic safety checks raised this to "{st.label.toLowerCase()}".
        </p>
      ) : (
        v?.summary && <p>{v.summary}</p>
      )}
      <CheckedBy v={v} />
      {children}
      <CodeChecks items={v?.code_checks} />
      <Corrections items={v?.corrections} content={content} onChange={onChange} />
      {v?.limitations?.length > 0 && (
        <details className="more">
          <summary>Limits of this check</summary>
          <List items={v.limitations} />
        </details>
      )}
    </Card>
  );
}

export default function ReviewView({ result, content, onContentChange }) {
  const profile = useProfile();
  const brand = result.brand_validation || {};
  const hr = result.human_review || {};
  const pub = tone(PUBLICATION, result.publication_status);
  const skipped = brand.status === "NOT_RUN";

  const issues = Array.isArray(brand.issues) ? brand.issues : [];

  return (
    <div className="review">
      <div className={`banner banner-${pub.tone}`}>
        <Icon name="shield" />
        <div className="banner-body">
          <strong>{pub.label}</strong>
          <p>{pub.text}</p>
          <p className="muted small">Nothing here is approved for publication. Only an authorised human reviewer can approve content.</p>
        </div>
      </div>

      {content && JSON.stringify(content) !== JSON.stringify(result.content) && (
        <p className="notice" role="status">
          <Icon name="alert" size={16} />
          <span>You have changed the draft since these checks ran. The results below describe the original text, so generate again to re-check.</span>
        </p>
      )}

      {result.content?.reviewer_notes?.length > 0 && (
        <Card title="Notes from the writer">
          <p className="muted small">Written for you, not for {profile.audience}. These are not part of the content.</p>
          <List items={result.content.reviewer_notes} />
        </Card>
      )}

      {result.wording_fixes?.length > 0 && (
        <Card title="Wording to fix" aside={<Badge tone="warn">{result.wording_fixes.length} found</Badge>}>
          <p className="muted small">
            Sentences the website research does not support: invented statistics, promises, offers or superlatives. Each one has its own change.
          </p>
          <Corrections items={result.wording_fixes} content={content} onChange={onContentChange} title="Flagged sentences" />
        </Card>
      )}

      {skipped ? (
        <Card title="Checks skipped">
          <p>You generated this without the brand check. Turn the checks on and generate again to see a review.</p>
        </Card>
      ) : (
        <>
          <Validator title={profile.brand_check_label} v={brand} content={content} onChange={onContentChange}>
            {issues.length > 0 ? (
              <ul className="claims">
                {issues.map((it, i) => {
                  const sev = tone(SEVERITY, it.severity);
                  return (
                    <li key={i} className="claim">
                      <div className="claim-head">
                        <Badge tone={sev.tone}>{sev.label}</Badge>
                        <span className="muted small">{(it.category || "").replaceAll("_", " ").toLowerCase()}</span>
                      </div>
                      <p>{it.text}</p>
                      {it.evidence && <p className="muted small">{it.evidence}</p>}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="muted">No brand issues were reported.</p>
            )}
          </Validator>

          <Card title="Briefing for the reviewer">
            {hr.content_purpose && <p>{hr.content_purpose}</p>}
            {[
              ["Accuracy concerns", hr.accuracy_concerns],
              ["Brand concerns", hr.brand_concerns],
              ["Evidence gaps", hr.evidence_gaps],
              ["Conflicts between checks", hr.conflicts],
              ["Questions to answer before publishing", hr.questions_for_reviewer],
            ].map(([label, items]) =>
              items?.length ? (
                <div key={label} className="brief-block">
                  <h4>{label}</h4>
                  <List items={items} />
                </div>
              ) : null,
            )}
            {hr.recommended_next_action && (
              <p>
                <strong>Suggested next step:</strong> {NEXT_STEP[hr.recommended_next_action] || hr.recommended_next_action.replaceAll("_", " ").toLowerCase()}
              </p>
            )}
            <p className="muted small">Approval authority: {hr.approval_authority || "Authorised human reviewer only"}.</p>
          </Card>
        </>
      )}
    </div>
  );
}
