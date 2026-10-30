import { Icon } from "./ui.jsx";

function ago(ts) {
  const m = Math.round((Date.now() - ts) / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  return new Date(ts).toLocaleDateString();
}

export default function History({ items, activeId, onOpen, onDelete, onClear }) {
  if (!items.length) return null;
  return (
    <section className="card history" aria-label="Recent drafts">
      <header className="card-head">
        <h3>
          <Icon name="clock" size={16} /> Recent drafts
        </h3>
        <button type="button" className="btn btn-ghost btn-sm" onClick={onClear}>
          Clear all
        </button>
      </header>
      <ul>
        {items.map((it) => (
          <li key={it.id} className={it.id === activeId ? "active" : ""}>
            <button type="button" className="history-open" onClick={() => onOpen(it)}>
              <span className="history-title">{it.result.content.title}</span>
              <span className="muted">
                {it.form.content_type.replace("_", " ")} · {ago(it.ts)}
              </span>
            </button>
            <button type="button" className="btn btn-ghost btn-icon btn-sm" onClick={() => onDelete(it.id)} aria-label={`Delete draft ${it.result.content.title}`}>
              <Icon name="trash" size={15} />
            </button>
          </li>
        ))}
      </ul>
      <p className="muted small">Saved only in this browser.</p>
    </section>
  );
}
