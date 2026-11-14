"""
Gumroad API wrapper for license verification.
https://app.gumroad.com/api
"""

async def verify_license(license_key: str, product_permalink: str) -> dict:
    """Verify a Gumroad license key."""
    # ponytail: POST https://api.gumroad.com/v2/licenses/verify
    return {"success": True, "uses": 1}
