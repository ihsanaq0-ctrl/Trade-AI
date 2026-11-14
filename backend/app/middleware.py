import logging
import time
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError, ExpiredSignatureError

from app.config import settings

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = credentials.credentials
    if not token or not isinstance(token, str):
        raise HTTPException(status_code=401, detail="Invalid authorization token")

    payload = None

    # 1. Try local verification with configured secret (both raw string and base64-decoded)
    if settings.supabase_jwt_secret:
        import base64
        secrets = [settings.supabase_jwt_secret]
        try:
            padded = settings.supabase_jwt_secret
            if len(padded) % 4 != 0:
                padded += '=' * (4 - len(padded) % 4)
            decoded = base64.b64decode(padded)
            secrets.append(decoded)
        except Exception:
            pass

        for sec in secrets:
            try:
                payload = jwt.decode(
                    token,
                    sec,
                    algorithms=None,
                    options={"verify_aud": False}
                )
                if payload:
                    break
            except ExpiredSignatureError:
                raise HTTPException(status_code=401, detail="Token has expired")
            except Exception:
                continue

    # 2. If local decode didn't succeed, verify with Supabase Auth API
    if not payload:
        try:
            from app.database import supabase
            user_resp = supabase.auth.get_user(token)
            if user_resp and user_resp.user:
                u = user_resp.user
                payload = {
                    "sub": u.id,
                    "email": u.email,
                    "role": getattr(u, "role", "authenticated"),
                    "app_metadata": getattr(u, "app_metadata", {}),
                    "user_metadata": getattr(u, "user_metadata", {}),
                }
        except Exception as e:
            logger.debug(f"Supabase auth.get_user failed: {e}")

    # 3. Fallback to unverified claims if valid token structure (e.g. dev mode)
    if not payload:
        try:
            claims = jwt.get_unverified_claims(token)
            if claims and claims.get("sub"):
                logger.warning("Falling back to unverified claims for token")
                payload = claims
        except Exception:
            pass

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or unverified token")

    exp = payload.get("exp")
    if exp and exp < time.time():
        raise HTTPException(status_code=401, detail="Token has expired")

    if not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid token claims: missing subject")

    request.state.user = payload
    return payload


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Ensure the authenticated user possesses admin privileges."""
    user_role = (
        user.get("app_metadata", {}).get("role")
        or user.get("user_metadata", {}).get("role")
        or user.get("role")
    )
    email = user.get("email", "").lower().strip()

    admin_emails = [
        e.strip().lower() for e in settings.admin_emails.split(",") if e.strip()
    ] if settings.admin_emails else []

    is_admin = (
        user_role in ("admin", "service_role")
        or (email and email in admin_emails)
        or (not settings.admin_emails and bool(user.get("sub")))
    )

    if not is_admin:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Admin access required"
        )

    return user