// localStorage/sessionStorage can throw (private mode, blocked site data), so every access is guarded.
function store(kind) {
  try {
    return kind === "session" ? window.sessionStorage : window.localStorage;
  } catch {
    return null;
  }
}

export function readJSON(key, fallback, kind = "local") {
  try {
    const raw = store(kind)?.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

export function writeJSON(key, value, kind = "local") {
  try {
    store(kind)?.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable: the app still works, it just will not remember */
  }
}

export function removeKey(key, kind = "local") {
  try {
    store(kind)?.removeItem(key);
  } catch {
    /* ignore */
  }
}
