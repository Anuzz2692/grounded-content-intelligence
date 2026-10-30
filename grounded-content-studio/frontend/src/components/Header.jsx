import { useProfile } from "../lib/profile.js";
import { Icon } from "./ui.jsx";

export default function Header({ health, onOpenSettings, hasKey }) {
  const profile = useProfile();
  let state = "checking";
  let text = "Checking server…";
  if (health === "offline") {
    state = "bad";
    text = "Server offline";
  } else if (health) {
    const needsKey = health.auth_enabled && !hasKey;
    const ollama = health.ollama;
    const localOnly = health.llm_provider === "ollama";
    state = needsKey ? "warn" : "ok";
    text = needsKey ? "API key needed" : localOnly ? "Server online · Ollama" : "Server online";
    // In Ollama-only mode a missing model or stopped Ollama means nothing can be generated.
    if (localOnly && ollama && !ollama.reachable) {
      state = "bad";
      text = "Ollama not running";
    } else if (localOnly && ollama?.model_installed === false) {
      state = "warn";
      text = "Ollama model missing";
    }
  }

  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true">
          <Icon name="sparkle" size={20} />
        </span>
        <div>
          <div className="brand-name">{profile.name}</div>
          <div className="brand-sub">Content Studio</div>
        </div>
      </div>
      <div className="topbar-actions">
        <span className={`status-pill status-${state}`} role="status">
          <span className="dot" aria-hidden="true" />
          {text}
        </span>
        <button type="button" className="btn btn-ghost btn-icon" onClick={onOpenSettings} aria-label="Settings">
          <Icon name="settings" />
        </button>
      </div>
    </header>
  );
}
