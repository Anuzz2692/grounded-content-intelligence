import { useCallback, useEffect, useRef, useState } from "react";
import Composer from "./components/Composer.jsx";
import ErrorBanner from "./components/ErrorBanner.jsx";
import Header from "./components/Header.jsx";
import History from "./components/History.jsx";
import Loading from "./components/Loading.jsx";
import Result from "./components/Result.jsx";
import Settings from "./components/Settings.jsx";
import { Icon } from "./components/ui.jsx";
import { ApiError, generate, getHealth } from "./lib/api.js";
import { EMPTY_BRIEF, buildBrief } from "./lib/brief.js";
import { ProfileContext, profileFromHealth } from "./lib/profile.js";
import { readJSON, removeKey, writeJSON } from "./lib/storage.js";

const DEFAULT_FORM = { query: "", content_type: "article", length: "standard", tone: "Empathetic and clear", validate_content: true, polish: "natural", use_brief: false, brief: EMPTY_BRIEF };
const HISTORY_KEY = "art-history-v1";
const FORM_KEY = "art-form-v1";
const KEY_NAME = "art-api-key";
const MAX_HISTORY = 10;

function loadKey() {
  const session = readJSON(KEY_NAME, "", "session");
  if (session) return { apiKey: session, remember: false };
  const local = readJSON(KEY_NAME, "");
  return { apiKey: local || "", remember: Boolean(local) };
}

export default function App() {
  const [form, setForm] = useState(() => {
    const saved = readJSON(FORM_KEY, {});
    return { ...DEFAULT_FORM, ...saved, brief: { ...EMPTY_BRIEF, ...(saved.brief || {}) } };
  });
  const [health, setHealth] = useState(null);
  const [{ apiKey, remember }, setKeyState] = useState(loadKey);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const [status, setStatus] = useState("idle"); // idle | loading | done | error
  const [result, setResult] = useState(null);
  const [content, setContent] = useState(null);
  const [error, setError] = useState(null);
  const [cooldown, setCooldown] = useState(0);
  const [history, setHistory] = useState(() => readJSON(HISTORY_KEY, []));
  const [activeId, setActiveId] = useState(null);

  const abortRef = useRef(null);
  const outputRef = useRef(null);

  useEffect(() => writeJSON(FORM_KEY, form), [form]);
  useEffect(() => writeJSON(HISTORY_KEY, history), [history]);

  // Health check on load, then every 30s so the status pill stays honest.
  const checkHealth = useCallback(async () => {
    try {
      setHealth(await getHealth());
    } catch {
      setHealth("offline");
    }
  }, []);
  useEffect(() => {
    checkHealth();
    const id = setInterval(checkHealth, 30000);
    return () => clearInterval(id);
  }, [checkHealth]);

  useEffect(() => {
    if (cooldown <= 0) return;
    const id = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(id);
  }, [cooldown]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const saveKey = (key, keep) => {
    removeKey(KEY_NAME, "session");
    removeKey(KEY_NAME);
    if (key) writeJSON(KEY_NAME, key, keep ? "local" : "session");
    setKeyState({ apiKey: key, remember: keep });
    if (error?.kind === "auth") setError(null);
  };

  const submit = async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setStatus("loading");
    setError(null);
    const { polish, use_brief, brief: briefForm, ...rest } = form;
    const withBrief = use_brief && form.content_type === "video_script";
    const payload = {
      ...rest,
      ...(withBrief ? { brief: buildBrief(briefForm).brief } : {}),
      query: form.query.trim(),
      tone: form.tone.trim() || DEFAULT_FORM.tone,
      humanize: polish !== "off",
      humanize_level: polish === "light" ? "light" : "natural",
    };

    try {
      const data = await generate(payload, { apiKey, signal: controller.signal });
      const entry = { id: crypto.randomUUID?.() ?? String(Date.now()), ts: Date.now(), form: { ...payload, polish, use_brief: withBrief, brief: briefForm }, result: data };
      setResult(data);
      setContent(data.content);
      setActiveId(entry.id);
      setHistory((h) => [entry, ...h].slice(0, MAX_HISTORY));
      setStatus("done");
      requestAnimationFrame(() => outputRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
    } catch (err) {
      const apiError = err instanceof ApiError ? err : new ApiError({ kind: "unknown", message: "Something unexpected went wrong." });
      if (apiError.kind === "cancelled") {
        setStatus(result ? "done" : "idle");
        return;
      }
      if (apiError.kind === "rate_limit" && apiError.retryAfter) setCooldown(apiError.retryAfter);
      if (apiError.kind === "network") checkHealth();
      setError(apiError);
      setStatus("error");
      requestAnimationFrame(() => outputRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
    }
  };

  const openEntry = (entry) => {
    // Drafts saved before the polish setting existed only have the old on/off flag.
    const polish = entry.form.polish ?? (entry.form.humanize === false ? "off" : "natural");
    setForm((f) => ({ ...f, ...entry.form, polish, brief: { ...EMPTY_BRIEF, ...(entry.form.brief || {}) }, use_brief: Boolean(entry.form.use_brief) }));
    setResult(entry.result);
    setContent(entry.result.content);
    setActiveId(entry.id);
    setError(null);
    setStatus("done");
  };

  const deleteEntry = (id) => {
    setHistory((h) => h.filter((x) => x.id !== id));
    if (id === activeId) setActiveId(null);
  };

  const showResult = result && status !== "loading";
  const profile = profileFromHealth(health);

  return (
    <ProfileContext.Provider value={profile}>
    <div className="app">
      <Header health={health} hasKey={Boolean(apiKey)} onOpenSettings={() => setSettingsOpen(true)} />
      <div className="layout">
        <aside className="side">
          <Composer form={form} setForm={setForm} onSubmit={submit} onCancel={() => abortRef.current?.abort()} loading={status === "loading"} cooldown={cooldown} />
          <History items={history} activeId={activeId} onOpen={openEntry} onDelete={deleteEntry} onClear={() => { setHistory([]); setActiveId(null); }} />
        </aside>

        <main className="main" ref={outputRef} aria-live="polite">
          {error && <ErrorBanner error={error} health={health} cooldown={cooldown} onRetry={submit} onOpenSettings={() => setSettingsOpen(true)} />}
          {status === "loading" && <Loading validating={form.validate_content} />}
          {showResult && <Result key={activeId} result={result} content={content} onContentChange={setContent} />}
          {!result && status !== "loading" && !error && (
            <section className="empty">
              <span className="empty-mark" aria-hidden="true">
                <Icon name="sparkle" size={28} />
              </span>
              <h1>{profile.tagline}</h1>
              <p>
                Describe a topic and the studio reads {profile.subject}'s own website, drafts the content from it, then flags any brand issues or unsupported claims a human should check.
              </p>
              <ul className="empty-points">
                <li>Grounded in {profile.subject}'s published pages, with sources you can open</li>
                <li>Every draft is marked for human review. Nothing is auto-approved</li>
                <li>Edit, copy or download as Markdown or text</li>
              </ul>
            </section>
          )}
        </main>
      </div>
      <Settings open={settingsOpen} onClose={() => setSettingsOpen(false)} apiKey={apiKey} remember={remember} onSave={saveKey} health={health} />
    </div>
    </ProfileContext.Provider>
  );
}
