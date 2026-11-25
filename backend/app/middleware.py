import asyncio
import base64
import hashlib
import json
import logging
import time
import urllib.request
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, jwk, ExpiredSignatureError

from app.config import settings

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)

# In-memory caches to avoid blocking Supabase Cloud calls on every API request
_JWKS_CACHE: dict = {"keys": {}, "fetched_at": 0.0}
_JWKS_TTL_SEC = 3600.0

_TOKEN_CACHE: dict = {}
_TOKEN_TTL_SEC = 60.0
_MAX_TOKEN_CACHE = 512


def _fetch_jwks_sync() -> dict:
    """Fetch public JWKS keys from Supabase Auth to verify ES256/RS256 JWTs locally."""
    if not settings.supabase_url:
        return {}
    url = settings.supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"
    headers = {"Accept": "application/json"}
    if settings.supabase_key:
        headers["apikey"] = settings.supabase_key
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        out = {}
        for k in data.get("keys", []):
            kid = k.get("kid") or "_default"
            out[kid] = {
                "alg": k.get("alg", "ES256"),
                "key": jwk.construct(k),
            }
        return out


async def _get_jwks_keys() -> dict:
    now = time.time()
    if _JWKS_CACHE["keys"] and (now - _JWKS_CACHE["fetched_at"] < _JWKS_TTL_SEC):
        return _JWKS_CACHE["keys"]
    try:
        keys = await asyncio.to_thread(_fetch_jwks_sync)
        if keys:
            _JWKS_CACHE["keys"] = keys
            _JWKS_CACHE["fetched_at"] = now
    except Exception as e:
        logger.debug(f"JWKS fetch warning: {e}")
    return _JWKS_CACHE["keys"]


def _verify_hs256_sync(token: str) -> dict | None:
    if not settings.supabase_jwt_secret:
        return None
    secrets = [settings.supabase_jwt_secret]
    try:
        padded = settings.supabase_jwt_secret
        if len(padded) % 4 != 0:
            padded += "=" * (4 - len(padded) % 4)
        secrets.append(base64.b64decode(padded))
    except Exception:
        pass

    for sec in secrets:
        try:
            payload = jwt.decode(
                token,
                sec,
                algorithms=["HS256", "HS384", "HS512"],
                options={"verify_aud": False},
            )
            if payload:
                return payload
        except ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired")
        except Exception:
            continue
    return None


def _verify_supabase_api_sync(token: str) -> dict | None:
    from app.database import supabase
    user_resp = supabase.auth.get_user(token)
    if user_resp and user_resp.user:
        u = user_resp.user
        return {
            "sub": u.id,
            "email": u.email,
            "role": getattr(u, "role", "authenticated"),
            "app_metadata": getattr(u, "app_metadata", {}) or {},
            "user_metadata": getattr(u, "user_metadata", {}) or {},
        }
    return None


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = credentials.credentials
    if not token or not isinstance(token, str):
        raise HTTPException(status_code=401, detail="Invalid authorization token")

    now = time.time()
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    # 0. Fast-path in-memory verification cache (reduces 500ms/req -> 0.01ms/req)
    cached = _TOKEN_CACHE.get(token_hash)
    if cached:
        cached_payload, cached_at = cached
        exp = cached_payload.get("exp")
        if (now - cached_at < _TOKEN_TTL_SEC) and (not exp or exp > now):
            request.state.user = cached_payload
            return cached_payload
        else:
            _TOKEN_CACHE.pop(token_hash, None)

    payload = None

    # Inspect JWT header to pick fast cryptographic verifier cleanly
    try:
        header = jwt.get_unverified_header(token)
    except Exception:
        header = {}

    alg = header.get("alg", "")
    kid = header.get("kid")

    # 1. Verify asymmetric ES256/RS256 token locally using Supabase JWKS public key
    if alg.startswith(("ES", "RS")):
        jwks_keys = await _get_jwks_keys()
        key_entry = jwks_keys.get(kid) or (next(iter(jwks_keys.values()), None) if jwks_keys else None)
        if key_entry:
            try:
                payload = jwt.decode(
                    token,
                    key_entry["key"],
                    algorithms=[alg, key_entry["alg"]],
                    options={"verify_aud": False},
                )
            except ExpiredSignatureError:
                raise HTTPException(status_code=401, detail="Token has expired")
            except Exception as e:
                logger.debug(f"JWKS decode failed: {e}")

    # 2. Try symmetric HS256 secret verification
    if not payload and (alg.startswith("HS") or not alg):
        payload = _verify_hs256_sync(token)

    # 3. Authoritative fallback via Supabase Auth Cloud (run off event loop)
    if not payload:
        try:
            payload = await asyncio.to_thread(_verify_supabase_api_sync, token)
        except Exception as e:
            logger.debug(f"Supabase auth.get_user failed: {e}")

    # STRICT SECURITY: Never fall back to unverified JWT claims.
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or unverified token")

    exp = payload.get("exp")
    if exp and exp < now:
        raise HTTPException(status_code=401, detail="Token has expired")

    if not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid token claims: missing subject")

    # Populate bounded cache
    if len(_TOKEN_CACHE) >= _MAX_TOKEN_CACHE:
        _TOKEN_CACHE.clear()
    _TOKEN_CACHE[token_hash] = (payload, now)

    request.state.user = payload
    return payload


def is_owner_or_admin(user: dict | None) -> bool:
    """Return True if the authenticated user is an app admin/owner."""
    if not user:
        return False
    app_meta = user.get("app_metadata") or {}
    user_role = app_meta.get("role")
    email = (user.get("email") or "").lower().strip()
    admin_emails = [
        e.strip().lower() for e in settings.admin_emails.split(",") if e.strip()
    ] if settings.admin_emails else []
    return (
        user_role in ("admin", "service_role")
        or (bool(email) and email in admin_emails)
    )


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """
    Fail-closed Admin check. Requires explicit 'admin'/'service_role' claim
    or user email listed in ADMIN_EMAILS env config. Never allows regular
    authenticated users to execute admin endpoints when ADMIN_EMAILS is unset.
    """
    if not is_owner_or_admin(user):
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Admin access required"
        )

    return user


async def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict | None:
    """Return authenticated user claims if a valid token is present, else None."""
    if not credentials or not credentials.credentials:
        return None
    try:
        return await get_current_user(request, credentials)
    except Exception:
        return None
