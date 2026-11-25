import asyncio
from fastapi import APIRouter, Depends, HTTPException
from app.database import supabase
from app.middleware import get_current_user, is_owner_or_admin
from app.schemas.bots import BotCreate, BotUpdate
from app.services import bot_engine
from uuid import uuid4
from datetime import datetime

router = APIRouter(prefix="/api/bots", tags=["bots"])


@router.get("")
async def list_bots(user=Depends(get_current_user)):
    result = await asyncio.to_thread(
        lambda: supabase.table("bot_settings").select("*").eq("user_id", user["sub"]).execute()
    )
    return result.data or []


@router.post("")
async def create_bot(data: BotCreate, user=Depends(get_current_user)):
    try:
        account_id = data.account_id
        if not account_id:
            acc_res = await asyncio.to_thread(
                lambda: supabase.table("accounts").select("id").eq("user_id", user["sub"]).eq("status", "connected").limit(1).execute()
            )
            if acc_res.data:
                account_id = acc_res.data[0]["id"]

        bot = {
            "id": str(uuid4()),
            "user_id": user["sub"],
            "account_id": account_id or "",
            "strategy": data.strategy,
            "status": "stopped",
            "pair": data.pair,
            "timeframe": data.timeframe,
            "lot_size": data.lot_size,
            "take_profit": data.take_profit,
            "stop_loss": data.stop_loss,
            "max_trades": data.max_trades,
            "max_daily_loss": data.max_daily_loss,
            "config": data.config,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        result = await asyncio.to_thread(
            lambda: supabase.table("bot_settings").insert(bot).execute()
        )
        return result.data[0] if result.data else bot
    except Exception as e:
        msg = str(e)
        if "bot_settings_strategy_check" in msg:
            raise HTTPException(
                status_code=400,
                detail=f"Database schema needs migration for '{data.strategy}'. Please run supabase/migrations/006_add_pipstep_reversal_and_security.sql in your Supabase SQL Editor."
            )
        raise HTTPException(status_code=400, detail=msg)


@router.get("/{bot_id}")
async def get_bot(bot_id: str, user=Depends(get_current_user)):
    result = await asyncio.to_thread(
        lambda: supabase.table("bot_settings").select("*").eq("id", bot_id).eq("user_id", user["sub"]).single().execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Bot not found")
    return result.data


@router.put("/{bot_id}")
async def update_bot(bot_id: str, data: BotUpdate, user=Depends(get_current_user)):
    try:
        updates = {k: v for k, v in data.dict().items() if v is not None}
        updates["updated_at"] = datetime.utcnow().isoformat()
        result = await asyncio.to_thread(
            lambda: supabase.table("bot_settings").update(updates).eq("id", bot_id).eq("user_id", user["sub"]).execute()
        )
        return result.data[0] if result.data else {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{bot_id}")
async def delete_bot(bot_id: str, user=Depends(get_current_user)):
    try:
        await bot_engine.stop_bot(bot_id)
        await asyncio.to_thread(
            lambda: supabase.table("bot_settings").delete().eq("id", bot_id).eq("user_id", user["sub"]).execute()
        )
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{bot_id}/start")
async def start_bot(bot_id: str, user=Depends(get_current_user)):
    try:
        result = await asyncio.to_thread(
            lambda: supabase.table("bot_settings").select("*").eq("id", bot_id).eq("user_id", user["sub"]).single().execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Bot not found")
        if result.data["status"] == "running":
            return {"success": True, "message": "Bot already running"}

        # Check plan & connected account concurrently
        def _get_sub():
            return supabase.table("subscriptions").select("plan").eq("user_id", user["sub"]).eq("status", "active").limit(1).execute()

        def _get_prof():
            return supabase.table("profiles").select("plan").eq("id", user["sub"]).limit(1).execute()

        def _get_acc():
            return supabase.table("accounts").select("*").eq("user_id", user["sub"]).eq("status", "connected").limit(1).execute()

        from app.services import metaapi_service as mt5
        sub_res, prof_res, acc_res, terminal_info = await asyncio.gather(
            asyncio.to_thread(_get_sub),
            asyncio.to_thread(_get_prof),
            asyncio.to_thread(_get_acc),
            mt5.get_account_info(""),
        )

        user_plan = "free"
        if is_owner_or_admin(user):
            user_plan = "elite"
        elif sub_res.data and sub_res.data[0].get("plan"):
            user_plan = sub_res.data[0]["plan"].lower()
        elif prof_res.data and prof_res.data[0].get("plan"):
            user_plan = prof_res.data[0]["plan"].lower()

        strategy_name = result.data.get("strategy", "").lower()

        if user_plan == "free":
            running_bots = await asyncio.to_thread(
                lambda: supabase.table("bot_settings").select("id").eq("user_id", user["sub"]).eq("status", "running").execute()
            )
            if running_bots.data and len(running_bots.data) >= 1:
                raise HTTPException(
                    status_code=403,
                    detail="Free Tier Limit: You can only run 1 active bot simultaneously. Please stop your running bot or upgrade to Pro."
                )
            if strategy_name == "pipstep_reversal":
                raise HTTPException(
                    status_code=403,
                    detail="PipStep Reversal EA requires the Pro Plan. Upgrade to unlock this strategy."
                )

        if user_plan == "pro":
            running_bots = await asyncio.to_thread(
                lambda: supabase.table("bot_settings").select("id").eq("user_id", user["sub"]).eq("status", "running").execute()
            )
            if running_bots.data and len(running_bots.data) >= 3:
                raise HTTPException(
                    status_code=403,
                    detail="Pro Plan Limit: You can run up to 3 active bots simultaneously."
                )

        ELITE_ONLY_STRATEGIES = {"trading_agents", "ai_committee", "signal_strength_hedge"}
        if strategy_name in ELITE_ONLY_STRATEGIES and user_plan != "elite":
            raise HTTPException(
                status_code=403,
                detail="This strategy is reserved for the Elite Plan (Coming Soon). It is currently locked."
            )

        if not acc_res.data:
            raise HTTPException(
                status_code=400,
                detail="Cannot start bot: No connected broker account found. Please connect your broker account in the Portfolio tab first."
            )

        user_acc = acc_res.data[0]
        user_login = str(user_acc.get("login", "")).strip()
        terminal_login = str(terminal_info.get("login", "")).strip() if terminal_info else ""

        if not terminal_login or terminal_login != user_login:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot start bot: MetaTrader 5 Desktop is not synced with your connected account #{user_login}. Please log into #{user_login} in MT5 Desktop first."
            )

        try:
            await asyncio.to_thread(
                lambda: supabase.table("bot_settings").update({
                    "account_id": user_acc["id"],
                    "status": "running",
                    "updated_at": datetime.utcnow().isoformat(),
                }).eq("id", bot_id).eq("user_id", user["sub"]).execute()
            )
            await bot_engine.start_bot(bot_id)
        except Exception as start_err:
            await asyncio.to_thread(
                lambda: supabase.table("bot_settings").update({"status": "stopped", "updated_at": datetime.utcnow().isoformat()}).eq("id", bot_id).eq("user_id", user["sub"]).execute()
            )
            raise HTTPException(status_code=400, detail=f"Failed to start bot engine: {str(start_err)}")

        return {"success": True, "message": "Bot started"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{bot_id}/stop")
async def stop_bot(bot_id: str, user=Depends(get_current_user)):
    try:
        await bot_engine.stop_bot(bot_id)
        await asyncio.to_thread(
            lambda: supabase.table("bot_settings").update({"status": "stopped", "updated_at": datetime.utcnow().isoformat()}).eq("id", bot_id).eq("user_id", user["sub"]).execute()
        )
        return {"success": True, "message": "Bot stopped"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
