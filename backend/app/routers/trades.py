import asyncio
from fastapi import APIRouter, Depends, HTTPException, Query
from app.database import supabase
from app.middleware import get_current_user
from app.schemas.trades import TradeCloseRequest, TradeModifySlRequest, TradePartialCloseRequest, TradeOpenRequest
from app.services import metaapi_service as mt5
from datetime import datetime
from uuid import uuid4
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.get("")
@router.get("/")
async def list_trades(
    user=Depends(get_current_user),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    status: str = None,
    strategy: str = None,
    pair: str = None,
    symbol: str = None,
):
    def _q():
        query = supabase.table("trades").select("*", count="exact").eq("user_id", user["sub"])
        if status:
            query = query.eq("status", status)
        if strategy:
            query = query.eq("strategy", strategy)
        target_symbol = symbol or pair
        if target_symbol:
            query = query.eq("symbol", target_symbol)
        return query.order("opened_at", desc=True).range(offset, offset + limit - 1).execute()

    def _acc():
        return supabase.table("accounts").select("login").eq("user_id", user["sub"]).eq("status", "connected").limit(1).execute()

    result, acc_res, terminal_info = await asyncio.gather(
        asyncio.to_thread(_q),
        asyncio.to_thread(_acc),
        mt5.get_account_info(""),
    )
    db_trades = result.data or []
    user_login = str(acc_res.data[0].get("login", "")).strip() if acc_res.data else ""
    terminal_login = str(terminal_info.get("login", "")).strip() if terminal_info else ""

    if offset == 0 and (not status or status == "open") and user_login and user_login == terminal_login:
        try:
            positions = await mt5.get_positions("")
            if symbol or pair:
                clean = (symbol or pair).replace("/", "").replace(" ", "").strip().upper()
                positions = [p for p in positions if clean in p.get("symbol", "").upper()]
            db_by_ticket = {str(t.get("ticket")): t for t in db_trades if t.get("ticket")}
            seen = set()
            merged = []
            for p in positions:
                t_str = str(p.get("ticket"))
                seen.add(t_str)
                db_row = db_by_ticket.get(t_str)
                merged.append({
                    "id": db_row.get("id") if db_row else f"mt5-{t_str}",
                    "ticket": t_str,
                    "symbol": p.get("symbol"),
                    "direction": (p.get("type") or "BUY").lower(),
                    "volume": p.get("volume"),
                    "open_price": p.get("open_price"),
                    "current_price": p.get("current_price"),
                    "profit": round(float(p.get("profit") or 0), 2),
                    "strategy": (db_row.get("strategy") if db_row else None) or (p.get("comment") or "mt5_live"),
                    "status": "open",
                    "opened_at": p.get("time") or (db_row.get("opened_at") if db_row else None),
                    "is_live": True,
                })
            for t in db_trades:
                ts = str(t.get("ticket") or "")
                if ts and ts in seen:
                    continue
                merged.append(t)
            return {"trades": merged[:limit], "total": max(result.count or 0, len(merged))}
        except Exception:
            pass

    return {"trades": db_trades, "total": result.count or 0}


@router.post("/open")
async def open_manual_trade(data: TradeOpenRequest, user=Depends(get_current_user)):
    """Open a manual market trade via MT5 terminal and persist record."""
    if data.lot_size <= 0:
        raise HTTPException(status_code=400, detail="Lot size must be greater than 0")

    order_type = data.type.upper()
    if order_type not in ["BUY", "SELL"]:
        raise HTTPException(status_code=400, detail="Trade type must be BUY or SELL")

    clean_symbol = data.symbol.replace("/", "").replace(" ", "").strip().upper()

    acc_res, terminal_info = await asyncio.gather(
        asyncio.to_thread(
            lambda: supabase.table("accounts").select("*").eq("user_id", user["sub"]).eq("status", "connected").limit(1).execute()
        ),
        mt5.get_account_info(""),
    )
    if not acc_res.data:
        raise HTTPException(
            status_code=400,
            detail="No connected trading account found. Please connect your broker account in the Portfolio tab before trading."
        )

    user_acc = acc_res.data[0]
    account_id = user_acc["id"]
    user_login = str(user_acc.get("login", "")).strip()
    terminal_login = str(terminal_info.get("login", "")).strip() if terminal_info else ""

    if not terminal_login or terminal_login != user_login:
        raise HTTPException(
            status_code=400,
            detail=f"Security alert: MetaTrader 5 Desktop is not synced with your connected account #{user_login}. Please log into #{user_login} on MT5 Desktop first."
        )

    result = await mt5.place_order(
        account_id=account_id,
        pair=clean_symbol,
        order_type=order_type,
        volume=float(data.lot_size),
        stop_loss=data.stop_loss,
        take_profit=data.take_profit,
        comment=data.comment or "Manual Trade"
    )

    if not result.get("success"):
        error_msg = result.get("error", "Order placement failed on MT5")
        raise HTTPException(status_code=400, detail=error_msg)

    opened_at = datetime.utcnow().isoformat()
    ticket_val = str(result.get("ticket"))
    exec_price = float(result.get("price", 0))

    try:
        trade_record = {
            "id": str(uuid4()),
            "user_id": user["sub"],
            "account_id": account_id or None,
            "bot_id": None,
            "strategy": "manual",
            "symbol": clean_symbol,
            "direction": order_type.lower(),
            "volume": float(data.lot_size),
            "open_price": exec_price,
            "stop_loss": float(data.stop_loss) if data.stop_loss else 0.0,
            "take_profit": float(data.take_profit) if data.take_profit else 0.0,
            "status": "open",
            "reason": data.reason or "Manual Analysis",
            "opened_at": opened_at,
        }
        try:
            await asyncio.to_thread(
                lambda: supabase.table("trades").insert({**trade_record, "ticket": ticket_val}).execute()
            )
        except Exception as col_err:
            if "ticket" in str(col_err).lower():
                await asyncio.to_thread(
                    lambda: supabase.table("trades").insert(trade_record).execute()
                )
            else:
                raise col_err
    except Exception as e:
        logger.error(f"Failed to insert manual trade record: {e}")

    return {
        "success": True,
        "ticket": ticket_val,
        "price": exec_price,
        "symbol": clean_symbol,
        "type": order_type,
        "volume": float(data.lot_size),
        "stop_loss": data.stop_loss,
        "take_profit": data.take_profit,
        "opened_at": opened_at,
        "message": f"Successfully opened {order_type} {data.lot_size} lots of {clean_symbol} at {exec_price}"
    }


@router.get("/positions")
async def get_live_positions(symbol: str = None, user=Depends(get_current_user)):
    """Fetch live open positions directly from MT5 terminal for the authenticated user's account."""
    try:
        acc_res, terminal_info = await asyncio.gather(
            asyncio.to_thread(
                lambda: supabase.table("accounts").select("login").eq("user_id", user["sub"]).eq("status", "connected").limit(1).execute()
            ),
            mt5.get_account_info(""),
        )
        if not acc_res.data:
            return {"positions": []}

        user_login = str(acc_res.data[0].get("login", "")).strip()
        terminal_login = str(terminal_info.get("login", "")).strip() if terminal_info else ""

        if not terminal_login or terminal_login != user_login:
            return {"positions": []}

        positions = await mt5.get_positions("")
        if symbol:
            clean = symbol.replace("/", "").replace(" ", "").strip().upper()
            positions = [p for p in positions if clean in p.get("symbol", "").upper()]
        return {"positions": positions}
    except Exception as e:
        return {"positions": [], "error": str(e)}


@router.post("/sync-mt5")
async def sync_closed_trades_from_mt5(user=Depends(get_current_user)):
    """Reconcile any DB 'open' trades that already hit SL/TP or were closed directly in MT5 Desktop."""
    try:
        acc_res, terminal_info = await asyncio.gather(
            asyncio.to_thread(
                lambda: supabase.table("accounts").select("login").eq("user_id", user["sub"]).eq("status", "connected").limit(1).execute()
            ),
            mt5.get_account_info(""),
        )
        if not acc_res.data:
            return {"synced": 0, "reason": "no_connected_account"}

        user_login = str(acc_res.data[0].get("login", "")).strip()
        terminal_login = str(terminal_info.get("login", "")).strip() if terminal_info else ""
        if not terminal_login or terminal_login != user_login:
            return {"synced": 0, "reason": "terminal_not_synced"}

        open_db_res, mt5_positions = await asyncio.gather(
            asyncio.to_thread(
                lambda: supabase.table("trades").select("id, ticket").eq("user_id", user["sub"]).eq("status", "open").execute()
            ),
            mt5.get_positions(""),
        )

        active_tickets = {str(p["ticket"]) for p in (mt5_positions or [])}
        synced = 0
        for row in (open_db_res.data or []):
            t_str = str(row.get("ticket") or "").strip()
            if not t_str or not t_str.isdigit() or t_str in active_tickets:
                continue
            profit = await mt5.get_history_deal_profit(int(t_str))
            await asyncio.to_thread(
                lambda rid=row["id"], pr=profit: supabase.table("trades").update({
                    "status": "closed",
                    "closed_at": datetime.utcnow().isoformat(),
                    "profit": pr,
                }).eq("id", rid).execute()
            )
            synced += 1
        return {"synced": synced}
    except Exception as e:
        logger.debug(f"sync_closed_trades_from_mt5 error: {e}")
        return {"synced": 0}


@router.post("/close")
async def close_trade(data: TradeCloseRequest, user=Depends(get_current_user)):
    """Close an open trade by ticket number via MT5."""
    acc_res, terminal_info = await asyncio.gather(
        asyncio.to_thread(
            lambda: supabase.table("accounts").select("login").eq("user_id", user["sub"]).eq("status", "connected").limit(1).execute()
        ),
        mt5.get_account_info(""),
    )
    if not acc_res.data:
        raise HTTPException(status_code=403, detail="No connected account found for this user")

    user_login = str(acc_res.data[0].get("login", "")).strip()
    terminal_login = str(terminal_info.get("login", "")).strip() if terminal_info else ""

    if not terminal_login or terminal_login != user_login:
        raise HTTPException(status_code=403, detail="MT5 terminal is not logged into your account")

    result = await mt5.close_position(data.account_id or "", str(data.ticket))
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Close failed"))

    realized_profit = 0.0
    try:
        realized_profit = await mt5.get_history_deal_profit(int(data.ticket))
    except Exception:
        pass

    try:
        await asyncio.to_thread(
            lambda: supabase.table("trades").update({
                "status": "closed",
                "closed_at": datetime.utcnow().isoformat(),
                "close_price": result.get("price"),
                "profit": realized_profit,
            }).eq("user_id", user["sub"]).eq("ticket", str(data.ticket)).execute()
        )
    except Exception as e:
        logger.error(f"Failed to update closed trade in database: {e}")

    return {
        "success": True,
        "ticket": data.ticket,
        "close_price": result.get("price"),
        "profit": realized_profit
    }


@router.post("/modify-sl")
async def modify_sl_trade(data: TradeModifySlRequest, user=Depends(get_current_user)):
    """Modify stop loss and/or take profit on an open trade via MT5."""
    if data.stop_loss is None and data.take_profit is None:
        raise HTTPException(status_code=400, detail="At least one of stop_loss or take_profit required")

    acc_res, terminal_info = await asyncio.gather(
        asyncio.to_thread(
            lambda: supabase.table("accounts").select("login").eq("user_id", user["sub"]).eq("status", "connected").limit(1).execute()
        ),
        mt5.get_account_info(""),
    )
    if not acc_res.data:
        raise HTTPException(status_code=403, detail="No connected account found for this user")

    user_login = str(acc_res.data[0].get("login", "")).strip()
    terminal_login = str(terminal_info.get("login", "")).strip() if terminal_info else ""

    if not terminal_login or terminal_login != user_login:
        raise HTTPException(status_code=403, detail="MT5 terminal is not logged into your account")

    result = await mt5.modify_sl_tp(data.account_id or "", str(data.ticket),
                                    stop_loss=data.stop_loss, take_profit=data.take_profit)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Modify failed"))
    return {"success": True, "ticket": data.ticket, "new_sl": data.stop_loss, "new_tp": data.take_profit}


@router.post("/partial-close")
async def partial_close_trade(data: TradePartialCloseRequest, user=Depends(get_current_user)):
    """Close a percentage of an open trade by ticket number via MT5."""
    if data.close_pct <= 0 or data.close_pct > 1:
        raise HTTPException(status_code=400, detail="close_pct must be in (0, 1]")

    acc_res, terminal_info = await asyncio.gather(
        asyncio.to_thread(
            lambda: supabase.table("accounts").select("login").eq("user_id", user["sub"]).eq("status", "connected").limit(1).execute()
        ),
        mt5.get_account_info(""),
    )
    if not acc_res.data:
        raise HTTPException(status_code=403, detail="No connected account found for this user")

    user_login = str(acc_res.data[0].get("login", "")).strip()
    terminal_login = str(terminal_info.get("login", "")).strip() if terminal_info else ""

    if not terminal_login or terminal_login != user_login:
        raise HTTPException(status_code=403, detail="MT5 terminal is not logged into your account")

    result = await mt5.partial_close_position(data.account_id or "", str(data.ticket), data.close_pct)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Partial close failed"))
    return {"success": True, "ticket": data.ticket, "close_pct": data.close_pct,
            "closed_volume": result.get("closed_volume"), "close_price": result.get("price")}
