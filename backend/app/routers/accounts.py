from fastapi import APIRouter, Depends, HTTPException
from app.database import supabase
from app.middleware import get_current_user
from app.schemas.accounts import AccountCreate, AccountUpdate, AccountOut, ConnectResponse
from typing import List
from uuid import uuid4
from datetime import datetime

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
    result = supabase.table("accounts").select("*").eq("user_id", user["sub"]).execute()
    return [_sanitize_account(acc) for acc in (result.data or [])]

@router.post("")
async def create_account(data: AccountCreate, user=Depends(get_current_user)):
    account = {
        "id": str(uuid4()),
        "user_id": user["sub"],
        "nickname": data.nickname,
        "broker": data.broker,
        "login": data.login,
        "server": data.server,
        "account_type": data.account_type,
        "password": data.password,  # ponytail: encrypt with pgcrypto or python-cryptography in production
        "status": "disconnected",
        "balance": 0,
        "equity": 0,
        "profit": 0,
        "created_at": datetime.utcnow().isoformat()
    }
    # Some deployments still have the OLD `accounts` schema (columns:
    # type/connected/metaapi_id — no password/status/connected_at). If the
    # insert is rejected for a missing column, adapt the payload to the live
    # schema instead of failing: drop the code-only columns one by one and
    # insert again. This keeps the endpoint working until the
    # 003_fix_accounts_schema.sql migration is applied.
    #
    # NOTE: no password column means the plaintext is not persisted on the
    # old schema — acceptable as a stopgap only; always apply the migration.
    while True:
        try:
            result = supabase.table("accounts").insert(account).execute()
            saved = result.data[0] if result.data else account
            return _sanitize_account(saved)
        except Exception as e:
            reason = str(e)
            missing = []
            for col in ('password', 'status', 'connected_at', 'account_type'):
                if f"Could not find the '{col}' column" in reason or f'Could not find the "{col}" column' in reason:
                    missing.append(col)
            if missing:
                for col in missing:
                    account.pop(col, None)
                continue  # retry with the missing columns removed
            raise HTTPException(status_code=500, detail=reason)

@router.get("/{account_id}")
async def get_account(account_id: str, user=Depends(get_current_user)):
    result = supabase.table("accounts").select("*").eq("id", account_id).eq("user_id", user["sub"]).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Account not found")
    return _sanitize_account(result.data)

@router.delete("/{account_id}")
async def delete_account(account_id: str, user=Depends(get_current_user)):
    result = supabase.table("accounts").delete().eq("id", account_id).eq("user_id", user["sub"]).execute()
    return {"success": True}

@router.post("/{account_id}/connect")
async def connect_account(account_id: str, user=Depends(get_current_user)):
    result = supabase.table("accounts").select("*").eq("id", account_id).eq("user_id", user["sub"]).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Account not found")

    acc = result.data
    balance = float(acc.get("balance") or 0.0)
    equity = float(acc.get("equity") or balance)
    profit = float(acc.get("profit") or 0.0)

    # Query local MT5 terminal if available
    try:
        from app.services import metaapi_service as mt5
        info = await mt5.get_account_info(account_id)
        if info and "balance" in info:
            balance = float(info.get("balance", balance))
            equity = float(info.get("equity", equity))
            profit = float(info.get("profit", 0.0))
    except Exception:
        pass

    supabase.table("accounts").update({
        "status": "connected",
        "balance": balance,
        "equity": equity,
        "profit": profit,
        "connected_at": datetime.utcnow().isoformat()
    }).eq("id", account_id).execute()

    return ConnectResponse(success=True, message="Connected successfully", balance=balance, equity=equity)

@router.post("/{account_id}/disconnect")
async def disconnect_account(account_id: str, user=Depends(get_current_user)):
    # Note: Do not invoke mt5.shutdown() on singleton server terminal, simply mark account disconnected
    supabase.table("accounts").update({"status": "disconnected"}).eq("id", account_id).eq("user_id", user["sub"]).execute()
    return {"success": True, "message": "Disconnected"}

@router.post("/{account_id}/sync")
async def sync_account(account_id: str, user=Depends(get_current_user)):
    result = supabase.table("accounts").select("*").eq("id", account_id).eq("user_id", user["sub"]).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Account not found")

    acc = result.data
    balance = float(acc.get("balance") or 0.0)
    equity = float(acc.get("equity") or balance)
    profit = float(acc.get("profit") or 0.0)

    try:
        from app.services import metaapi_service as mt5
        info = await mt5.get_account_info(account_id)
        if info and "balance" in info:
            balance = float(info.get("balance", balance))
            equity = float(info.get("equity", equity))
            profit = float(info.get("profit", profit))
    except Exception:
        pass

    supabase.table("accounts").update({
        "balance": balance,
        "equity": equity,
        "profit": profit
    }).eq("id", account_id).execute()

    return {"success": True, "balance": balance, "equity": equity, "profit": profit}
