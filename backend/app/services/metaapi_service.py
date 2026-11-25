"""
Local MT5 connector (Path A — free, local terminal).
Uses the MetaTrader5 Python library connected to the local MT5 terminal.
"""

import asyncio
import pandas as pd
from datetime import datetime, timezone
from typing import Optional

# MT5 timeframe mapping — populated lazily from the actual module constants

_initialized = False
_symbol_cache = {}
_mt5_mod = None
_TIMEFRAMES = {}


def _ensure_mt5():
    global _initialized, _mt5_mod, _symbol_cache, _TIMEFRAMES
    if _initialized and _mt5_mod is not None:
        try:
            if _mt5_mod.terminal_info() is None:
                _initialized = False
        except Exception:
            _initialized = False

    if not _initialized:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
        # Build symbol cache on init
        _symbol_cache = {s.name: s.name for s in mt5.symbols_get() or []}
        # Build timeframe map from actual constants
        _TIMEFRAMES = {
            'M1': mt5.TIMEFRAME_M1,
            'M5': mt5.TIMEFRAME_M5,
            'M15': mt5.TIMEFRAME_M15,
            'M30': mt5.TIMEFRAME_M30,
            'H1': mt5.TIMEFRAME_H1,
            'H4': mt5.TIMEFRAME_H4,
            'D1': mt5.TIMEFRAME_D1,
            'W1': mt5.TIMEFRAME_W1,
            'MN1': mt5.TIMEFRAME_MN1,
        }
        _mt5_mod = mt5
        _initialized = True
    return _mt5_mod


def _refresh_symbol_cache():
    """Re-sync the symbol cache with the terminal's Market Watch.

    symbols_get() only returns what's in Market Watch, and the user may add a
    symbol (e.g. XAUUSDm) while the backend runs — the one-time init cache would
    never see it, so the bot loops on 'no candle data' forever for that pair.
    """
    global _symbol_cache
    try:
        if _mt5_mod is not None:
            _symbol_cache = {s.name: s.name for s in _mt5_mod.symbols_get() or []}
    except Exception as e:

        import logging; logging.getLogger(__name__).error(f'Database operation failed: {e}')


def _ensure_symbol_visible(pair: str) -> str:
    """
    Resolve a configured pair to a real broker symbol AND make sure it is in
    Market Watch (symbol_select). Without this, copy_rates_from_pos /
    symbol_info_tick return None for any symbol not in the watchlist — the
    'XAUUSD never trades while EURUSD works' root cause.
    Returns the resolved symbol (best effort) or the pair unchanged.
    """
    if not _mt5_mod:
        return pair
    # Try direct match first
    resolved = _resolve_symbol(pair)
    if resolved != pair:
        _mt5_mod.symbol_select(resolved, True)
        return resolved
    # Not resolvable from current cache — refresh once, then retry
    _refresh_symbol_cache()
    resolved = _resolve_symbol(pair)
    if resolved != pair:
        _mt5_mod.symbol_select(resolved, True)
    return resolved


def _normalize_symbol(sym: str) -> str:
    """Strip broker suffixes/dots for matching: 'XAUUSDm' -> 'XAUUSD', 'EURUSD.fx' -> 'EURUSD'."""
    return (sym or '').upper().replace('.', '').replace('-', '')


def _resolve_symbol(pair: str) -> str:
    """
    Find the correct symbol name on this broker, with fallback.

    Handles BOTH directions:
      - configured 'XAUUSD'  -> broker 'XAUUSDm' / 'XAUUSDc' / 'XAUUSD.fx'
      - configured 'XAUUSDm' -> broker 'XAUUSD'  (user typed the suffixed name)
    Previously only tried pair+suffix against the cache, so a suffixed config
    (or a broker with an unusual suffix) resolved to a symbol MT5 cannot find —
    the order silently failed or the bot looped on 'insufficient candle data'.
    """
    # 1. Direct match (case-insensitive)
    for name in _symbol_cache:
        if name.upper() == pair.upper():
            return name

    # 2. Broker suffix variants of the configured pair
    for suffix in ['m', '.c', '.ecn', 'pro', '.fx', '.n', 'a', 'b']:
        candidate = pair + suffix
        for name in _symbol_cache:
            if name.upper() == candidate.upper():
                return name

    # 3. Reverse: configured pair already carries a suffix, broker has the base
    base = _normalize_symbol(pair)
    for name in _symbol_cache:
        if _normalize_symbol(name) == base:
            return name

    # 4. Partial-suffix match: broker has e.g. XAUUSD with a different suffix
    for name in _symbol_cache:
        if _normalize_symbol(name).startswith(base):
            return name

    return pair


async def connect(login: str, password: str, server: str) -> str:
    """Connect to broker via local MT5 terminal."""
    # The terminal already handles login — this just verifies we can reach it
    mt5 = _ensure_mt5()
    info = mt5.account_info()
    if info:
        return str(info.login)
    raise RuntimeError("No MT5 account logged in")


async def get_account_info(account_id: str) -> dict:
    """Get account balance, equity, etc. from local MT5."""
    mt5 = _ensure_mt5()
    info = mt5.account_info()
    if not info:
        return {"balance": 0, "equity": 0, "currency": "USD"}
    return {
        "balance": info.balance,
        "equity": info.equity,
        "currency": info.currency,
        "login": info.login,
        "server": info.server,
        "leverage": info.leverage,
        "profit": info.profit,
        "margin": info.margin,
        "margin_free": info.margin_free,
    }


async def get_positions(account_id: str) -> list:
    """Get open positions from local MT5 without blocking the event loop."""
    def _get_sync():
        mt5 = _ensure_mt5()
        positions = mt5.positions_get()
        if not positions:
            return []
        result = []
        for p in positions:
            result.append({
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": "BUY" if p.type == 0 else "SELL",
                "volume": p.volume,
                "open_price": p.price_open,
                "current_price": p.price_current,
                "stop_loss": p.sl,
                "take_profit": p.tp,
                "profit": round(float(p.profit), 2),
                "swap": round(float(p.swap), 2),
                "comment": getattr(p, "comment", ""),
                "magic": getattr(p, "magic", 0),
                "time": datetime.fromtimestamp(p.time, tz=timezone.utc).isoformat(),
            })
        return result

    return await asyncio.to_thread(_get_sync)


async def get_candles(pair: str, timeframe: str, count: int = 100) -> list:
    """Get OHLCV candle data from local MT5."""
    mt5 = _ensure_mt5()
    # Ensure the symbol is in Market Watch (refresh cache + symbol_select) —
    # otherwise gold/crypto pairs not pre-added to the watchlist return None
    # forever and the bot never trades.
    symbol = _ensure_symbol_visible(pair)
    tf = _TIMEFRAMES.get(timeframe, _TIMEFRAMES.get('H1', 16385))
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    if rates is None or len(rates) == 0:
        return []
    df = pd.DataFrame(rates)
    candles = []
    for _, r in df.iterrows():
        candles.append({
            # CRITICAL: MT5 timestamps are UTC epoch seconds. datetime.fromtimestamp
            # (no tz) produced NAIVE LOCAL time — on a UTC+5 machine the strategies
            # then mislabeled it as UTC, shifting Kill Zones by 5 hours so the bots
            # NEVER fired during real London/NY sessions. Always convert as UTC.
            "time": datetime.fromtimestamp(r.time, tz=timezone.utc).isoformat(),
            "open": round(r.open, 5),
            "high": round(r.high, 5),
            "low": round(r.low, 5),
            "close": round(r.close, 5),
            "volume": int(r.tick_volume),
        })
    return candles


# MT5 trade retcodes → human-readable labels. Only codes we can verify are
# correct are included (MetaTrader5 trade server return codes); anything not
# listed stays a raw numeric code in the log rather than a guessed label.
RETCODE_LABELS = {
    10004: "Requote",
    10006: "Request rejected",
    10007: "Request canceled by trader",
    10011: "Request processing error",
    10012: "Request canceled by expiration",
    10013: "Invalid request",
    10014: "Invalid volume in request",
    10015: "Invalid price in request",
    10016: "Invalid stops (SL/TP) in request",
    10017: "Trade is disabled",
    10018: "Market closed",
    10019: "No money (insufficient funds)",
    10020: "Prices changed",
    10021: "Invalid price / no quotes",
    10024: "Too frequent requests",
    10026: "Autotrading disabled by broker/server",
    10027: "Algo Trading is disabled in MT5 terminal. Please enable the 'Algo Trading' button (Ctrl+E) in MetaTrader 5.",
    10028: "Request locked for processing",
    10029: "Order or position frozen",
    10030: "Unsupported filling mode",
    10031: "No connection with trade server",
}


def _retcode_message(retcode: int) -> str:
    """Human-readable message for an MT5 order_send retcode, e.g. 'Retcode: 10018 (Market closed)'."""
    label = RETCODE_LABELS.get(retcode)
    return f"Retcode: {retcode} ({label})" if label else f"Retcode: {retcode}"


async def place_order(account_id: str, pair: str, order_type: str, volume: float,
                      stop_loss: float = None, take_profit: float = None,
                      comment: str = "TradeAI Bot") -> dict:
    """Place a market order via local MT5 terminal."""
    mt5 = _ensure_mt5()

    # Pre-flight check terminal permissions
    t_info = mt5.terminal_info()
    if t_info:
        if not t_info.trade_allowed:
            return {
                "success": False,
                "error": "Algo Trading is disabled in your MetaTrader 5 terminal. In MT5, click 'Algo Trading' in the top toolbar (or press Ctrl+E) to allow order execution."
            }
        if t_info.tradeapi_disabled:
            return {
                "success": False,
                "error": "External Python API trading is disabled in MetaTrader 5. Go to Tools > Options > Expert Advisors and ensure external API trading is enabled."
            }

    # Pre-flight check account trading permissions
    a_info = mt5.account_info()
    if a_info and not a_info.trade_allowed:
        return {
            "success": False,
            "error": "Trading is disabled for this account by your broker (or an investor read-only password is in use)."
        }

    symbol = _ensure_symbol_visible(pair)
    mt5_type = mt5.ORDER_TYPE_BUY if order_type.upper() == "BUY" else mt5.ORDER_TYPE_SELL

    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        return {"success": False, "error": f"Symbol {pair} (resolved: {symbol}) not found"}

    if not symbol_info.trade_mode == mt5.SYMBOL_TRADE_MODE_FULL:
        return {"success": False, "error": f"Trading not allowed for {pair}"}

    # symbol_info_tick can return None (weekend, market closed, symbol not in
    # Market Watch) — accessing .ask/.bid on None crashes the whole bot loop.
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return {"success": False, "error": f"No tick data for {symbol} (market closed or not in Market Watch)"}
    price = tick.ask if mt5_type == mt5.ORDER_TYPE_BUY else tick.bid

    # Detect supported filling mode from symbol_info
    filling = mt5.ORDER_FILLING_IOC
    if hasattr(symbol_info, "filling_mode") and symbol_info.filling_mode:
        if symbol_info.filling_mode & 2:
            filling = mt5.ORDER_FILLING_IOC
        elif symbol_info.filling_mode & 1:
            filling = mt5.ORDER_FILLING_FOK
        else:
            filling = mt5.ORDER_FILLING_RETURN

    magic_num = 234001 if "manual" in comment.lower() else 234000

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(volume),
        "type": mt5_type,
        "price": price,
        "sl": float(stop_loss) if stop_loss else 0.0,
        "tp": float(take_profit) if take_profit else 0.0,
        "deviation": 10,
        "magic": magic_num,
        "comment": comment[:31],
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling,
    }

    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        return {"ticket": result.order, "success": True, "price": price}

    # If rejected due to filling mode (10030), retry with alternative filling modes
    if result and result.retcode == 10030:
        for alt_fill in [mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN, mt5.ORDER_FILLING_IOC]:
            if alt_fill != filling:
                request["type_filling"] = alt_fill
                retry_res = mt5.order_send(request)
                if retry_res and retry_res.retcode == mt5.TRADE_RETCODE_DONE:
                    return {"ticket": retry_res.order, "success": True, "price": price}

    error = mt5.last_error() if result is None else _retcode_message(result.retcode)
    return {"success": False, "error": str(error)}


async def close_position(account_id: str, position_id: str) -> dict:
    """Close an open position by ticket number."""
    mt5 = _ensure_mt5()
    position = mt5.positions_get(ticket=int(position_id))
    if not position or len(position) == 0:
        return {"success": False, "error": "Position not found"}
    pos = position[0]

    close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
    tick = mt5.symbol_info_tick(pos.symbol)
    if tick is None:
        return {"success": False, "error": f"No tick data for {pos.symbol} (market closed)"}
    price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask

    # Detect supported filling mode from symbol_info
    symbol_info = mt5.symbol_info(pos.symbol)
    filling = mt5.ORDER_FILLING_IOC
    if symbol_info and hasattr(symbol_info, "filling_mode") and symbol_info.filling_mode:
        if symbol_info.filling_mode & 2:
            filling = mt5.ORDER_FILLING_IOC
        elif symbol_info.filling_mode & 1:
            filling = mt5.ORDER_FILLING_FOK
        else:
            filling = mt5.ORDER_FILLING_RETURN

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": pos.symbol,
        "volume": pos.volume,
        "type": close_type,
        "position": pos.ticket,
        "price": price,
        "deviation": 10,
        "magic": 234000,
        "comment": "TradeAI Close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling,
    }

    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        return {"success": True, "price": price}

    # If rejected due to filling mode (10030), retry with alternative filling modes
    if result and result.retcode == 10030:
        for alt_fill in [mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN, mt5.ORDER_FILLING_IOC]:
            if alt_fill != filling:
                request["type_filling"] = alt_fill
                retry_res = mt5.order_send(request)
                if retry_res and retry_res.retcode == mt5.TRADE_RETCODE_DONE:
                    return {"success": True, "price": price}

    # result can be None — branch like place_order does instead of crashing
    error = mt5.last_error() if result is None else _retcode_message(result.retcode)
    return {"success": False, "error": str(error)}



async def partial_close_position(account_id: str, position_id: str, close_pct: float) -> dict:
    """Close a percentage (0 < close_pct <= 1) of an open position via MT5."""
    if not close_pct or close_pct <= 0 or close_pct > 1:
        return {"success": False, "error": "close_pct must be in (0, 1]"}
    mt5 = _ensure_mt5()
    position = mt5.positions_get(ticket=int(position_id))
    if not position or len(position) == 0:
        return {"success": False, "error": "Position not found"}
    pos = position[0]

    close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
    tick = mt5.symbol_info_tick(pos.symbol)
    if tick is None:
        return {"success": False, "error": f"No tick data for {pos.symbol} (market closed)"}
    price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask

    close_volume = round(pos.volume * close_pct, 2)
    if close_volume <= 0:
        return {"success": False, "error": "Computed close volume is zero"}

    symbol_info = mt5.symbol_info(pos.symbol)
    filling = mt5.ORDER_FILLING_IOC
    if symbol_info and hasattr(symbol_info, "filling_mode") and symbol_info.filling_mode:
        if symbol_info.filling_mode & 2:
            filling = mt5.ORDER_FILLING_IOC
        elif symbol_info.filling_mode & 1:
            filling = mt5.ORDER_FILLING_FOK
        else:
            filling = mt5.ORDER_FILLING_RETURN

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": pos.symbol,
        "volume": close_volume,
        "type": close_type,
        "position": pos.ticket,
        "price": price,
        "deviation": 10,
        "magic": 234000,
        "comment": "TradeAI Partial Close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling,
    }

    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        return {"success": True, "price": price, "closed_volume": close_volume}

    if result and result.retcode == 10030:
        for alt_fill in [mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN, mt5.ORDER_FILLING_IOC]:
            if alt_fill != filling:
                request["type_filling"] = alt_fill
                retry_res = mt5.order_send(request)
                if retry_res and retry_res.retcode == mt5.TRADE_RETCODE_DONE:
                    return {"success": True, "price": price, "closed_volume": close_volume}

    error = mt5.last_error() if result is None else _retcode_message(result.retcode)
    return {"success": False, "error": str(error)}

async def modify_sl_tp(account_id: str, position_id: str,
                        stop_loss: float = None, take_profit: float = None) -> dict:
    """Modify stop loss and/or take profit on an open position."""
    mt5 = _ensure_mt5()
    position = mt5.positions_get(ticket=int(position_id))
    if not position or len(position) == 0:
        return {"success": False, "error": "Position not found"}
    pos = position[0]

    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": pos.symbol,
        "position": pos.ticket,
        "sl": float(stop_loss) if stop_loss is not None else pos.sl,
        "tp": float(take_profit) if take_profit is not None else pos.tp,
    }

    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        return {"success": True, "ticket": pos.ticket, "new_sl": stop_loss, "new_tp": take_profit}
    error = mt5.last_error() if result is None else _retcode_message(result.retcode)
    return {"success": False, "error": str(error)}


async def disconnect(account_id: str):
    """Shutdown MT5 connection."""
    global _initialized
    if _initialized and _mt5_mod:
        _mt5_mod.shutdown()
        _initialized = False

async def get_history_deal_profit(ticket: int) -> float:
    """Get the total profit of a closed position by its position ticket."""
    mt5 = _ensure_mt5()
    
    # We must provide a time range. We can just use the beginning of time to now, 
    # but the API allows passing position=ticket instead.
    deals = mt5.history_deals_get(position=ticket)
    if not deals:
        return 0.0
        
    total_profit = sum(d.profit for d in deals)
    return float(total_profit)


async def get_history_deal_reason(position_ticket: int) -> int:
    """Get the DEAL_REASON of the deal that closed a position (e.g. DEAL_REASON_SL = 4)."""
    mt5 = _ensure_mt5()
    deals = mt5.history_deals_get(position=int(position_ticket))
    if not deals:
        return -1
    for d in reversed(deals):
        # Entry OUT or OUT_BY is the closing deal
        if getattr(d, 'entry', None) in (mt5.DEAL_ENTRY_OUT, getattr(mt5, 'DEAL_ENTRY_OUT_BY', 1)):
            return int(getattr(d, 'reason', -1))
    return -1


async def place_pending_order(account_id: str, pair: str, order_type: str, volume: float,
                              price: float, stop_loss: float = 0.0, take_profit: float = 0.0,
                              magic: int = 26110401, comment: str = "PIPSTEP") -> dict:
    """Place a pending stop/limit order (e.g. BUY_STOP, SELL_STOP) via local MT5 terminal."""
    mt5 = _ensure_mt5()

    symbol = _ensure_symbol_visible(pair)
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        return {"success": False, "error": f"Symbol {pair} not found"}

    ot_str = order_type.upper().replace(" ", "_")
    if ot_str in ("BUY_STOP", "BUYSTOP"):
        mt5_type = mt5.ORDER_TYPE_BUY_STOP
    elif ot_str in ("SELL_STOP", "SELLSTOP"):
        mt5_type = mt5.ORDER_TYPE_SELL_STOP
    elif ot_str in ("BUY_LIMIT", "BUYLIMIT"):
        mt5_type = mt5.ORDER_TYPE_BUY_LIMIT
    elif ot_str in ("SELL_LIMIT", "SELLLIMIT"):
        mt5_type = mt5.ORDER_TYPE_SELL_LIMIT
    else:
        return {"success": False, "error": f"Unsupported pending order type: {order_type}"}

    filling = mt5.ORDER_FILLING_RETURN
    if hasattr(symbol_info, "filling_mode") and symbol_info.filling_mode:
        if symbol_info.filling_mode & 2:
            filling = mt5.ORDER_FILLING_IOC
        elif symbol_info.filling_mode & 1:
            filling = mt5.ORDER_FILLING_FOK

    request = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": symbol,
        "volume": float(volume),
        "type": mt5_type,
        "price": float(price),
        "sl": float(stop_loss) if stop_loss else 0.0,
        "tp": float(take_profit) if take_profit else 0.0,
        "deviation": 10,
        "magic": int(magic),
        "comment": comment[:31],
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling,
    }

    result = mt5.order_send(request)
    if result and result.retcode in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_PLACED):
        return {"ticket": result.order, "success": True, "price": price}

    # Retry if filling mode rejected
    if result and result.retcode == 10030:
        for alt_fill in [mt5.ORDER_FILLING_RETURN, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK]:
            if alt_fill != filling:
                request["type_filling"] = alt_fill
                retry_res = mt5.order_send(request)
                if retry_res and retry_res.retcode in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_PLACED):
                    return {"ticket": retry_res.order, "success": True, "price": price}

    error = mt5.last_error() if result is None else _retcode_message(result.retcode)
    return {"success": False, "error": str(error)}


async def delete_pending_order(ticket: int) -> dict:
    """Delete a pending order by its ticket number."""
    mt5 = _ensure_mt5()
    request = {
        "action": mt5.TRADE_ACTION_REMOVE,
        "order": int(ticket),
    }
    result = mt5.order_send(request)
    if result and result.retcode in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_PLACED):
        return {"success": True, "ticket": int(ticket)}
    error = mt5.last_error() if result is None else _retcode_message(result.retcode)
    return {"success": False, "error": str(error)}


async def get_pending_orders(symbol: str = None, magic: int = None) -> list:
    """Get active pending orders for a symbol and/or magic number."""
    mt5 = _ensure_mt5()
    orders = mt5.orders_get(symbol=symbol) if symbol else mt5.orders_get()
    if not orders:
        return []
    out = []
    for o in orders:
        if magic is not None and getattr(o, "magic", None) != magic:
            continue
        ot = getattr(o, "type", None)
        type_str = "BUY_STOP" if ot == mt5.ORDER_TYPE_BUY_STOP else \
                   "SELL_STOP" if ot == mt5.ORDER_TYPE_SELL_STOP else \
                   "BUY_LIMIT" if ot == mt5.ORDER_TYPE_BUY_LIMIT else \
                   "SELL_LIMIT" if ot == mt5.ORDER_TYPE_SELL_LIMIT else str(ot)
        out.append({
            "ticket": o.ticket,
            "symbol": o.symbol,
            "type": type_str,
            "volume": o.volume_current,
            "price_open": o.price_open,
            "sl": o.sl,
            "tp": o.tp,
            "magic": o.magic,
            "comment": getattr(o, "comment", ""),
        })
    return out
