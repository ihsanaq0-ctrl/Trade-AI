import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException
from app.database import supabase
from app.middleware import get_current_user
from app.schemas.accounts import AccountCreate, ConnectResponse
from app.services.crypto_utils import encrypt_secret, decrypt_secret
from uuid import uuid4
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def _sanitize_account(account: dict) -> dict:
    if not account:
        return account
    cleaned = dict(account)
    if "password" in cleaned:
        cleaned["has_password"] = bool(cleaned["password"])
        cleaned["password"] = "••••••••" if cleaned["password"] else ""
    return cleaned


@router.get("")
async def list_accounts(user=Depends(get_current_user)):
    result = await asyncio.to_thread(
        lambda: supabase.table("accounts").select("*").eq("user_id", user["sub"]).execute()
    )
    return [_sanitize_account(acc) for acc in (result.data or [])]


@router.post("")
async def create_account(data: AccountCreate, user=Depends(get_current_user)):
    encrypted_pw = encrypt_secret(data.password) if data.password else ""
    account = {
        "id": str(uuid4()),
        "user_id": user["sub"],
        "nickname": data.nickname,
        "broker": data.broker,
        "login": data.login.strip(),
        "server": data.server.strip(),
        "account_type": data.account_type,
        "password": encrypted_pw,
        "status": "disconnected",
        "balance": 0,
        "equity": 0,
        "profit": 0,
        "created_at": datetime.utcnow().isoformat()
    }
    while True:
        try:
            result = await asyncio.to_thread(
                lambda: supabase.table("accounts").insert(account).execute()
            )
            saved = result.data[0] if result.data else account
            return _sanitize_account(saved)
        except Exception as e:
            reason = str(e)
            missing = []
            for col in ("password", "status", "connected_at", "account_type"):
                if f"Could not find the '{col}' column" in reason or f'Could not find the "{col}" column' in reason:
                    missing.append(col)
            if missing:
                for col in missing:
                    account.pop(col, None)
                continue
            raise HTTPException(status_code=500, detail=reason)


@router.get("/{account_id}")
async def get_account(account_id: str, user=Depends(get_current_user)):
    result = await asyncio.to_thread(
        lambda: supabase.table("accounts").select("*").eq("id", account_id).eq("user_id", user["sub"]).single().execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Account not found")
    return _sanitize_account(result.data)


@router.delete("/{account_id}")
async def delete_account(account_id: str, user=Depends(get_current_user)):
    await asyncio.to_thread(
        lambda: supabase.table("accounts").delete().eq("id", account_id).eq("user_id", user["sub"]).execute()
    )
    return {"success": True}


@router.post("/{account_id}/connect")
async def connect_account(account_id: str, user=Depends(get_current_user)):
    result = await asyncio.to_thread(
        lambda: supabase.table("accounts").select("*").eq("id", account_id).eq("user_id", user["sub"]).single().execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Account not found")

    acc = result.data
    target_login = str(acc.get("login", "")).strip()
    target_password = decrypt_secret(acc.get("password", "") or "")
    target_server = str(acc.get("server", "") or "").strip()

    if not target_login:
        raise HTTPException(status_code=400, detail="Missing MT5 Login ID on this account")

    # Security guard: prevent another user from binding to an already-connected MT5 login
    # unless they supply a valid password proving broker ownership.
    other_owner_res = await asyncio.to_thread(
        lambda: supabase.table("accounts")
        .select("id, user_id")
        .eq("login", target_login)
        .eq("status", "connected")
        .neq("user_id", user["sub"])
        .execute()
    )
    if other_owner_res.data and not target_password:
        raise HTTPException(
            status_code=403,
            detail=f"MT5 account #{target_login} is currently linked to another active user session. Provide broker password credentials to verify ownership."
        )

    from app.services import metaapi_service as mt5

    # 1. Check current terminal login (off event loop)
    info = await mt5.get_account_info(account_id)
    terminal_login = str(info.get("login", "")).strip() if info else ""

    # 2. Switch terminal login when password & server are available (also verifies password!)
    if target_login.isdigit() and target_password and target_server:
        if terminal_login != target_login or other_owner_res.data:
            def _try_mt5_login():
                mod = mt5._ensure_mt5()
                return mod.login(int(target_login), password=target_password, server=target_server)

            try:
                switched = await asyncio.to_thread(_try_mt5_login)
                if switched:
                    info = await mt5.get_account_info(account_id)
                    terminal_login = str(info.get("login", "")).strip() if info else ""
                elif other_owner_res.data:
                    raise HTTPException(
                        status_code=403,
                        detail=f"MT5 broker credential verification failed for account #{target_login}."
                    )
            except HTTPException:
                raise
            except Exception as e:
                logger.warning(f"MT5 login switch error: {e}")

    # Privacy-safe check: NEVER disclose another user's live terminal_login in error responses
    if not terminal_login or terminal_login != target_login:
        raise HTTPException(
            status_code=400,
            detail=f"Unable to connect: MetaTrader 5 Desktop is not currently logged into account #{target_login}. Please open MT5 Desktop and log into #{target_login} ({target_server or 'your broker server'}) first."
        )

    balance = float(info.get("balance", acc.get("balance") or 0.0))
    equity = float(info.get("equity", balance))
    profit = float(info.get("profit", 0.0))

    # If ownership verified via password switch, release stale locks on other users' rows for this login
    if other_owner_res.data:
        await asyncio.to_thread(
            lambda: supabase.table("accounts")
            .update({"status": "disconnected"})
            .eq("login", target_login)
            .neq("user_id", user["sub"])
            .execute()
        )

    # Mark other accounts of this user as disconnected, then mark target connected
    await asyncio.to_thread(
        lambda: supabase.table("accounts").update({"status": "disconnected"}).eq("user_id", user["sub"]).execute()
    )
    await asyncio.to_thread(
        lambda: supabase.table("accounts").update({
            "status": "connected",
            "balance": balance,
            "equity": equity,
            "profit": profit,
            "connected_at": datetime.utcnow().isoformat()
        }).eq("id", account_id).execute()
    )

    return ConnectResponse(success=True, message="Connected successfully", balance=balance, equity=equity)


@router.post("/{account_id}/disconnect")
async def disconnect_account(account_id: str, user=Depends(get_current_user)):
    await asyncio.to_thread(
        lambda: supabase.table("accounts").update({"status": "disconnected"}).eq("id", account_id).eq("user_id", user["sub"]).execute()
    )
    # Also stop any running bots bound to this disconnecting account for this user
    try:
        bots_res = await asyncio.to_thread(
            lambda: supabase.table("bot_settings").select("id").eq("user_id", user["sub"]).eq("status", "running").execute()
        )
        if bots_res.data:
            from app.services import bot_engine
            for b in bots_res.data:
                await bot_engine.stop_bot(b["id"])
            await asyncio.to_thread(
                lambda: supabase.table("bot_settings").update({"status": "stopped"}).eq("user_id", user["sub"]).eq("status", "running").execute()
            )
    except Exception as e:
        logger.debug(f"Disconnect bot stop notice: {e}")

    return {"success": True, "message": "Disconnected"}


@router.post("/{account_id}/sync")
async def sync_account(account_id: str, user=Depends(get_current_user)):
    result = await asyncio.to_thread(
        lambda: supabase.table("accounts").select("*").eq("id", account_id).eq("user_id", user["sub"]).single().execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Account not found")

    acc = result.data
    target_login = str(acc.get("login", "")).strip()

    from app.services import metaapi_service as mt5
    info = await mt5.get_account_info(account_id)
    terminal_login = str(info.get("login", "")).strip() if info else ""

    if not terminal_login or terminal_login != target_login:
        raise HTTPException(
            status_code=400,
            detail=f"Sync failed: MT5 Desktop is not currently synced with account #{target_login}. Please switch to #{target_login} in MetaTrader 5."
        )

    balance = float(info.get("balance", acc.get("balance") or 0.0))
    equity = float(info.get("equity", balance))
    profit = float(info.get("profit", acc.get("profit") or 0.0))

    await asyncio.to_thread(
        lambda: supabase.table("accounts").update({
            "balance": balance,
            "equity": equity,
            "profit": profit
        }).eq("id", account_id).execute()
    )

    return {"success": True, "balance": balance, "equity": equity, "profit": profit}
