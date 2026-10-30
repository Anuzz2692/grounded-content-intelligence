import { useState } from "react";
import ContentView from "./ContentView.jsx";
import DetailsView from "./DetailsView.jsx";
import ReviewView from "./ReviewView.jsx";
import SourcesView from "./SourcesView.jsx";
import BriefView from "./BriefView.jsx";
import { isStale } from "../lib/brief.js";
import { PUBLICATION, tone } from "../lib/labels.js";

const wasValidated = (result) => result.brand_validation?.status !== "NOT_RUN";

export default function Result({ result, content, onContentChange }) {
  const [tab, setTab] = useState(result.brief_report ? "script" : "content");
  const stale = wasValidated(result) && isStale(result.content, content);
  const pub = tone(PUBLICATION, result.publication_status);
  const validated = result.brand_validation?.status !== "NOT_RUN";

  const tabs = [
    ...(result.brief_report ? [{ id: "script", label: "Script", dot: ({ PASS: "good", FAIL: "danger" })[result.brief_report.overall] || "warn" }] : []),
    { id: "content", label: "Content" },
    { id: "review", label: "Review", dot: pub.tone },
    { id: "sources", label: `Sources (${result.sources.length})` },
    { id: "details", label: "Details" },
  ];

  return (
    <div className="result">
      {stale && (
        <div className="banner banner-warn" role="alert">
          <div className="banner-body">
            <strong>You edited this text after it was checked</strong>
            <p>The checks, self-check and review status describe the original wording, not your edits. Generate again to re-check it. Nothing here is approved for publication.</p>
          </div>
        </div>
      )}
      <div className="tabs" role="tablist" aria-label="Result sections">
        {tabs.map((t) => (
          <button
            key={t.id}
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            tabIndex={tab === t.id ? 0 : -1}
            className={tab === t.id ? "tab active" : "tab"}
            onClick={() => setTab(t.id)}
            onKeyDown={(e) => {
              const i = tabs.findIndex((x) => x.id === tab);
              if (e.key === "ArrowRight") setTab(tabs[(i + 1) % tabs.length].id);
              if (e.key === "ArrowLeft") setTab(tabs[(i - 1 + tabs.length) % tabs.length].id);
            }}
          >
            {t.label}
            {t.dot && <span className={`tab-dot dot-${t.dot}`} aria-hidden="true" />}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} className="tabpanel">
        {tab === "script" && result.brief_report && <BriefView result={result} />}
        {tab === "content" && <ContentView content={content} original={result.content} onChange={onContentChange} publicationStatus={result.publication_status} validated={validated} warnings={result.metadata.format_warnings ?? []} repaired={Boolean(result.metadata.format_repaired)} contentType={result.metadata.content_type || "article"} originalDraft={result.original_content ?? null} humanized={Boolean(result.metadata.humanized)} humanizeLevel={result.metadata.humanize_level} />}
        {tab === "review" && <ReviewView result={result} content={content} onContentChange={onContentChange} />}
        {tab === "sources" && <SourcesView sources={result.sources} />}
        {tab === "details" && <DetailsView metadata={result.metadata} />}
      </div>
    </div>
  );
}
