import { Card, Icon } from "./ui.jsx";

export default function SourcesView({ sources }) {
  if (!sources?.length) return <Card><p className="muted">No sources were used.</p></Card>;
  const max = Math.max(...sources.map((s) => s.relevance_score), 0.0001);
  return (
    <div className="sources">
      <p className="muted">These pages from the website were given to the AI. Bars show how closely each matched your request.</p>
      <ul>
        {sources.map((s) => {
          let path = s.url;
          try {
            const u = new URL(s.url);
            path = u.hostname + (u.pathname === "/" ? "" : u.pathname);
          } catch {
            /* show raw url */
          }
          return (
            <li key={s.url} className="card source">
              <div className="source-main">
                <a href={s.url} target="_blank" rel="noopener noreferrer">
                  {s.title}
                </a>
                <span className="muted small">
                  <Icon name="link" size={12} /> {path}
                </span>
              </div>
              <div className="meter" title={`Relevance ${s.relevance_score}`}>
                <span style={{ width: `${Math.max(4, (s.relevance_score / max) * 100)}%` }} />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
