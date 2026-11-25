import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from app.database import supabase
from app.middleware import get_current_user
from app.config import settings
from uuid import uuid4
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payments", tags=["payments"])

@router.post("/webhook-gumroad")
async def gumroad_webhook(request: Request):
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")
    else:
        try:
            form = await request.form()
            payload = dict(form)
        except Exception:
            try:
                payload = await request.json()
            except Exception:
                payload = {}

    # Verify Gumroad webhook secret if configured
    if settings.gumroad_secret:
        provided_secret = (
            request.query_params.get("secret")
            or request.headers.get("x-gumroad-secret")
            or payload.get("secret")
        )
        if provided_secret != settings.gumroad_secret:
            raise HTTPException(status_code=401, detail="Unauthorized: Invalid Gumroad webhook secret")
    else:
        logger.warning("GUMROAD_SECRET is not configured; webhook processing without secret verification")

    event = payload.get("event") or ("sale" if payload.get("sale_id") else "")
    license_key = payload.get("license_key") or payload.get("subscription_id", "")
    email = (payload.get("email") or payload.get("purchaser_email") or "").strip().lower()
    product_id = payload.get("product_id", "")

    if not email:
        raise HTTPException(status_code=400, detail="Missing customer email in webhook payload")

    # Find user by email
    user_result = supabase.table("profiles").select("id").eq("email", email).execute()
    if not user_result.data:
        raise HTTPException(status_code=404, detail="User not found")

    user_id = user_result.data[0]["id"]

    if event in ("sale", "charge.succeeded"):
        # Create subscription record
        sub = {
            "id": str(uuid4()),
            "user_id": user_id,
            "gumroad_license_key": license_key,
            "gumroad_product_id": product_id,
            "plan": "pro",
            "status": "active",
            "current_period_start": datetime.utcnow().isoformat(),
            "current_period_end": datetime.utcnow().isoformat(),  # extend properly in production
            "created_at": datetime.utcnow().isoformat()
        }
        supabase.table("subscriptions").insert(sub).execute()
        # Upgrade user plan
        supabase.table("profiles").update({"plan": "pro"}).eq("id", user_id).execute()

    elif event in ("refund", "subscription_ended", "cancellation", "subscription_cancelled"):
        supabase.table("subscriptions").update({"status": "cancelled"}).eq("gumroad_license_key", license_key).execute()
        supabase.table("profiles").update({"plan": "free"}).eq("id", user_id).execute()
        # Stop all running bots
        supabase.table("bot_settings").update({"status": "stopped"}).eq("user_id", user_id).eq("status", "running").execute()

    return {"success": True}

@router.get("/license")
async def check_license(user=Depends(get_current_user)):
    result = supabase.table("subscriptions").select("*").eq("user_id", user["sub"]).eq("status", "active").execute()
    if result.data:
        return {"plan": result.data[0].get("plan", "pro"), "status": "active", "license_key": result.data[0].get("gumroad_license_key")}
    try:
        prof = supabase.table("profiles").select("plan").eq("id", user["sub"]).limit(1).execute()
        if prof.data and prof.data[0].get("plan"):
            return {"plan": prof.data[0]["plan"].lower(), "status": "active"}
    except Exception:
        pass
    return {"plan": "free", "status": "none"}

@router.post("/validate")
async def validate_license(data: dict, user=Depends(get_current_user)):
    license_key = data.get("license_key", "")
    # ponytail: verify via Gumroad API: GET https://api.gumroad.com/v2/licenses/verify
    result = supabase.table("subscriptions").select("*").eq("gumroad_license_key", license_key).eq("user_id", user["sub"]).execute()
    if result.data:
        return {"valid": True, "plan": "pro"}
    return {"valid": False, "plan": "free"}
