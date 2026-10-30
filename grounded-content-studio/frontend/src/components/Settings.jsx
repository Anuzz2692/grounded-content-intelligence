import { useEffect, useRef, useState } from "react";
import { Icon } from "./ui.jsx";

export default function Settings({ open, onClose, apiKey, remember, onSave, health }) {
  const ref = useRef(null);
  const [key, setKey] = useState(apiKey);
  const [keep, setKeep] = useState(remember);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      setKey(apiKey);
      setKeep(remember);
      dialog.showModal();
    }
    if (!open && dialog.open) dialog.close();
  }, [open, apiKey, remember]);

  return (
    <dialog ref={ref} className="dialog" onClose={onClose} onClick={(e) => e.target === ref.current && onClose()}>
      <form
        method="dialog"
        onSubmit={(e) => {
          e.preventDefault();
          onSave(key.trim(), keep);
          onClose();
        }}
      >
        <div className="dialog-head">
          <h2>Settings</h2>
          <button type="button" className="btn btn-ghost btn-icon" onClick={onClose} aria-label="Close settings">
            <Icon name="x" />
          </button>
        </div>

        <label className="field">
          <span className="field-label">API key</span>
          <input type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="Paste your access key" autoComplete="off" spellCheck="false" />
          <small className="muted">
            {health && health !== "offline"
              ? health.auth_enabled
                ? "This server requires a key."
                : "This server does not require a key right now."
              : "Sent as the X-API-Key header with each request."}
          </small>
        </label>

        <label className="check">
          <input type="checkbox" checked={keep} onChange={(e) => setKeep(e.target.checked)} />
          <span>Remember on this device</span>
        </label>
        <p className="notice">
          <Icon name="shield" size={16} />
          <span>
            Anything stored in a browser can be read by whoever uses this computer. Only keep the key on a device you trust. By default it is forgotten when you close the tab.
          </span>
        </p>

        <div className="dialog-actions">
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary">
            Save
          </button>
        </div>
      </form>
    </dialog>
  );
}
