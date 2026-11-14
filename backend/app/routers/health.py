from fastapi import APIRouter, Query, Depends
from app.services import metaapi_service as mt5
from app.middleware import get_optional_user
from app.database import supabase
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}


@router.get("/api/markets/prices")
async def get_market_prices():
    """Fetch real-time prices from MT5 for common symbols."""
    symbols = ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'AUDUSD', 'USDCAD', 'GBPJPY', 'EURJPY',
               'BTCUSD', 'ETHUSD', 'SOLUSD', 'XRPUSD', 'LTCUSD', 'BNBUSD', 'DOGEUSD', 'ADAUSD', 'XAGUSD']
    result = []
    try:
        mod = mt5._ensure_mt5()
        for pair in symbols:
            resolved = mt5._resolve_symbol(pair)
            tick = mod.symbol_info_tick(resolved)
            s_info = mod.symbol_info(resolved)
            if tick:
                digits = s_info.digits if s_info else (3 if "JPY" in pair else (2 if any(c in pair for c in ["BTC", "ETH", "XAU"]) else 5))
                if s_info and s_info.point and s_info.point > 0:
                    pip_multiplier = 10 if digits in (3, 5) else 1
                    pip_size = s_info.point * pip_multiplier
                    spread = round((tick.ask - tick.bid) / pip_size, 1)
                else:
                    pip_size = 0.01 if "JPY" in pair else (0.1 if "XAU" in pair else (1.0 if "BTC" in pair else 0.0001))
                    spread = round((tick.ask - tick.bid) / pip_size, 1)

                result.append({
                    "symbol": pair,
                    "bid": round(tick.bid, digits),
                    "ask": round(tick.ask, digits),
                    "spread": max(0.0, spread),
                    "time": tick.time,
                })
    except Exception as e:

        import logging

        logging.getLogger(__name__).error(f"Swallowed error: {e}")
    return {"prices": result}


@router.get("/api/markets/candles")
async def get_candles(
    symbol: str = Query("EURUSD"),
    timeframe: str = Query("H1"),
    count: int = Query(100, le=500),
):
    """Fetch OHLCV candle data from MT5 for the chart."""
    try:
        clean_symbol = symbol.replace("/", "").replace(" ", "").strip().upper()
        candles = await mt5.get_candles(clean_symbol, timeframe, count)
        return {"symbol": clean_symbol, "timeframe": timeframe, "candles": candles}
    except Exception as e:
        return {"error": str(e), "candles": []}


@router.get("/api/markets/active-account")
async def get_active_account(user=Depends(get_optional_user)):
    """
    Get the currently connected broker account for the AUTHENTICATED user.
    Never exposes another user's local terminal account or balances.
    """
    if not user or not user.get("sub"):
        return {"connected": False, "login": None, "balance": 0.0, "equity": 0.0}

    try:
        # Query Supabase for this specific user's connected account
        res = supabase.table("accounts").select("*").eq("user_id", user["sub"]).eq("status", "connected").limit(1).execute()
        if not res.data:
            return {"connected": False, "login": None, "balance": 0.0, "equity": 0.0}

        user_acc = res.data[0]
        user_login = str(user_acc.get("login", "")).strip()

        # Check MT5 terminal
        terminal_info = await mt5.get_account_info(user_acc["id"])
        terminal_login = str(terminal_info.get("login", "")).strip() if terminal_info else ""

        # Only return live terminal figures if the terminal is logged into THIS user's account!
        if terminal_login and terminal_login == user_login:
            # Update DB with freshest balance if changed
            bal = float(terminal_info.get("balance", user_acc.get("balance") or 0.0))
            eq = float(terminal_info.get("equity", bal))
            try:
                supabase.table("accounts").update({
                    "balance": bal,
                    "equity": eq,
                    "profit": float(terminal_info.get("profit", 0.0))
                }).eq("id", user_acc["id"]).execute()
            except Exception:
                pass

            return {
                **terminal_info,
                "id": user_acc["id"],
                "nickname": user_acc.get("nickname"),
                "broker": user_acc.get("broker"),
                "connected": True,
                "terminal_synced": True
            }
        else:
            # Terminal is either not logged in or logged into a different account
            return {
                "id": user_acc["id"],
                "nickname": user_acc.get("nickname"),
                "broker": user_acc.get("broker"),
                "login": user_acc.get("login"),
                "server": user_acc.get("server"),
                "balance": float(user_acc.get("balance") or 0.0),
                "equity": float(user_acc.get("equity") or 0.0),
                "profit": float(user_acc.get("profit") or 0.0),
                "currency": "USD",
                "connected": True,
                "terminal_synced": False,
                "warning": f"MT5 terminal is not synced with account #{user_login}"
            }
    except Exception as e:
        logger.error(f"Error fetching active account: {e}")
        return {"connected": False, "error": str(e), "balance": 0.0, "equity": 0.0}