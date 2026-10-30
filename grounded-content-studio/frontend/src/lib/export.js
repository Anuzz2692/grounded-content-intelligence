/** Content shape: { title, summary, introduction, sections: [{heading, body}], conclusion, suggested_cta } */

export function toMarkdown(c) {
  const parts = [`# ${c.title}`, "", `*${c.summary}*`, "", c.introduction, ""];
  for (const s of c.sections) parts.push(`## ${s.heading}`, "", s.body, "");
  parts.push(`## Conclusion`, "", c.conclusion);
  if (c.suggested_cta) parts.push("", `> ${c.suggested_cta}`);
  return parts.join("\n").trim() + "\n";
}

export function toPlainText(c) {
  const parts = [c.title, "", c.summary, "", c.introduction, ""];
  for (const s of c.sections) parts.push(s.heading.toUpperCase(), "", s.body, "");
  parts.push("CONCLUSION", "", c.conclusion);
  if (c.suggested_cta) parts.push("", c.suggested_cta);
  return parts.join("\n").trim() + "\n";
}

const METADATA = /^(tags|hashtags|title and hook options)$/i;
const SCREENPLAY = /^screenplay$/i;

function spokenLines(body) {
  return body
    .split("\n")
    .map((line) => line.match(/^\s*voice[- ]?over\s*:\s*(.*)$/i)?.[1]?.trim())
    .filter(Boolean)
    .join(" ");
}

/**
 * Only the writing: no labels, tags, hashtags or scene directions. For a video that is the spoken
 * lines plus the caption. Useful for pasting into a scheduler, and the only part of a social post
 * that a reader (or a detector) can judge as prose.
 */
export function toProseText(c) {
  const spoken = c.sections.filter((s) => SCREENPLAY.test(s.heading.trim())).map((s) => spokenLines(s.body)).filter(Boolean);
  const parts = [];
  // In a video the hook and the closing line are already spoken in the screenplay.
  const alreadySpoken = (text) => spoken.some((line) => line.toLowerCase().includes(text.trim().toLowerCase()));
  if (c.introduction && !alreadySpoken(c.introduction)) parts.push(c.introduction.trim());
  for (const s of c.sections) {
    const heading = s.heading.trim();
    if (METADATA.test(heading)) continue;
    parts.push(SCREENPLAY.test(heading) ? spokenLines(s.body) : s.body.trim());
  }
  if (c.conclusion && !alreadySpoken(c.conclusion)) parts.push(c.conclusion.trim());
  return parts.filter(Boolean).join("\n\n") + "\n";
}

export function slugify(text) {
  return (
    String(text || "content")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 60) || "content"
  );
}

export function wordCount(c) {
  const text = [c.summary, c.introduction, ...c.sections.map((s) => `${s.heading} ${s.body}`), c.conclusion].join(" ");
  return text.split(/\s+/).filter(Boolean).length;
}

export function download(filename, text, mime = "text/markdown") {
  const url = URL.createObjectURL(new Blob([text], { type: `${mime};charset=utf-8` }));
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Clipboard API needs a secure context; fall back for plain http on a LAN address.
    const ta = Object.assign(document.createElement("textarea"), { value: text });
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch {
      ok = false;
    }
    ta.remove();
    return ok;
  }
}
