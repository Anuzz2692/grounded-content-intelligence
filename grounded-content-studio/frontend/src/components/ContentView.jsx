import { useLayoutEffect, useRef, useState } from "react";
import { download, slugify, toMarkdown, toPlainText, toProseText, wordCount } from "../lib/export.js";
import { Badge, CopyButton, Icon } from "./ui.jsx";
import { PUBLICATION, tone } from "../lib/labels.js";

// Metadata blocks people paste straight into a scheduling tool.
const COPYABLE = /^(screenplay|title and hook options|caption|tags|hashtags)$/i;

// What the opening and closing fields mean for each format (the API uses the same fields for all of them).
const FRAMING = {
  video_script: { intro: "Opening hook", outro: "Closing line", cta: "Call to action" },
  social_post: { intro: "Post copy", outro: "Closing line", cta: "Call to action" },
};

const SCENE = /^scene\s+\d+/i;
const LABEL = /^(visual|voice[- ]?over|on[- ]screen text)\s*:\s*(.*)$/i;

/** Plain paragraphs, except screenplay scenes, which get their VISUAL / VOICEOVER / TEXT lines laid out. */
function Body({ text }) {
  return text.split(/\n{2,}/).map((block, i) => {
    const lines = block.split("\n").map((l) => l.trim()).filter(Boolean);
    const structured = lines.some((l) => SCENE.test(l) || LABEL.test(l));
    if (!structured) return <p key={i} style={{ whiteSpace: "pre-line" }}>{block}</p>;
    return (
      <div key={i} className="scene">
        {lines.map((line, j) => {
          if (SCENE.test(line)) return <div key={j} className="scene-title">{line}</div>;
          const m = line.match(LABEL);
          if (!m) return <p key={j} className="scene-line">{line}</p>;
          const kind = m[1].toLowerCase().replace(/[- ]/g, "");
          return (
            <p key={j} className={`scene-line scene-${kind}`}>
              <span className="scene-label">{m[1].toUpperCase()}</span>
              {m[2]}
            </p>
          );
        })}
      </div>
    );
  });
}

function AutoText({ value, onChange, className = "", label }) {
  const ref = useRef(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${el.scrollHeight}px`;
    }
  }, [value]);
  return <textarea ref={ref} className={`inline-edit ${className}`} value={value} onChange={(e) => onChange(e.target.value)} rows={1} aria-label={label} />;
}

export default function ContentView({ content: liveContent, original, onChange, publicationStatus, validated, warnings = [], repaired = false, contentType = "article", originalDraft = null, humanized = false, humanizeLevel = "natural" }) {
  const [editing, setEditing] = useState(false);
  const [viewingOriginal, setViewingOriginal] = useState(false);
  // While comparing, show the draft from before the natural-writing pass (read-only).
  const showingDraft = viewingOriginal && Boolean(originalDraft);
  const content = showingDraft ? originalDraft : liveContent;
  const editingNow = editing && !showingDraft;
  const edited = JSON.stringify(liveContent) !== JSON.stringify(original);
  const pub = tone(PUBLICATION, publicationStatus);
  const framing = FRAMING[contentType] || {};

  const setField = (field, value) => onChange({ ...liveContent, [field]: value });
  const setSection = (i, field, value) =>
    onChange({ ...liveContent, sections: liveContent.sections.map((s, idx) => (idx === i ? { ...s, [field]: value } : s)) });

  const view = (text) => <Body text={text} />;

  return (
    <div className="content-view">
      <div className="content-toolbar">
        <div className="toolbar-left">
          <Badge tone={pub.tone}>{pub.label}</Badge>
          <span className="muted">{wordCount(content).toLocaleString()} words</span>
          {edited && <Badge tone="warn" title="The checks ran on the original text">Edited since checks</Badge>}
          {humanized && !showingDraft && <Badge tone="neutral" title={humanizeLevel === "light" ? "Stock filler phrases were removed. Nothing else was changed." : "The wording was smoothed by a second pass. Facts, numbers and structure are checked to be unchanged."}>{humanizeLevel === "light" ? "Light edit" : "Rewritten for natural flow"}</Badge>}
          {showingDraft && <Badge tone="warn">Original draft</Badge>}
          {repaired && warnings.length === 0 && <Badge tone="neutral" title="The first answer missed some counts or sections, so the AI was asked once to fix them">Fixed automatically</Badge>}
        </div>
        <div className="toolbar-right">
          <button type="button" className={editingNow ? "btn btn-secondary btn-sm" : "btn btn-ghost btn-sm"} onClick={() => setEditing((v) => !v)} aria-pressed={editingNow} disabled={showingDraft}>
            <Icon name="edit" size={15} /> {editingNow ? "Done editing" : "Edit"}
          </button>
          {humanized && originalDraft && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setViewingOriginal((v) => !v)} aria-pressed={showingDraft}>
              {showingDraft ? "Show edited version" : "Compare with original draft"}
            </button>
          )}
          {edited && !showingDraft && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => onChange(original)}>
              Reset
            </button>
          )}
          <CopyButton getText={() => toMarkdown(content)} label="Copy" />
          {(contentType === "social_post" || contentType === "video_script") && (
            <CopyButton getText={() => toProseText(content)} label="Copy text only" />
          )}
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => download(`${slugify(content.title)}.md`, toMarkdown(content))}>
            <Icon name="download" size={15} /> .md
          </button>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => download(`${slugify(content.title)}.txt`, toPlainText(content), "text/plain")}>
            <Icon name="download" size={15} /> .txt
          </button>
        </div>
      </div>

      <p className="draft-note">
        <Icon name="shield" size={15} />
        <span>
          {validated ? "Automated checks help a reviewer but do not approve content." : "Checks were skipped. This is an unreviewed draft."} Content must be approved by an authorised person before it is published.
        </span>
      </p>

      {showingDraft && (
        <div className="banner banner-neutral" role="status">
          <Icon name="clock" />
          <div className="banner-body">
            <strong>You are reading the draft from before the writing polish</strong>
            <p className="muted small">It is read-only. The checks ran on the edited version, and Copy and download use what you see here.</p>
          </div>
        </div>
      )}

      {warnings.length > 0 && !showingDraft && (
        <div className="banner banner-warn" role="status">
          <Icon name="alert" />
          <div className="banner-body">
            <strong>{repaired ? "Still misses some requirements after one automatic fix" : "This draft misses some format requirements"}</strong>
            <ul className="plain-list">
              {warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
            <p className="muted small">Edit it here, or generate again.</p>
          </div>
        </div>
      )}

      <article className="article">
        {editingNow ? <AutoText className="h1" value={content.title} onChange={(v) => setField("title", v)} label="Title" /> : <h1>{content.title}</h1>}
        {editingNow ? <AutoText className="lede" value={content.summary} onChange={(v) => setField("summary", v)} label="Summary" /> : <p className="lede">{content.summary}</p>}
        {framing.intro && <h2 className="framing">{framing.intro}</h2>}
        {editingNow ? <AutoText value={content.introduction} onChange={(v) => setField("introduction", v)} label={framing.intro || "Introduction"} /> : view(content.introduction)}

        {content.sections.map((s, i) => (
          <section key={i} className="article-section">
            {editingNow ? (
              <AutoText className="h2" value={s.heading} onChange={(v) => setSection(i, "heading", v)} label={`Section ${i + 1} heading`} />
            ) : (
              <div className="section-head">
                <h2>{s.heading}</h2>
                {COPYABLE.test(s.heading.trim()) && <CopyButton getText={() => s.body} label="Copy" />}
              </div>
            )}
            {editingNow ? <AutoText value={s.body} onChange={(v) => setSection(i, "body", v)} label={`Section ${i + 1} text`} /> : view(s.body)}
          </section>
        ))}

        <section className="article-section">
          <h2>{framing.outro || "Conclusion"}</h2>
          {editingNow ? <AutoText value={content.conclusion} onChange={(v) => setField("conclusion", v)} label="Conclusion" /> : view(content.conclusion)}
        </section>

        {(content.suggested_cta || editingNow) && (
          <aside className="cta">
            <span className="cta-label">{framing.cta ? "Call to action" : "Suggested call to action"}</span>
            {editingNow ? <AutoText value={content.suggested_cta || ""} onChange={(v) => setField("suggested_cta", v || null)} label="Call to action" /> : <p>{content.suggested_cta}</p>}
          </aside>
        )}
      </article>
    </div>
  );
}
