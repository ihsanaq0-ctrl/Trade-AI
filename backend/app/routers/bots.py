from fastapi import APIRouter, Depends, HTTPException
from app.database import supabase
from app.middleware import get_current_user
from app.schemas.bots import BotCreate, BotUpdate, BotOut
from app.services import bot_engine
from uuid import uuid4
from datetime import datetime

router = APIRouter(prefix="/api/bots", tags=["bots"])


@router.get("")
async def list_bots(user=Depends(get_current_user)):
    result = supabase.table("bot_settings").select("*").eq("user_id", user["sub"]).execute()
    return result.data


@router.post("")
async def create_bot(data: BotCreate, user=Depends(get_current_user)):
    try:
        bot = {
            "id": str(uuid4()),
            "user_id": user["sub"],
            "account_id": data.account_id,
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
        result = supabase.table("bot_settings").insert(bot).execute()
        return result.data[0] if result.data else bot
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{bot_id}")
async def get_bot(bot_id: str, user=Depends(get_current_user)):
    result = supabase.table("bot_settings").select("*").eq("id", bot_id).eq("user_id", user["sub"]).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Bot not found")
    return result.data


@router.put("/{bot_id}")
async def update_bot(bot_id: str, data: BotUpdate, user=Depends(get_current_user)):
    try:
        updates = {k: v for k, v in data.dict().items() if v is not None}
        updates["updated_at"] = datetime.utcnow().isoformat()
        result = supabase.table("bot_settings").update(updates).eq("id", bot_id).eq("user_id", user["sub"]).execute()
        return result.data[0] if result.data else {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{bot_id}")
async def delete_bot(bot_id: str, user=Depends(get_current_user)):
    try:
        await bot_engine.stop_bot(bot_id)
        supabase.table("bot_settings").delete().eq("id", bot_id).eq("user_id", user["sub"]).execute()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{bot_id}/start")
async def start_bot(bot_id: str, user=Depends(get_current_user)):
    try:
        result = supabase.table("bot_settings").select("*").eq("id", bot_id).eq("user_id", user["sub"]).single().execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Bot not found")
        if result.data["status"] == "running":
            return {"success": True, "message": "Bot already running"}
        
        try:
            await bot_engine.start_bot(bot_id)
            supabase.table("bot_settings").update({"status": "running", "updated_at": datetime.utcnow().isoformat()}).eq("id", bot_id).eq("user_id", user["sub"]).execute()
        except Exception as start_err:
            supabase.table("bot_settings").update({"status": "stopped", "updated_at": datetime.utcnow().isoformat()}).eq("id", bot_id).eq("user_id", user["sub"]).execute()
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
        supabase.table("bot_settings").update({"status": "stopped", "updated_at": datetime.utcnow().isoformat()}).eq("id", bot_id).eq("user_id", user["sub"]).execute()
        return {"success": True, "message": "Bot stopped"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))