from fastapi import APIRouter, Query
from app.services import metaapi_service as mt5

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
async def get_active_account():
    """Get the currently logged-in MT5 account info."""
    try:
        info = await mt5.get_account_info('')
        return info
    except Exception as e:
        return {"error": str(e)}