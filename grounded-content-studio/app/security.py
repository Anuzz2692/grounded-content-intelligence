import hashlib
import hmac
import time
from collections import deque

from fastapi import HTTPException, Request

from app.config import get_settings

_WINDOW_SECONDS = 60.0
_MAX_CLIENTS = 10_000

# client id -> timestamps of requests inside the window. Single-process, in-memory:
# limits are per worker and reset on restart.
_hits: dict[str, deque[float]] = {}


def reset_rate_limits() -> None:
    _hits.clear()


def _authenticate(request: Request) -> str | None:
    """Return a stable client id for a valid key, or None when auth is disabled."""
    keys = get_settings().api_key_list
    if not keys:
        return None

    supplied = request.headers.get("x-api-key", "")
    # Compare against every key so timing does not reveal which one matched.
    matched = False
    for key in keys:
        matched |= hmac.compare_digest(supplied.encode(), key.encode())
    if not supplied or not matched:
        raise HTTPException(status_code=401, detail="Missing or invalid API key.")
    return "key:" + hashlib.sha256(supplied.encode()).hexdigest()[:16]


def _check_rate_limit(client_id: str) -> None:
    limit = get_settings().rate_limit_per_minute
    if limit <= 0:
        return

    now = time.monotonic()
    if len(_hits) >= _MAX_CLIENTS:
        for cid in [c for c, q in _hits.items() if not q or now - q[-1] > _WINDOW_SECONDS]:
            del _hits[cid]

    hits = _hits.setdefault(client_id, deque())
    while hits and now - hits[0] > _WINDOW_SECONDS:
        hits.popleft()

    if len(hits) >= limit:
        retry_after = max(1, int(_WINDOW_SECONDS - (now - hits[0])) + 1)
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Try again shortly.",
            headers={"Retry-After": str(retry_after)},
        )
    hits.append(now)


async def require_access(request: Request) -> None:
    """FastAPI dependency: authenticate, then rate-limit per key (or per IP if auth is off).

    Behind a reverse proxy, configure the server to pass the real client address,
    otherwise every request shares the proxy's IP.
    """
    client_id = _authenticate(request)
    if client_id is None:
        client_id = "ip:" + (request.client.host if request.client else "unknown")
    _check_rate_limit(client_id)
