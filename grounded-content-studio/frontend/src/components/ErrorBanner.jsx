import { reasonText } from "../lib/api.js";
import { Icon } from "./ui.jsx";

const TITLES = {
  auth: "API key needed",
  rate_limit: "Slow down a moment",
  unavailable: "Couldn't generate this",
  upstream: "Couldn't read the website",
  invalid: "Check your request",
  network: "Can't reach the server",
  unknown: "Something went wrong",
};

export default function ErrorBanner({ error, onOpenSettings, onRetry, cooldown, health }) {
  const providerLabel = { anthropic: "Main AI service", ollama: "Local model (Ollama)" };
  const model = health && health !== "offline" ? health.ollama?.model : null;
  const missingModel = error.reasons?.ollama === "model_not_found";
  return (
    <div className="banner banner-danger" role="alert">
      <Icon name="alert" />
      <div className="banner-body">
        <strong>{TITLES[error.kind] || TITLES.unknown}</strong>
        <p>{error.message}</p>
        {error.reasons && (
          <ul className="plain-list">
            {Object.entries(error.reasons).map(([provider, code]) => (
              <li key={provider}>
                {providerLabel[provider] || provider}: {reasonText(code)}
              </li>
            ))}
          </ul>
        )}
        {missingModel && (
          <p className="fix-hint">
            Install it, then try again:
            <code>ollama pull {model || "your-model-name"}</code>
            <span className="muted small">Run <code>ollama list</code> to see installed models, and make sure OLLAMA_MODEL in .env matches one of them exactly.</span>
          </p>
        )}
        <div className="banner-actions">
          {error.kind === "auth" && (
            <button type="button" className="btn btn-primary btn-sm" onClick={onOpenSettings}>
              Open settings
            </button>
          )}
          {error.kind !== "auth" && error.kind !== "invalid" && (
            <button type="button" className="btn btn-secondary btn-sm" onClick={onRetry} disabled={cooldown > 0}>
              {cooldown > 0 ? `Try again in ${cooldown}s` : "Try again"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
