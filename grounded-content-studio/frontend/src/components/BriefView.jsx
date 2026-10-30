import { Badge, Card, CopyButton } from "./ui.jsx";
import { CHECK_STATUS } from "../lib/brief.js";

const COLUMNS = ["time", "visual", "spoken line", "on-screen text"];

/** Title, hook, script table, caption, hashtags, claims used and the self-check, in the required order. */
export default function BriefView({ result }) {
  const report = result.brief_report;
  const typedTitle = result.content.title;
  const hook = result.content.introduction;
  const sections = Object.fromEntries(result.content.sections.map((s) => [s.heading.toLowerCase(), s.body]));
  const overall = CHECK_STATUS[report.overall] || CHECK_STATUS.UNVERIFIED;
  const wc = report.word_count;

  return (
    <div className="brief-view">
      <Card title="1. Title"><p>{typedTitle}</p></Card>
      <Card title="2. Hook"><p>{hook}</p></Card>
      <Card title="3. Script" aside={<span className="muted small">{wc.actual} spoken words (allowed {wc.minimum}-{wc.maximum})</span>}>
        <div className="table-wrap">
          <table className="script-table">
            <thead><tr>{COLUMNS.map((c) => <th key={c}>{c}</th>)}</tr></thead>
            <tbody>
              {report.script_table.map((row, i) => (
                <tr key={i}>{COLUMNS.map((c) => <td key={c}>{row[c]}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Card title="4. Caption" aside={<CopyButton getText={() => sections.caption || ""} />}><p>{sections.caption}</p></Card>
      <Card title="5. Hashtags"><p>{sections.hashtags || <span className="muted">None</span>}</p></Card>
      <Card title="6. Claims used">
        {report.claims_used.length ? (
          <ul className="claims-used">
            {report.claims_used.map((c) => (
              <li key={c.id}><strong>{c.id}</strong> <span>{c.statement}</span> <span className="muted small">({c.used_in.join(", ")})</span></li>
            ))}
          </ul>
        ) : <p className="muted">No approved claim was cited.</p>}
      </Card>
      <Card title="7. Self-check" aside={<Badge tone={overall.tone}>{overall.label}</Badge>}>
        <p className="muted small">{report.note}</p>
        <ul className="checks">
          {report.checks.map((c) => {
            const s = CHECK_STATUS[c.status] || CHECK_STATUS.UNVERIFIED;
            return (
              <li key={c.id}>
                <Badge tone={s.tone}>{s.label}</Badge> <strong>{c.name}</strong>
                <span className="muted small"> {c.detail}</span>
              </li>
            );
          })}
        </ul>
      </Card>
    </div>
  );
}
