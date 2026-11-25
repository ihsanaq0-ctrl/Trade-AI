import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from app.database import supabase
from app.middleware import get_current_user
from app.config import settings
from app.services import gumroad_service
from uuid import uuid4
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/payments", tags=["payments"])


class LicenseActivateRequest(BaseModel):
    license_key: str


@router.get("/plans")
async def get_plans():
    """Return membership tier metadata and live checkout availability."""
    return {
        "checkout_url": settings.gumroad_pro_url or "",
        "gumroad_configured": bool(settings.gumroad_product_id and settings.gumroad_pro_url),
        "tiers": [
            {
                "id": "free",
                "name": "Free Starter",
                "price_monthly": 0,
                "active_bot_limit": 1,
                "available": True,
            },
            {
                "id": "pro",
                "name": "Pro Trader",
                "price_monthly": 29,
                "active_bot_limit": 3,
                "available": True,
            },
            {
                "id": "elite",
                "name": "Elite VIP",
                "price_monthly": 79,
                "active_bot_limit": 99,
                "available": False,
                "coming_soon": True,
            },
        ],
    }


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

    if settings.gumroad_secret:
        provided_secret = (
            request.query_params.get("secret")
            or request.headers.get("x-gumroad-secret")
            or payload.get("secret")
        )
        if provided_secret != settings.gumroad_secret:
            raise HTTPException(status_code=401, detail="Unauthorized: Invalid Gumroad webhook secret")
    else:
        logger.warning("GUMROAD_SECRET is not configured; rejecting unauthenticated webhook in production")
        raise HTTPException(status_code=503, detail="Webhook secret not configured on server")

    event = payload.get("event") or ("sale" if payload.get("sale_id") else "")
    license_key = payload.get("license_key") or payload.get("subscription_id", "")
    email = (payload.get("email") or payload.get("purchaser_email") or "").strip().lower()
    product_id = payload.get("product_id", "")

    if not email:
        raise HTTPException(status_code=400, detail="Missing customer email in webhook payload")

    user_result = await asyncio.to_thread(
        lambda: supabase.table("profiles").select("id").eq("email", email).execute()
    )
    if not user_result.data:
        raise HTTPException(status_code=404, detail="User not found")

    user_id = user_result.data[0]["id"]

    if event in ("sale", "charge.succeeded"):
        sub = {
            "id": str(uuid4()),
            "user_id": user_id,
            "gumroad_license_key": license_key,
            "gumroad_product_id": product_id,
            "plan": "pro",
            "status": "active",
            "current_period_start": datetime.utcnow().isoformat(),
            "current_period_end": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        }
        await asyncio.to_thread(lambda: supabase.table("subscriptions").insert(sub).execute())
        await asyncio.to_thread(lambda: supabase.table("profiles").update({"plan": "pro"}).eq("id", user_id).execute())

    elif event in ("refund", "subscription_ended", "cancellation", "subscription_cancelled"):
        await asyncio.to_thread(
            lambda: supabase.table("subscriptions").update({"status": "cancelled"}).eq("gumroad_license_key", license_key).execute()
        )
        await asyncio.to_thread(
            lambda: supabase.table("profiles").update({"plan": "free"}).eq("id", user_id).execute()
        )
        await asyncio.to_thread(
            lambda: supabase.table("bot_settings").update({"status": "stopped"}).eq("user_id", user_id).eq("status", "running").execute()
        )

    return {"success": True}


@router.get("/license")
async def check_license(user=Depends(get_current_user)):
    sub_res, prof_res = await asyncio.gather(
        asyncio.to_thread(
            lambda: supabase.table("subscriptions").select("plan, status, gumroad_license_key").eq("user_id", user["sub"]).eq("status", "active").limit(1).execute()
        ),
        asyncio.to_thread(
            lambda: supabase.table("profiles").select("plan").eq("id", user["sub"]).limit(1).execute()
        ),
    )

    if sub_res.data:
        return {
            "plan": (sub_res.data[0].get("plan") or "pro").lower(),
            "status": "active",
            "license_key": sub_res.data[0].get("gumroad_license_key")
        }

    if prof_res.data and prof_res.data[0].get("plan"):
        plan_val = prof_res.data[0]["plan"].lower()
        return {"plan": plan_val, "status": "active" if plan_val != "free" else "none"}

    return {"plan": "free", "status": "none"}


@router.post("/activate-license")
async def activate_license(data: LicenseActivateRequest, user=Depends(get_current_user)):
    """Activate a Pro subscription using a verified Gumroad license key or pre-issued database license."""
    license_key = (data.license_key or "").strip()
    if not license_key:
        raise HTTPException(status_code=400, detail="Please enter a valid license key")

    # 1. Check if key was already pre-provisioned or webhook-recorded in DB
    existing = await asyncio.to_thread(
        lambda: supabase.table("subscriptions").select("*").eq("gumroad_license_key", license_key).limit(1).execute()
    )
    if existing.data:
        row = existing.data[0]
        if row.get("user_id") and row["user_id"] != user["sub"]:
            raise HTTPException(status_code=403, detail="This license key is already bound to another account")
        await asyncio.to_thread(
            lambda: supabase.table("subscriptions").update({"user_id": user["sub"], "status": "active", "plan": "pro"}).eq("id", row["id"]).execute()
        )
        await asyncio.to_thread(
            lambda: supabase.table("profiles").update({"plan": "pro"}).eq("id", user["sub"]).execute()
        )
        return {"success": True, "plan": "pro", "message": "Pro Trader license activated!"}

    # 2. Verify live against Gumroad v2 API
    verification = await gumroad_service.verify_license(license_key)
    if not verification.get("success"):
        raise HTTPException(
            status_code=400,
            detail=verification.get("message") or "Invalid or expired license key"
        )

    purchase = verification.get("purchase") or {}
    if purchase.get("refunded") or purchase.get("chargebacked") or purchase.get("subscription_ended_at"):
        raise HTTPException(status_code=400, detail="This license key has been refunded or cancelled")

    sub = {
        "id": str(uuid4()),
        "user_id": user["sub"],
        "gumroad_license_key": license_key,
        "gumroad_product_id": settings.gumroad_product_id or purchase.get("product_id", ""),
        "plan": "pro",
        "status": "active",
        "current_period_start": datetime.utcnow().isoformat(),
        "current_period_end": datetime.utcnow().isoformat(),
        "created_at": datetime.utcnow().isoformat(),
    }
    await asyncio.to_thread(lambda: supabase.table("subscriptions").insert(sub).execute())
    await asyncio.to_thread(lambda: supabase.table("profiles").update({"plan": "pro"}).eq("id", user["sub"]).execute())

    return {"success": True, "plan": "pro", "message": "Pro Trader license verified & activated!"}


@router.post("/validate")
async def validate_license(data: dict, user=Depends(get_current_user)):
    license_key = (data.get("license_key") or "").strip()
    if not license_key:
        return {"valid": False, "plan": "free"}
    result = await asyncio.to_thread(
        lambda: supabase.table("subscriptions").select("*").eq("gumroad_license_key", license_key).eq("user_id", user["sub"]).eq("status", "active").execute()
    )
    if result.data:
        return {"valid": True, "plan": result.data[0].get("plan", "pro")}
    verification = await gumroad_service.verify_license(license_key)
    if verification.get("success"):
        return {"valid": True, "plan": "pro"}
    return {"valid": False, "plan": "free"}
