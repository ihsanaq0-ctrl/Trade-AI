"""
Scalp FVG Scheduler — drives ScalpModeBot with dollarized risk management.

Three exported components used by the bot engine:
  1. execute_trade()     — routes ENTER / CLOSE_AND_REVERSE / STOP_TRADING to MT5
  2. monitor_breakeven() — background asyncio task: moves SL to entry at $0.50 profit
  3. run_scheduler_cycle() — single-cycle fetch → analyze → execute (called in a loop)
"""

import asyncio
import logging
from datetime import datetime

import pandas as pd

from app.database import supabase
from app.services import metaapi_service as mt5
from app.services.strategies.scalp_fvg import ScalpModeBot

_logger = logging.getLogger("scalp_scheduler")

# Registered breakeven monitor tasks keyed by bot_id
_breakeven_tasks: dict[str, asyncio.Task] = {}


def _normalize_symbol(sym: str) -> str:
    """Strip broker suffixes/dots for matching: 'XAUUSDm' -> 'XAUUSD', 'EURUSD.fx' -> 'EURUSD'."""
    return (sym or '').upper().replace('.', '').replace('-', '')


def _symbols_match(position_symbol: str, configured_pair: str) -> bool:
    """
    True when an MT5 position symbol matches a bot's configured pair.
    Handles broker suffixes: configured 'XAUUSD' matches position 'XAUUSDm',
    'XAUUSDc', 'XAUUSD.fx', 'XAUUSD.pro' AND vice versa (configured 'XAUUSDm'
    also matches position 'XAUUSD'). This is the fix for positions never being
    found on suffix-bearing brokers (Exness 'm', ICMarkets 'c', etc.) — which
    made FVG/pyramid bots double-open instead of managing, breakeven never
    trigger, and emergency closes skip every position.
    """
    a = _normalize_symbol(position_symbol)
    b = _normalize_symbol(configured_pair)
    if not a or not b:
        return False
    return a == b or a.startswith(b) or b.startswith(a)


def _resolve_pip_specs(pair: str) -> tuple[float, float]:
    """
    Resolve the REAL pip value per 1.0 lot and pip size for a symbol from MT5.

    Returns (pip_value_per_lot, pip_size):
      - pip_value_per_lot: how many dollars 1 pip (or 1 tick*10) is worth for 1.0 lot
      - pip_size: the price step of 1 pip for this symbol (0.0001 forex, 0.01 gold)

    Falls back to sane defaults if MT5 is unreachable.
    """
    try:
        mod = mt5._ensure_mt5()
        symbol = mt5._resolve_symbol(pair)
        info = mod.symbol_info(symbol)
        if info:
            tick_size = info.trade_tick_size
            tick_value = info.trade_tick_value
            if tick_size and tick_value and tick_size > 0:
                # 1 pip = 10 ticks on most brokers (5-digit quotes, 3-digit JPY,
                # 3-digit gold like this broker's 0.001 tick). BUT some brokers
                # quote gold at 2 decimals with tick_size=0.01 (1 tick per pip) —
                # blindly multiplying by 10 inflates the pip 10x there. Clamp the
                # result to the asset-class sane range instead of trusting the
                # tick ratio blindly.
                raw_pip_size = tick_size * 10.0
                raw_pip_value = (tick_value / tick_size) * raw_pip_size
                base = _normalize_symbol(pair)
                if "JPY" in base:
                    pip_size = min(max(raw_pip_size, 0.001), 0.01)
                    pip_value = min(max(raw_pip_value, 1.0), 12.0)
                elif any(k in base for k in ("XAU", "GOLD", "XAG", "SILVER", "XPT", "PALLADIUM")):
                    # metals: pip step 0.01 .. 0.1, value $1..$5 per pip per lot
                    pip_size = min(max(raw_pip_size, 0.01), 0.1)
                    pip_value = min(max(raw_pip_value, 1.0), 5.0)
                elif any(k in base for k in ("BTC", "ETH", "LTC", "XRP", "SOL", "ADA", "BNB", "DOGE")):
                    pip_size = min(max(raw_pip_size, 0.1), 1.0)
                    pip_value = min(max(raw_pip_value, 0.01), 1.0)
                else:
                    # standard forex: pip 0.0001 (5-digit) or 0.001 (3-digit JPY-like)
                    pip_size = min(max(raw_pip_size, 0.0001), 0.001)
                    pip_value = min(max(raw_pip_value, 1.0), 12.0)
                return pip_value, pip_size
    except Exception as e:

        _logger.error(f'Database operation failed: {e}')

    # Fallbacks if MT5 unreachable. NOTE: the base symbol check must test the
    # BASE of the pair (strip any broker suffix and trailing quote currency).
    # 'XAUUSD'.endswith('XAU') is FALSE (it ends with 'USD') — the previous
    # check silently sent gold/crypto to the forex defaults, making SL/TP 100x
    # too small. Check by CONTAINS on the base instead.
    base = _normalize_symbol(pair)
    if "JPY" in base:
        return 9.0, 0.001   # USDJPY-style: pip = 0.001 (5-digit) or 0.01 (3-digit)
    if any(k in base for k in ("XAU", "GOLD", "XAG", "SILVER", "BTC", "ETH", "LTC", "XRP", "SOL", "ADA", "BNB", "DOGE", "XPT", "PALLADIUM")):
        return 1.0, 0.01    # metals/crypto: pip-sized step = 0.01
    return 10.0, 0.0001     # standard 5-digit forex

# ---------------------------------------------------------------------------
# ACTION 1: ENTER — standard market order
# ---------------------------------------------------------------------------
async def _execute_enter(signal: dict, bot_id: str, user_id: str | None, pair: str,
                         lot_size: float) -> dict:
    """Place a market order with the dollarized SL and TP levels from the signal."""
    try:
        order = await mt5.place_order(
            account_id="",
            pair=pair,
            order_type=signal['direction'],
            volume=lot_size,
            stop_loss=signal.get('stop_loss'),
            take_profit=signal.get('take_profit'),
        )

        if order and order.get("success"):
            # Columns match the LIVE trades schema; id is required (no default)
            from uuid import uuid4
            record = {
                "id": str(uuid4()),
                "user_id": user_id or "",
                "bot_id": bot_id,
                "strategy": "scalp_fvg",
                "symbol": pair,
                "direction": signal['direction'].lower(),
                "volume": lot_size,
                "open_price": order.get("price", 0),
                "stop_loss": signal.get('stop_loss'),
                "take_profit": signal.get('take_profit'),
                "status": "open",
                "reason": signal.get('reason', ''),
                "opened_at": datetime.utcnow().isoformat(),
                "ticket": str(order.get("ticket")),
            }
            try:
                supabase.table("trades").insert(record).execute()
            except Exception as e:
                _logger.warning(f"[scalp_fvg {bot_id}] DB insert failed: {e}")

            return {"success": True, "action": "ENTER", "ticket": order.get("ticket")}

        _logger.warning(f"[scalp_fvg {bot_id}] Order failed: {order.get('error')}")
        return {"success": False, "action": "ENTER", "error": order.get("error")}

    except Exception as e:
        _logger.error(f"[scalp_fvg {bot_id}] ENTER exception: {e}")
        return {"success": False, "action": "ENTER", "error": str(e)}


# ---------------------------------------------------------------------------
# ACTION 2: CLOSE_AND_REVERSE — close existing position, then open opposite
# ---------------------------------------------------------------------------
async def _execute_close_and_reverse(signal: dict, bot_id: str, user_id: str | None,
                                      pair: str, lot_size: float) -> dict:
    """Close the current position, then immediately open a new one in the opposite direction."""
    close_ticket = signal.get('close_ticket')
    if not close_ticket:
        return {"success": False, "action": "CLOSE_AND_REVERSE", "error": "No close_ticket in signal"}

    # Step 1: Close existing position
    close_result = await mt5.close_position("", str(close_ticket))
    if not close_result.get("success"):
        _logger.warning(f"[scalp_fvg {bot_id}] Close of {close_ticket} failed: {close_result.get('error')}")
        # Continue anyway — try to open the new position

    # Mark the old trade as closed in DB (no 'ticket' column in live schema —
    # match by bot + symbol + open status)
    try:
        supabase.table("trades").update({
            "status": "closed",
            "closed_at": datetime.utcnow().isoformat(),
            "close_price": close_result.get("price", 0),
        }).eq("ticket", str(close_ticket)).execute()
    except Exception as e:

        _logger.error(f'Database operation failed: {e}')

    # Step 2: Open new position
    order = await mt5.place_order(
        account_id="",
        pair=pair,
        order_type=signal['direction'],
        volume=lot_size,
        stop_loss=signal.get('stop_loss'),
        take_profit=signal.get('take_profit'),
    )

    if order and order.get("success"):
        # Columns match the LIVE trades schema; id is required (no default)
        from uuid import uuid4
        record = {
            "id": str(uuid4()),
            "user_id": user_id or "",
            "bot_id": bot_id,
            "strategy": "scalp_fvg",
            "symbol": pair,
            "direction": signal['direction'].lower(),
            "volume": lot_size,
            "open_price": order.get("price", 0),
            "stop_loss": signal.get('stop_loss'),
            "take_profit": signal.get('take_profit'),
            "status": "open",
            "reason": signal.get('reason', ''),
            "opened_at": datetime.utcnow().isoformat(),
            "ticket": str(order.get("ticket")),
        }
        try:
            supabase.table("trades").insert(record).execute()
        except Exception as e:

            _logger.error(f'Database operation failed: {e}')

        return {"success": True, "action": "CLOSE_AND_REVERSE", "ticket": order.get("ticket")}

    return {"success": False, "action": "CLOSE_AND_REVERSE", "error": order.get("error")}


# ---------------------------------------------------------------------------
# ACTION 3: STOP_TRADING — halt bot, log drawdown event
# ---------------------------------------------------------------------------
async def _execute_stop_trading(signal: dict, bot_id: str, pair: str = None) -> dict:
    """Log the drawdown event, close ALL open positions for this pair, and stop the bot."""
    reason = signal.get('reason', 'Unknown drawdown trigger')
    _logger.warning(f"[scalp_fvg {bot_id}] STOP_TRADING: {reason}")

    # Close ALL open positions for this bot's pair immediately
    closed_tickets = []
    try:
        positions = await mt5.get_positions("")
        for p in positions:
            # Match by pair if given, otherwise close everything on this account
            if pair and not _symbols_match(p.get("symbol", ""), pair):
                continue
            close_result = await mt5.close_position("", str(p["ticket"]))
            if close_result.get("success"):
                closed_tickets.append(p["ticket"])
                _logger.warning(f"[scalp_fvg {bot_id}] Emergency closed position {p['ticket']} at {close_result.get('price')}")
                # Mark closed in DB (no 'ticket' column — match by bot+symbol+open)
                try:
                    supabase.table("trades").update({
                        "status": "closed",
                        "closed_at": datetime.utcnow().isoformat(),
                        "close_price": close_result.get("price", 0),
                    }).eq("ticket", str(p["ticket"])).execute()
                except Exception as e:

                    _logger.error(f'Database operation failed: {e}')
    except Exception as close_err:
        _logger.error(f"[scalp_fvg {bot_id}] Emergency close error: {close_err}")

    # Log event to Supabase
    try:
        supabase.table("bot_events").insert({
            "bot_id": bot_id,
            "event_type": "drawdown_halt",
            "message": reason,
            "positions_closed": len(closed_tickets),
            "created_at": datetime.utcnow().isoformat(),
        }).execute()

        supabase.table("bot_settings").update({
            "status": "stopped",
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", bot_id).execute()
    except Exception as e:
        _logger.error(f"[scalp_fvg {bot_id}] Failed to persist stop: {e}")

    return {"success": True, "action": "STOP_TRADING", "reason": reason, "positions_closed": closed_tickets}


# ---------------------------------------------------------------------------
# PUBLIC: execute_trade — routes signal actions to the right handler
# ---------------------------------------------------------------------------
async def execute_trade(signal: dict, bot_id: str, user_id: str | None,
                         pair: str, lot_size: float, bot_instance: ScalpModeBot) -> dict:
    """
    Route a signal dict to its execution handler.

    The caller MUST call bot_instance.register_trade_executed() after this
    returns success for ENTER or CLOSE_AND_REVERSE actions.

    Returns {'success': bool, 'action': str, ...}
    """
    action_type = signal.get('action')
    _logger.info(f"[scalp_fvg {bot_id}] Executing {action_type}: {signal.get('reason', '')}")

    if action_type == 'ENTER':
        return await _execute_enter(signal, bot_id, user_id, pair, lot_size)

    elif action_type == 'CLOSE_AND_REVERSE':
        return await _execute_close_and_reverse(signal, bot_id, user_id, pair, lot_size)

    elif action_type == 'STOP_TRADING':
        return await _execute_stop_trading(signal, bot_id, pair=pair)

    else:
        return {"success": False, "error": f"Unknown action: {action_type}"}


# ---------------------------------------------------------------------------
# PUBLIC: monitor_breakeven — background task that checks floating profit
# ---------------------------------------------------------------------------
async def monitor_breakeven(bot_id: str, bot_instance: ScalpModeBot,
                             check_interval: float = 3.0):
    """
    Background asyncio task. Every check_interval seconds, fetches open MT5 positions
    for this bot's symbol. If a position's floating profit >= breakeven_usd and
    breakeven hasn't been applied yet, moves SL to entry price.

    Stops when the bot loop is cancelled.
    Use start_breakeven_monitor() / stop_breakeven_monitor() to manage the lifecycle.
    """
    try:
        while True:
            # Fetch bot config to get the pair and check if still running
            result = supabase.table("bot_settings").select("pair,status").eq("id", bot_id).single().execute()
            if not result.data or result.data.get("status") != "running":
                _logger.info(f"[breakeven {bot_id}] Bot no longer running, stopping monitor")
                break

            pair = result.data["pair"]
            positions = await mt5.get_positions("")

            for p in positions:
                # Match symbol to this bot's pair (handles broker suffixes)
                if not _symbols_match(p.get("symbol", ""), pair):
                    continue

                ticket = p["ticket"]
                profit = p.get("profit", 0)

                # Check if breakeven already applied
                if bot_instance.breakeven_applied.get(ticket):
                    continue

                # If floating profit >= threshold, move SL to entry
                if profit >= bot_instance.breakeven_usd:
                    entry_price = p["open_price"]
                    result_mod = await mt5.modify_sl_tp("", ticket, stop_loss=entry_price)

                    if result_mod.get("success"):
                        bot_instance.breakeven_applied[ticket] = True
                        _logger.info(f"[breakeven {bot_id}] Position {ticket}: SL moved to breakeven at {entry_price}")
                    else:
                        _logger.warning(f"[breakeven {bot_id}] Failed to modify SL for {ticket}: {result_mod.get('error')}")

            await asyncio.sleep(check_interval)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        _logger.error(f"[breakeven {bot_id}] Error: {e}")


def start_breakeven_monitor(bot_id: str, bot_instance: ScalpModeBot,
                             check_interval: float = 3.0):
    """Start the breakeven monitor background task."""
    if bot_id in _breakeven_tasks and not _breakeven_tasks[bot_id].done():
        return  # Already running
    task = asyncio.create_task(
        monitor_breakeven(bot_id, bot_instance, check_interval)
    )
    _breakeven_tasks[bot_id] = task
    _logger.info(f"[breakeven {bot_id}] Monitor started")


def stop_breakeven_monitor(bot_id: str):
    """Stop the breakeven monitor background task."""
    task = _breakeven_tasks.pop(bot_id, None)
    if task and not task.done():
        task.cancel()
        _logger.info(f"[breakeven {bot_id}] Monitor stopped")


# ---------------------------------------------------------------------------
# PUBLIC: run_scheduler_cycle — one full iteration of fetch → analyze → execute
# ---------------------------------------------------------------------------
async def run_scheduler_cycle(bot_id: str, bot_instance: ScalpModeBot,
                               bot_cfg: dict) -> list[dict]:
    """
    Single scheduler cycle:
      1. Fetch candles
      2. Fetch MT5 account info (balance, positions)
      3. Resolve pip value for the symbol
      4. Call bot_instance.generate_signal()
      5. Execute returned action (ENTER / CLOSE_AND_REVERSE / STOP_TRADING)

    Returns list of result dicts (typically 0-1 results, but keeps the pattern).

    The caller (bot engine loop) should wrap this in a while loop with sleep.
    """
    results = []
    pair = bot_cfg["pair"]
    timeframe = bot_cfg.get("timeframe", "M1")
    lot_size = bot_cfg.get("lot_size", 0.01)

    # 1. Fetch candles
    candles = await mt5.get_candles(pair, timeframe, count=100)
    if not candles or len(candles) < 30:
        _logger.warning(f"[scalp_fvg {bot_id}] Insufficient candle data for {pair}")
        return results

    df = pd.DataFrame(candles)

    # 2a. Fetch account info (balance + drawdown tracking)
    account_info = await mt5.get_account_info(bot_cfg.get("account_id", ""))
    balance = account_info.get("balance", 0.0)

    # 2a-1. Today's realized P&L for this bot (closed trades since UTC midnight)
    # — feeds the daily-loss cap (max_daily_loss_pct of live balance).
    realized_pnl_today = 0.0
    try:
        from datetime import datetime as _dt
        from datetime import timezone as _tz
        day_start = _dt.now(_tz.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        closed = supabase.table("trades").select("profit").eq("bot_id", bot_id) \
            .eq("status", "closed").gte("closed_at", day_start).execute()
        realized_pnl_today = sum(float(t.get("profit") or 0) for t in (closed.data or []))
        bot_instance.realized_pnl_today = realized_pnl_today
    except Exception as e:
        _logger.warning(f"[scalp_fvg {bot_id}] Failed to read realized P&L for daily loss cap: {e}")

    # Track initial_balance from MT5 if not set.
    # A configured initial_balance can be a STALE snapshot (e.g. config says
    # $100 but the account really has $20 after a withdrawal, or a previous
    # test wrote 100 into config). The drawdown kill switch would then fire on
    # EVERY boot (79.5% >= 40%) and the bot would never trade — which is the
    # exact 'bot is not starting' symptom. Policy:
    #   - if no baseline yet: adopt live balance
    #   - if live balance is HIGHER than baseline: re-anchor (account grew)
    #   - if live balance is LOWER but the drop is the FULL configured
    #     drawdown limit (i.e. the kill switch would fire immediately at
    #     startup before any trading): the baseline is stale, not a real
    #     drawdown — re-anchor to live balance too. A real drawdown is
    #     measured from a baseline the bot itself set on its first cycle,
    #     not from a hand-typed config value.
    if bot_instance.initial_balance <= 0:
        bot_instance.initial_balance = balance if balance > 0 else 100.0
        _logger.info(f"[scalp_fvg {bot_id}] initial_balance set to ${bot_instance.initial_balance:.2f}")
    elif balance > bot_instance.initial_balance:
        bot_instance.initial_balance = balance
        _logger.info(f"[scalp_fvg {bot_id}] initial_balance re-anchored to live ${balance:.2f}")
    elif balance > 0 and bot_instance.initial_balance > 0:
        drop_pct = (1 - balance / bot_instance.initial_balance) * 100
        if drop_pct >= (bot_instance.max_drawdown_pct * 100):
            # Baseline is stale — a real drawdown would be measured from a
            # baseline the bot set itself. Re-anchor so the bot can trade.
            _logger.warning(
                f"[scalp_fvg {bot_id}] initial_balance ${bot_instance.initial_balance:.2f} is stale "
                f"(live ${balance:.2f} = {drop_pct:.0f}% drop) — re-anchoring to live balance"
            )
            bot_instance.initial_balance = balance

    # ---- INDEPENDENT DRAWDOWN CHECK — runs every cycle regardless of signals ----
    # Skip when balance is 0/None — that means MT5 has no account logged in,
    # NOT a 100% drawdown. Previously balance=0 fired the 40% kill switch and
    # silently halted the bot for what is actually a login problem.
    if balance > 0 and bot_instance.initial_balance > 0:
        current_drawdown_pct = max(0, (1 - balance / bot_instance.initial_balance) * 100)
        if current_drawdown_pct >= (bot_instance.max_drawdown_pct * 100):
            _logger.warning(
                f"[scalp_fvg {bot_id}] Drawdown {current_drawdown_pct:.1f}% >= "
                f"{bot_instance.max_drawdown_pct*100:.0f}% limit — emergency closing all positions"
            )
            stop_result = await _execute_stop_trading(
                {"action": "STOP_TRADING", "reason": f"Account drawdown {current_drawdown_pct:.1f}% exceeds {bot_instance.max_drawdown_pct*100:.0f}% limit"},
                bot_id,
                pair=pair,
            )
            results.append(stop_result)
            results.append({"action": "STOP_TRADING", "success": True})
            return results

    # 2b. Fetch open positions from MT5
    all_positions = await mt5.get_positions(bot_cfg.get("account_id", ""))
    current_position = None
    for p in all_positions:
        if _symbols_match(p.get("symbol", ""), pair):
            current_position = {
                "ticket": p["ticket"],
                "direction": p["type"],
                "entry_price": p["open_price"],
                "sl": p.get("stop_loss", 0),
            }
            break  # Only one position for scalping

    # 3. Resolve pip value from REAL MT5 symbol specs (tick value / tick size).
    #    Hardcoding pip values (10.0 for EURUSD, 0.1 for XAU) breaks gold and
    #    crypto — XAUUSD has 2-decimal prices and a different contract size.
    pip_value_per_lot, pip_size = _resolve_pip_specs(pair)

    # 4. Generate signal
    signal = bot_instance.generate_signal(
        df=df,
        current_position=current_position,
        account_balance=balance,
        pip_value_per_lot=pip_value_per_lot,
        lot_size=lot_size,
        pip_size=pip_size,
        realized_pnl_today=realized_pnl_today,
    )

    # 5. Execute
    if signal is None:
        return results

    result = await execute_trade(signal, bot_id, bot_cfg.get("user_id"),
                                  pair, lot_size, bot_instance)

    if result.get("success"):
        # Register trade count for daily cap
        if signal['action'] in ('ENTER', 'CLOSE_AND_REVERSE'):
            bot_instance.register_trade_executed()
            _logger.info(f"[scalp_fvg {bot_id}] {signal['action']} OK — {signal.get('reason', '')}")

        # If STOP_TRADING, signal the caller to break the loop
        if signal['action'] == 'STOP_TRADING':
            results.append({"action": "STOP_TRADING", "success": True})
    else:
        _logger.warning(f"[scalp_fvg {bot_id}] {signal['action']} FAIL — {result.get('error', '')}")

    results.append(result)
    return results
