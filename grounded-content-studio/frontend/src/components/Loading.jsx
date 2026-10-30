import { useEffect, useState } from "react";

// Stage timing is a rough guide: the API returns one response, so progress cannot be measured.
const STAGES = [
  { from: 0, text: "Reading the website" },
  { from: 5, text: "Writing the draft" },
  { from: 25, text: "Running checks", onlyIfValidating: true },
];

export default function Loading({ validating }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const stages = STAGES.filter((s) => validating || !s.onlyIfValidating);
  let current = 0;
  stages.forEach((s, i) => {
    if (seconds >= s.from) current = i;
  });

  return (
    <div className="card loading" role="status" aria-live="polite">
      <div className="loading-top">
        <span className="spinner" aria-hidden="true" />
        <div>
          <strong>{stages[current].text}…</strong>
          <div className="muted">{seconds}s elapsed. This usually takes under a minute.</div>
        </div>
      </div>
      <ol className="stages">
        {stages.map((s, i) => (
          <li key={s.text} className={i < current ? "done" : i === current ? "active" : ""}>
            {s.text}
          </li>
        ))}
      </ol>
      <div className="skeleton" aria-hidden="true">
        <span style={{ width: "70%" }} />
        <span style={{ width: "95%" }} />
        <span style={{ width: "88%" }} />
        <span style={{ width: "60%" }} />
      </div>
    </div>
  );
}
