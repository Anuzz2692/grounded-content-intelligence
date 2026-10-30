export class ApiError extends Error {
  constructor({ kind, status = 0, message, retryAfter = null, reasons = null }) {
    super(message);
    this.kind = kind; // auth | rate_limit | unavailable | upstream | invalid | network | cancelled | unknown
    this.status = status;
    this.retryAfter = retryAfter;
    this.reasons = reasons;
  }
}

const REASON_TEXT = {
  auth: "the API key was rejected",
  rate_limit: "the provider's rate limit was hit",
  timeout: "the request timed out",
  connection: "the service could not be reached",
  truncated: "the output was cut off",
  bad_output: "the model returned unusable output",
  not_configured: "no API key is configured",
  model_not_found: "the model is not installed in Ollama",
};

export function reasonText(code) {
  if (!code) return "";
  if (REASON_TEXT[code]) return REASON_TEXT[code];
  if (code.startsWith("http_")) return `the provider returned HTTP ${code.slice(5)}`;
  return code.replaceAll("_", " ");
}

function detailText(body) {
  const d = body?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    // A nested field (for example brief.approved_claims.0.id) is named so the person knows what to fix.
    return d.map((x) => (x?.msg && Array.isArray(x.loc) && x.loc.length > 2 ? `${x.loc.slice(1).join(".")}: ${x.msg}` : x?.msg)).filter(Boolean).join("; ");
  }
  return "";
}

/** Turn an HTTP failure into an ApiError with wording a person can act on. Pure, so it is easy to test. */
export function describeHttpError(status, body, headers) {
  const detail = detailText(body);
  const retryAfter = Number(headers?.get?.("Retry-After")) || null;

  if (status === 401) {
    return new ApiError({ kind: "auth", status, message: "This server needs a valid API key. Add it in Settings and try again." });
  }
  if (status === 429) {
    return new ApiError({
      kind: "rate_limit",
      status,
      retryAfter,
      message: retryAfter
        ? `You're sending requests too quickly. You can try again in ${retryAfter} seconds.`
        : "You're sending requests too quickly. Please wait a moment.",
    });
  }
  if (status === 503) {
    const reasons = body?.reasons || null;
    return new ApiError({
      kind: "unavailable",
      status,
      reasons,
      message: "The AI service couldn't write this.",
    });
  }
  if (status === 502) {
    return new ApiError({ kind: "upstream", status, message: detail || "The website could not be read. Try again shortly." });
  }
  if (status === 422) {
    return new ApiError({ kind: "invalid", status, message: detail || "The request was not valid. Check the form." });
  }
  return new ApiError({ kind: "unknown", status, message: detail || `Unexpected error (HTTP ${status}).` });
}

async function readBody(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

export async function getHealth(signal) {
  const response = await fetch("/health", { signal });
  if (!response.ok) throw new Error(`health ${response.status}`);
  return response.json();
}

export async function generate(payload, { apiKey, signal } = {}) {
  let response;
  try {
    response = await fetch("/api/v1/content/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(apiKey ? { "X-API-Key": apiKey } : {}) },
      body: JSON.stringify(payload),
      signal,
    });
  } catch (err) {
    if (err?.name === "AbortError") throw new ApiError({ kind: "cancelled", message: "Cancelled." });
    throw new ApiError({
      kind: "network",
      message: "Can't reach the server. Is the backend running at the address you opened this page from?",
    });
  }

  const body = await readBody(response);
  if (!response.ok) {
    const error = describeHttpError(response.status, body, response.headers);
    // The 503 detail embeds provider reason codes as text; surface them as structured data when present.
    if (response.status === 503 && !error.reasons) {
      const match = detailText(body).match(/\{.*\}/);
      if (match) {
        try {
          error.reasons = JSON.parse(match[0].replaceAll("'", '"'));
        } catch {
          /* keep the generic message */
        }
      }
    }
    throw error;
  }
  return body;
}
