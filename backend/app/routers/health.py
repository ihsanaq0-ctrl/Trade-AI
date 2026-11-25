import asyncio
import logging
from fastapi import APIRouter, Query, Depends
from app.services import metaapi_service as mt5
from app.middleware import get_optional_user
from app.database import supabase

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}


def _get_market_prices_sync() -> list:
    symbols = [
        "EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "AUDUSD", "USDCAD", "GBPJPY", "EURJPY",
        "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD", "BNBUSD", "DOGEUSD", "ADAUSD", "XAGUSD"
    ]
    result = []
    mod = mt5._ensure_mt5()
    for pair in symbols:
        resolved = mt5._resolve_symbol(pair)
        tick = mod.symbol_info_tick(resolved)
        s_info = mod.symbol_info(resolved)
        if tick:
            digits = s_info.digits if s_info else (
                3 if "JPY" in pair else (2 if any(c in pair for c in ["BTC", "ETH", "XAU", "XAG"]) else 5)
            )
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
    return result


@router.get("/api/markets/prices")
async def get_market_prices():
    """Fetch real-time prices from MT5 without blocking the event loop."""
    try:
        prices = await asyncio.to_thread(_get_market_prices_sync)
        return {"prices": prices}
    except Exception as e:
        logger.debug(f"Market prices fetch warning: {e}")
        return {"prices": []}


@router.get("/api/markets/candles")
async def get_candles(
    symbol: str = Query("EURUSD"),
    timeframe: str = Query("H1"),
    count: int = Query(100, le=500),
):
    """Fetch OHLCV candle data from MT5 for the chart."""
    try:
        clean_symbol = symbol.replace("/", "").replace(" ", "").strip().upper()
        candles = await asyncio.to_thread(mt5.get_candles_sync, clean_symbol, timeframe, count) if hasattr(mt5, "get_candles_sync") else await mt5.get_candles(clean_symbol, timeframe, count)
        return {"symbol": clean_symbol, "timeframe": timeframe, "candles": candles}
    except Exception as e:
        return {"error": str(e), "candles": []}


async def _bg_update_balance(account_id: str, bal: float, eq: float, profit: float):
    try:
        await asyncio.to_thread(
            lambda: supabase.table("accounts").update({
                "balance": bal,
                "equity": eq,
                "profit": profit,
            }).eq("id", account_id).execute()
        )
    except Exception:
        pass


@router.get("/api/markets/active-account")
async def get_active_account(user=Depends(get_optional_user)):
    """
    Get the currently connected broker account for the AUTHENTICATED user.
    Strictly scoped by user["sub"] and verifies terminal login ownership.
    """
    if not user or not user.get("sub"):
        return {"connected": False, "terminal_synced": False, "login": None, "balance": 0.0, "equity": 0.0}

    try:
        res, terminal_info = await asyncio.gather(
            asyncio.to_thread(
                lambda: supabase.table("accounts")
                .select("id, nickname, broker, login, server, balance, equity, profit, status, account_type")
                .eq("user_id", user["sub"])
                .eq("status", "connected")
                .limit(1)
                .execute()
            ),
            mt5.get_account_info(""),
        )

        if not res.data:
            return {"connected": False, "terminal_synced": False, "login": None, "balance": 0.0, "equity": 0.0}

        user_acc = res.data[0]
        user_login = str(user_acc.get("login", "")).strip()
        terminal_login = str(terminal_info.get("login", "")).strip() if terminal_info else ""

        # Only return live terminal metrics if MT5 Desktop is logged into THIS user's account!
        if terminal_login and terminal_login == user_login:
            bal = float(terminal_info.get("balance", user_acc.get("balance") or 0.0))
            eq = float(terminal_info.get("equity", bal))
            profit = float(terminal_info.get("profit", 0.0))

            # Non-blocking background sync ONLY if balance/equity actually moved
            prev_bal = float(user_acc.get("balance") or 0.0)
            prev_eq = float(user_acc.get("equity") or 0.0)
            if abs(bal - prev_bal) >= 0.01 or abs(eq - prev_eq) >= 0.01:
                asyncio.create_task(_bg_update_balance(user_acc["id"], bal, eq, profit))

            return {
                **terminal_info,
                "id": user_acc["id"],
                "nickname": user_acc.get("nickname"),
                "broker": user_acc.get("broker"),
                "account_type": user_acc.get("account_type"),
                "connected": True,
                "terminal_synced": True,
            }
        else:
            # Linked in DB, but MT5 Desktop is either closed or on a different account
            return {
                "id": user_acc["id"],
                "nickname": user_acc.get("nickname"),
                "broker": user_acc.get("broker"),
                "login": user_acc.get("login"),
                "server": user_acc.get("server"),
                "account_type": user_acc.get("account_type"),
                "balance": float(user_acc.get("balance") or 0.0),
                "equity": float(user_acc.get("equity") or 0.0),
                "profit": float(user_acc.get("profit") or 0.0),
                "currency": "USD",
                "connected": True,
                "terminal_synced": False,
                "warning": f"MT5 terminal is not currently logged into account #{user_login}",
            }
    except Exception as e:
        logger.error(f"Error fetching active account: {e}")
        return {"connected": False, "terminal_synced": False, "error": str(e), "balance": 0.0, "equity": 0.0}
