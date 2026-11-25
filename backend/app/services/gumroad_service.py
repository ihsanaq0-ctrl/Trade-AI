"""
Gumroad API wrapper for real license verification.
https://app.gumroad.com/api#licenses
"""

import asyncio
import json
import logging
import urllib.parse
import urllib.request
import urllib.error
from app.config import settings

logger = logging.getLogger(__name__)


def _verify_license_sync(license_key: str, product_id: str) -> dict:
    payload = urllib.parse.urlencode({
        "product_id": product_id,
        "license_key": license_key.strip(),
        "increment_uses_count": "true",
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.gumroad.com/v2/licenses/verify",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as he:
        try:
            body = json.loads(he.read().decode("utf-8"))
            return body
        except Exception:
            return {"success": False, "message": f"Gumroad HTTP {he.code}"}
    except Exception as e:
        return {"success": False, "message": str(e)}


async def verify_license(license_key: str, product_id: str = "") -> dict:
    """Verify a Gumroad license key against Gumroad's v2 API."""
    pid = (product_id or settings.gumroad_product_id or "").strip()
    if not license_key or not license_key.strip():
        return {"success": False, "message": "License key is required."}
    if not pid:
        return {
            "success": False,
            "message": "Gumroad product ID is not yet configured on this server. Verify via Supabase subscriptions or contact support.",
        }
    return await asyncio.to_thread(_verify_license_sync, license_key.strip(), pid)
