from fastapi import APIRouter, Depends, HTTPException, Query
from app.database import supabase
from app.middleware import get_current_user
from app.schemas.trades import TradeCloseRequest, TradeModifySlRequest, TradePartialCloseRequest, TradeOpenRequest
from app.services import metaapi_service as mt5
from datetime import datetime
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
    query = supabase.table("trades").select("*", count="exact").eq("user_id", user["sub"])
    if status:
        query = query.eq("status", status)
    if strategy:
        query = query.eq("strategy", strategy)
    target_symbol = symbol or pair
    if target_symbol:
        query = query.eq("symbol", target_symbol)
    result = query.order("opened_at", desc=True).range(offset, offset + limit - 1).execute()
    return {"trades": result.data or [], "total": result.count or 0}


@router.post("/open")
async def open_manual_trade(data: TradeOpenRequest, user=Depends(get_current_user)):
    """Open a manual market trade via MT5 terminal and persist record."""
    if data.lot_size <= 0:
        raise HTTPException(status_code=400, detail="Lot size must be greater than 0")
    
    order_type = data.type.upper()
    if order_type not in ["BUY", "SELL"]:
        raise HTTPException(status_code=400, detail="Trade type must be BUY or SELL")

    clean_symbol = data.symbol.replace("/", "").replace(" ", "").strip().upper()

    # Identify user's connected MT5 account
    acc_res = supabase.table("accounts").select("*").eq("user_id", user["sub"]).eq("status", "connected").limit(1).execute()
    if not acc_res.data:
        raise HTTPException(
            status_code=400,
            detail="No connected trading account found. Please connect your broker account in the Portfolio tab before trading."
        )

    user_acc = acc_res.data[0]
    account_id = user_acc["id"]
    user_login = str(user_acc.get("login", "")).strip()

    # Verify MT5 terminal is logged into THIS user's account
    terminal_info = await mt5.get_account_info("")
    terminal_login = str(terminal_info.get("login", "")).strip() if terminal_info else ""

    if not terminal_login or terminal_login != user_login:
        raise HTTPException(
            status_code=400,
            detail=f"Security alert: MT5 Desktop is currently logged into account #{terminal_login or 'None'}, but your connected account is #{user_login}. Please log into account #{user_login} on MT5 Desktop first."
        )

    # Send order to MT5
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

    # Persist in Supabase trades table
    try:
        trade_record = {
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
            supabase.table("trades").insert({**trade_record, "ticket": ticket_val}).execute()
        except Exception as col_err:
            if "ticket" in str(col_err).lower():
                supabase.table("trades").insert(trade_record).execute()
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
        acc_res = supabase.table("accounts").select("*").eq("user_id", user["sub"]).eq("status", "connected").limit(1).execute()
        if not acc_res.data:
            return {"positions": []}

        user_acc = acc_res.data[0]
        user_login = str(user_acc.get("login", "")).strip()

        terminal_info = await mt5.get_account_info("")
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


@router.post("/close")
async def close_trade(data: TradeCloseRequest, user=Depends(get_current_user)):
    """Close an open trade by ticket number via MT5."""
    acc_res = supabase.table("accounts").select("*").eq("user_id", user["sub"]).eq("status", "connected").limit(1).execute()
    if not acc_res.data:
        raise HTTPException(status_code=403, detail="No connected account found for this user")

    user_acc = acc_res.data[0]
    user_login = str(user_acc.get("login", "")).strip()

    terminal_info = await mt5.get_account_info("")
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

    # Mark the trade as closed in the local database using its ticket.
    try:
        supabase.table("trades").update({
            "status": "closed",
            "closed_at": datetime.utcnow().isoformat(),
            "close_price": result.get("price"),
            "profit": realized_profit,
        }).eq("user_id", user["sub"]).eq("ticket", str(data.ticket)).execute()
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
        
    acc_res = supabase.table("accounts").select("*").eq("user_id", user["sub"]).eq("status", "connected").limit(1).execute()
    if not acc_res.data:
        raise HTTPException(status_code=403, detail="No connected account found for this user")

    user_acc = acc_res.data[0]
    user_login = str(user_acc.get("login", "")).strip()

    terminal_info = await mt5.get_account_info("")
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
        
    acc_res = supabase.table("accounts").select("*").eq("user_id", user["sub"]).eq("status", "connected").limit(1).execute()
    if not acc_res.data:
        raise HTTPException(status_code=403, detail="No connected account found for this user")

    user_acc = acc_res.data[0]
    user_login = str(user_acc.get("login", "")).strip()

    terminal_info = await mt5.get_account_info("")
    terminal_login = str(terminal_info.get("login", "")).strip() if terminal_info else ""

    if not terminal_login or terminal_login != user_login:
        raise HTTPException(status_code=403, detail="MT5 terminal is not logged into your account")

    result = await mt5.partial_close_position(data.account_id or "", str(data.ticket), data.close_pct)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Partial close failed"))
    return {"success": True, "ticket": data.ticket, "close_pct": data.close_pct,
            "closed_volume": result.get("closed_volume"), "close_price": result.get("price")}
