"""
Async bot engine that runs trading strategies and executes trades via local MT5 terminal.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
import pandas as pd
from app.database import supabase
from app.services import metaapi_service as mt5
from app.services.scalp_scheduler import _symbols_match

_running_bots: dict = {}
_strategy_instances: dict = {}
_bot_runtime_status: dict = {}

logger = logging.getLogger("bot_engine")


def _set_bot_runtime(bot_id: str, state: str = "", last_message: str = "", error_code: Optional[int] = None, reversals: int = 0):
    _bot_runtime_status[bot_id] = {
        "state": state,
        "last_message": last_message,
        "error_code": error_code,
        "reversals": reversals,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def get_bot_runtime_status(bot_id: str) -> Optional[dict]:
    return _bot_runtime_status.get(bot_id)


async def _verify_bot_terminal_ownership(bot_cfg: dict) -> tuple[bool, str, str]:
    """
    Verify that the currently active local MT5 terminal login belongs to this bot's owner.
    Prevents cross-user bot execution or accidentally trading another user's live broker account.
    Returns (is_authorized, account_id, reason).
    """
    user_id = bot_cfg.get("user_id")
    if not user_id:
        return False, "", "Missing user_id on bot configuration"
    try:
        def _get_owner_acc():
            return (
                supabase.table("accounts")
                .select("id, login, status")
                .eq("user_id", user_id)
                .eq("status", "connected")
                .execute()
            )

        acc_res, terminal_info = await asyncio.gather(
            asyncio.to_thread(_get_owner_acc),
            mt5.get_account_info(""),
        )
        rows = acc_res.data or []
        if not rows:
            return False, "", "Owner has no connected broker account"

        terminal_login = str(terminal_info.get("login", "")).strip() if terminal_info else ""
        if not terminal_login:
            return False, "", "MT5 terminal is not logged in"

        req_acc_id = bot_cfg.get("account_id") or ""
        matched = None
        for r in rows:
            if str(r.get("login", "")).strip() == terminal_login:
                if not req_acc_id or r.get("id") == req_acc_id:
                    matched = r
                    break
        # Fallback if bot had stale account_id from a prior session of SAME user & login
        if not matched:
            for r in rows:
                if str(r.get("login", "")).strip() == terminal_login:
                    matched = r
                    break

        if not matched:
            return False, "", "Active MT5 terminal login does not match bot owner's connected account"
        return True, matched["id"], ""
    except Exception as e:
        return False, "", f"Ownership check error: {e}"


def _get_strategy(strategy_name: str, bot_config: dict = None) -> Optional:
    """Get a strategy instance by name, injecting sub-bots for Full Confluence."""
    key = strategy_name
    if strategy_name == "full_confluence":
        # Need fresh instances each time because they carry trade-count state
        from app.services.strategies.smart_money import SmartMoneyStrategy
        from app.services.strategies.mirror import MirrorStrategy
        from app.services.strategies.classic import ClassicStrategy
        from app.services.strategies.full_confluence import FullConfluenceStrategy

        sm = SmartMoneyStrategy(swing_lookback=5, displacement_atr_mult=1.5, atr_period=14, min_rr=1.0)
        mmc = MirrorStrategy(swing_lookback=5, min_rr=1.0)
        snr = ClassicStrategy(swing_lookback=5, zone_atr_multiplier=0.5, min_touches=2, atr_period=14, min_rr=1.0)
        return FullConfluenceStrategy(smart_money_bot=sm, mirror_bot=mmc, classic_bot=snr, min_rr=4.0)

    if key not in _strategy_instances:
        if strategy_name == "smart_money":
            from app.services.strategies.smart_money import SmartMoneyStrategy
            _strategy_instances[key] = SmartMoneyStrategy()
        elif strategy_name in ("mmc_mirror", "mirror"):
            from app.services.strategies.mirror import MirrorStrategy
            _strategy_instances[key] = MirrorStrategy(
                swing_lookback=8,
                eq_tp_extension=0.2,
                min_rr=1.0,
                rejection_mode="mid",
                enable_mirror_setup=False,
                zone_reentry_block_bars=240,
                zone_reentry_atr_mult=0.5,
                post_signal_cooldown_bars=6,
                atr_max_median_mult=1.5,
                trend_ema_period=200,
                spread_pct=0.0,
                drop_forming_bar=True
            )
        elif strategy_name == "classic":
            from app.services.strategies.classic import ClassicStrategy
            _strategy_instances[key] = ClassicStrategy()
        elif strategy_name == "scalp":
            from app.services.strategies.scalp import ScalpStrategy
            _strategy_instances[key] = ScalpStrategy()
        elif strategy_name == "scalp_pyramid":
            from app.services.strategies.scalp_pyramid import ScalpPyramidBot
            _strategy_instances[key] = ScalpPyramidBot()
        elif strategy_name == "scalp_fvg":
            from app.services.strategies.scalp_fvg import ScalpModeBot
            _strategy_instances[key] = ScalpModeBot()
        elif strategy_name == "signal_strength_hedge":
            from app.services.strategies.signal_strength_hedge import SignalStrengthHedgeBot
            _strategy_instances[key] = SignalStrengthHedgeBot()
        elif strategy_name == "nyao_scalper":
            from app.services.strategies.nyao_scalper import NyaoScalperBot
            _strategy_instances[key] = NyaoScalperBot()
        elif strategy_name in ("trading_agents", "ai_committee"):
            from app.services.strategies.trading_agents_strategy import TradingAgentsStrategy
            _strategy_instances[key] = TradingAgentsStrategy()
        elif strategy_name == "pipstep_reversal":
            from app.services.strategies.pipstep_reversal import PipStepReversalBot
            _strategy_instances[key] = PipStepReversalBot()
        else:
            # Custom strategy added via the admin panel (file-backed store, trusted code)
            from app.services import strategy_store
            cls = strategy_store.load_dynamic_class(strategy_name)
            if cls is not None:
                _strategy_instances[key] = cls()
    return _strategy_instances.get(key)


def _get_poll_interval(strategy: str) -> int:
    intervals = {
        "scalp": 15,
        "signal_strength_hedge": 15,
        "nyao_scalper": 10,
        "pipstep_reversal": 3,
        "smart_money": 60,
        "mmc_mirror": 60,
        "mirror": 60,
        "classic": 120,
        "full_confluence": 300,
    }
    return intervals.get(strategy, 60)


async def start_bot(bot_id: str):
    """Start a bot in the background."""
    # A previous task may have finished (crash, error, stop) but stayed in the
    # dict — if so, drop it so we can actually start a fresh loop. Previously
    # any crashed task blocked re-starting forever (UI said Running, nothing ran).
    old = _running_bots.pop(bot_id, None)
    if old and not old.done():
        old.cancel()
        try:
            await old
        except (asyncio.CancelledError, Exception):
            pass

    # Check if this is a pyramid bot — needs a position-aware loop
    result = supabase.table("bot_settings").select("strategy, config").eq("id", bot_id).single().execute()
    cfg = (result.data.get("config") or {}) if result.data else {}
    strategy_name = (cfg.get("_actual_strategy") if isinstance(cfg, dict) else None) or (result.data.get("strategy", "") if result.data else "")

    if strategy_name == "scalp_pyramid":
        task = asyncio.create_task(_bot_loop_pyramid(bot_id))
    elif strategy_name in ("mmc_mirror", "mirror"):
        task = asyncio.create_task(_bot_loop_mmc(bot_id))
    elif strategy_name == "scalp_fvg":
        task = asyncio.create_task(_bot_loop_scalp_fvg(bot_id))
    elif strategy_name == "signal_strength_hedge":
        task = asyncio.create_task(_bot_loop_signal_strength_hedge(bot_id))
    elif strategy_name == "nyao_scalper":
        task = asyncio.create_task(_bot_loop_nyao_scalper(bot_id))
    elif strategy_name == "pipstep_reversal":
        task = asyncio.create_task(_bot_loop_pipstep_reversal(bot_id))
    else:
        task = asyncio.create_task(_bot_loop(bot_id))
    _running_bots[bot_id] = task
    logger.info(f"Bot {bot_id} ({strategy_name}) started")


async def stop_bot(bot_id: str):
    """Stop a running bot."""
    task = _running_bots.pop(bot_id, None)
    _bot_runtime_status.pop(bot_id, None)
    if task:
        task.cancel()
        logger.info(f"Bot {bot_id} stopped")


async def _bot_loop(bot_id: str):
    """Main bot loop: fetch config -> fetch candles -> analyze -> execute -> log."""
    try:
        while True:
            result = supabase.table("bot_settings").select("*").eq("id", bot_id).single().execute()
            if not result.data or result.data.get("status") != "running":
                break

            bot = result.data
            cfg_meta = bot.get("config") or {}
            strategy_name = (cfg_meta.get("_actual_strategy") if isinstance(cfg_meta, dict) else None) or bot["strategy"]
            strategy = _get_strategy(strategy_name, bot.get("config"))
            if not strategy:
                logger.error(f"Unknown strategy: {strategy_name}")
                try:
                    supabase.table("bot_settings").update({"status": "error"}).eq("id", bot_id).execute()
                except Exception as e:

                    logger.error(f'Database operation failed: {e}')
                break

            config = bot.get("config", {})
            config["lot_size"] = bot.get("lot_size", 0.01)
            config["take_profit"] = bot.get("take_profit", 50)
            config["stop_loss"] = bot.get("stop_loss", 25)

            pair = bot["pair"]
            timeframe = bot.get("timeframe", "H1")

            # Multi-tenant security guard: verify owner's connected MT5 login matches terminal
            ok, resolved_acc_id, deny_reason = await _verify_bot_terminal_ownership(bot)
            if not ok:
                logger.warning(f"[SECURITY GUARD] Bot {bot_id} paused: {deny_reason}")
                await asyncio.sleep(_get_poll_interval(strategy_name))
                continue

            # Fetch candle data (300 candles ensures sufficient lookback for EMA 200, swings, and filters)
            candles = await mt5.get_candles(pair, timeframe, count=300)
            if not candles:
                logger.warning(f"No candle data for {pair}, skipping cycle")
                await asyncio.sleep(_get_poll_interval(strategy_name))
                continue

            # Run analysis
            signal = await strategy.analyze(pair, candles, config)

            if signal:
                # Execute trade via local MT5
                order = await mt5.place_order(
                    account_id=resolved_acc_id,
                    pair=signal.pair,
                    order_type=signal.action.upper(),
                    volume=signal.lot_size,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                )

                if order and order.get("success"):
                    # Column names MUST match the LIVE trades table schema —
                    # VERIFIED against the deployed DB: (id, user_id, bot_id,
                    # account_id, symbol, direction, volume, open_price,
                    # close_price, stop_loss, take_profit, status, profit,
                    # strategy, opened_at, closed_at, reason, metadata).
                    # The deployed 'id' column has NO gen_random_uuid() default
                    # (verified: insert without id -> 23502 null violation), so
                    # we must supply one. NOTE: 001_schema.sql describes a
                    # DIFFERENT schema (pair/type/lot_size) — NOT deployed.
                    from uuid import uuid4
                    trade = {
                        "id": str(uuid4()),
                        "user_id": bot["user_id"],
                        "account_id": bot["account_id"],
                        "bot_id": bot_id,
                        "strategy": strategy_name,
                        "symbol": signal.pair,
                        "direction": signal.action.lower(),
                        "volume": signal.lot_size,
                        "open_price": order.get("price", 0),
                        "stop_loss": signal.stop_loss,
                        "take_profit": signal.take_profit,
                        "status": "open",
                        "reason": signal.reason,
                        "opened_at": datetime.utcnow().isoformat(),
                        "ticket": str(order["ticket"]),
                    }
                    supabase.table("trades").insert(trade).execute()
                    logger.info(f"Bot {bot_id}: {signal.action.upper()} {pair} — {signal.reason}")
                else:
                    logger.warning(f"Bot {bot_id}: Order failed — {order.get('error', 'unknown')}")
            else:
                logger.debug(f"Bot {bot_id}: No signal for {pair}")

            await asyncio.sleep(_get_poll_interval(strategy_name))

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Bot {bot_id} error: {e}")
        try:
            supabase.table("bot_settings").update({"status": "error"}).eq("id", bot_id).execute()
        except Exception as e:

            logger.error(f'Database operation failed: {e}')

async def _bot_loop_mmc(bot_id: str):
    """Specialized loop for MMC Mirror that tracks trades and fires on_trade_result loss cooldown."""
    try:
        while True:
            result = supabase.table("bot_settings").select("*").eq("id", bot_id).single().execute()
            if not result.data or result.data.get("status") != "running":
                break

            bot = result.data
            cfg_meta = bot.get("config") or {}
            strategy_name = (cfg_meta.get("_actual_strategy") if isinstance(cfg_meta, dict) else None) or bot["strategy"]
            strategy = _get_strategy(strategy_name, bot.get("config"))
            if not strategy:
                logger.error(f"Unknown strategy: {strategy_name}")
                break

            config = bot.get("config", {})
            config["lot_size"] = bot.get("lot_size", 0.01)
            config["take_profit"] = bot.get("take_profit", 50)
            config["stop_loss"] = bot.get("stop_loss", 25)

            pair = bot["pair"]
            timeframe = bot.get("timeframe", "M5")

            ok, _, deny_reason = await _verify_bot_terminal_ownership(bot)
            if not ok:
                logger.warning(f"[SECURITY GUARD] MMC Bot {bot_id} paused: {deny_reason}")
                await asyncio.sleep(_get_poll_interval(strategy_name))
                continue

            # 1. Track closures and fire cooldown
            db_trades = supabase.table("trades").select("*").eq("bot_id", bot_id).eq("status", "open").execute()
            tracked_trades = {str(t["ticket"]): t for t in db_trades.data if t.get("ticket")} if db_trades.data else {}
            
            if tracked_trades:
                mt5_positions = await mt5.get_positions(bot.get("account_id", ""))
                active_tickets = {str(p["ticket"]) for p in mt5_positions}
                for ticket_str, db_trade in tracked_trades.items():
                    if ticket_str not in active_tickets:
                        # Trade disappeared from open positions -> it closed
                        profit = await mt5.get_history_deal_profit(int(ticket_str))
                        close_time = datetime.utcnow().isoformat()
                        
                        if profit < 0:
                            strategy.on_trade_result("loss", close_time, cooldown_seconds=18000)
                            logger.info(f"Bot {bot_id}: MMC Trade {ticket_str} closed at loss ({profit}). Cooldown activated.")
                        else:
                            strategy.on_trade_result("win", close_time)
                            logger.info(f"Bot {bot_id}: MMC Trade {ticket_str} closed at win ({profit}).")
                        
                        # Mark DB as closed
                        try:
                            supabase.table("trades").update({
                                "status": "closed",
                                "closed_at": close_time,
                                "profit": profit
                            }).eq("id", db_trade["id"]).execute()
                        except Exception as e:
                            logger.error(f"Failed to update trade {db_trade['id']}: {e}")

            # 2. Fetch candles and run analysis (300 candles exceeds min_bars_required of 205)
            candles = await mt5.get_candles(pair, timeframe, count=300)
            if not candles:
                logger.warning(f"No candle data for {pair}, skipping cycle")
                await asyncio.sleep(_get_poll_interval(strategy_name))
                continue

            signal = await strategy.analyze(pair, candles, config)
            if signal:
                order = await mt5.place_order(
                    account_id="",
                    pair=signal.pair,
                    order_type=signal.action.upper(),
                    volume=signal.lot_size,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                )

                if order and order.get("success"):
                    from uuid import uuid4
                    trade = {
                        "id": str(uuid4()),
                        "user_id": bot["user_id"],
                        "account_id": bot["account_id"],
                        "bot_id": bot_id,
                        "strategy": strategy_name,
                        "symbol": signal.pair,
                        "direction": signal.action.lower(),
                        "volume": signal.lot_size,
                        "open_price": order.get("price", 0),
                        "stop_loss": signal.stop_loss,
                        "take_profit": signal.take_profit,
                        "status": "open",
                        "reason": signal.reason,
                        "opened_at": datetime.utcnow().isoformat(),
                        "ticket": str(order["ticket"]),
                    }
                    supabase.table("trades").insert(trade).execute()
                    logger.info(f"Bot {bot_id}: {signal.action.upper()} {pair} — {signal.reason}")
                else:
                    logger.warning(f"Bot {bot_id}: Order failed — {order.get('error', 'unknown')}")

            await asyncio.sleep(_get_poll_interval(strategy_name))

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Bot {bot_id} error: {e}")
        try:
            supabase.table("bot_settings").update({"status": "error"}).eq("id", bot_id).execute()
        except Exception as e:
            logger.error(f'Database operation failed: {e}')


async def _bot_loop_pyramid(bot_id: str):
    """
    Specialized bot loop for ScalpPyramidBot (position-aware pyramiding).
    Unlike the standard _bot_loop which generates one Signal per cycle,
    this loop:
      1. Fetches OHLCV data and the bot's open positions from MT5
      2. Feeds both into generate_actions() to get close/modify_sl/open commands
      3. Executes each action via MT5 and logs to Supabase
      4. Runs more frequently (every 15s on M1 candles) for scalping
    """
    from app.services.strategies.scalp_pyramid import run_scalp_pyramid_cycle, ScalpPyramidBot

    bot_instance = ScalpPyramidBot()

    try:
        while True:
            result = supabase.table("bot_settings").select("*").eq("id", bot_id).single().execute()
            if not result.data or result.data.get("status") != "running":
                break

            bot_cfg = result.data
            pair = bot_cfg["pair"]
            timeframe = bot_cfg.get("timeframe", "M1")

            ok, _, deny_reason = await _verify_bot_terminal_ownership(bot_cfg)
            if not ok:
                logger.warning(f"[SECURITY GUARD] PyramidBot {bot_id} paused: {deny_reason}")
                await asyncio.sleep(15)
                continue

            # Pull config overrides from bot_settings.config dict
            cfg = bot_cfg.get("config", {}) or {}
            bot_instance.base_lot = cfg.get("base_lot", bot_cfg.get("lot_size", bot_instance.base_lot))
            bot_instance.lot_decrease_factor = cfg.get("lot_decrease_factor", bot_instance.lot_decrease_factor)
            bot_instance.max_positions = cfg.get("max_positions", bot_cfg.get("max_trades", bot_instance.max_positions))
            bot_instance.breakeven_trigger_pct = cfg.get("breakeven_trigger_pct", bot_instance.breakeven_trigger_pct)
            bot_instance.profit_target_pct = cfg.get("profit_target_pct", bot_instance.profit_target_pct)
            bot_instance.min_profit_to_add_pct = cfg.get("min_profit_to_add_pct", bot_instance.min_profit_to_add_pct)

            # 1. Fetch candles
            candles = await mt5.get_candles(pair, timeframe, count=100)
            if not candles or len(candles) < 30:
                logger.warning(f"[PyramidBot] Insufficient candle data for {pair}")
                await asyncio.sleep(15)
                continue

            df = pd.DataFrame(candles)

            # 2. Fetch open positions from MT5 for this symbol
            all_positions = await mt5.get_positions(bot_cfg.get("account_id", ""))
            symbol_positions = []
            for p in all_positions:
                # Match by resolved symbol — broker suffixes (XAUUSDm vs XAUUSD)
                # previously broke this, causing unbounded pyramid stacking
                if _symbols_match(p.get("symbol", ""), pair):
                    symbol_positions.append({
                        "ticket": p["ticket"],
                        "direction": p["type"],
                        "entry_price": p["open_price"],
                        "lot": p["volume"],
                        "sl": p.get("stop_loss", 0),
                        "breakeven_done": False,
                    })

            # 3. Generate and execute actions
            results = await run_scalp_pyramid_cycle(
                bot=bot_instance,
                df=df,
                open_positions=symbol_positions,
                symbol=pair,
                mt5_module=mt5,
                supabase=supabase,
                bot_id=bot_id,
                user_id=bot_cfg.get("user_id"),
            )

            for r in results:
                if r.get("success"):
                    logger.info(f"[PyramidBot {bot_id}] {r['action']} OK — {r.get('reason', '')}")
                else:
                    logger.warning(f"[PyramidBot {bot_id}] {r['action']} FAIL — {r.get('error', '')}")

            await asyncio.sleep(15)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"[PyramidBot {bot_id}] Fatal: {e}")
        try:
            supabase.table("bot_settings").update({"status": "error"}).eq("id", bot_id).execute()
        except Exception as e:

            logger.error(f'Database operation failed: {e}')


async def _bot_loop_scalp_fvg(bot_id: str):
    """
    Specialized loop for ScalpModeBot (FVG scalper with dollarized risk).
    Uses the scalp_scheduler module for the cycle logic and breakeven monitoring.
    """
    from app.services.scalp_scheduler import (
        run_scheduler_cycle,
        start_breakeven_monitor,
        stop_breakeven_monitor,
    )
    from app.services.strategies.scalp_fvg import ScalpModeBot

    bot_instance = ScalpModeBot()
    _config_loaded = False  # Only load config overrides once

    try:
        while True:
            result = supabase.table("bot_settings").select("*").eq("id", bot_id).single().execute()
            if not result.data or result.data.get("status") != "running":
                stop_breakeven_monitor(bot_id)
                break

            bot_cfg = result.data

            ok, _, deny_reason = await _verify_bot_terminal_ownership(bot_cfg)
            if not ok:
                logger.warning(f"[SECURITY GUARD] scalp_fvg {bot_id} paused: {deny_reason}")
                stop_breakeven_monitor(bot_id)
                await asyncio.sleep(15)
                continue

            # Load config overrides ONCE on first cycle only.
            # Previously this ran every cycle, overwriting the scheduler's
            # live-balance re-anchor (cfg says initial_balance=100 but
            # the real account has $20 → scheduler re-anchors to $20 →
            # next cycle reloads $100 from config → re-anchor fires again
            # → infinite loop, never actually trading).
            if not _config_loaded:
                _config_loaded = True
                cfg = bot_cfg.get("config", {}) or {}
                bot_instance.initial_balance = cfg.get("initial_balance", bot_cfg.get("initial_balance", 100.0))
                bot_instance.risk_per_trade_pct = cfg.get("risk_per_trade_pct", bot_instance.risk_per_trade_pct)
                bot_instance.target_profit_usd = cfg.get("target_profit_usd", bot_instance.target_profit_usd)
                # % of balance risk scaling (overrides the fixed-dollar fallbacks)
                bot_instance.target_profit_pct = cfg.get("target_profit_pct", bot_instance.target_profit_pct)
                bot_instance.max_daily_loss_pct = cfg.get("max_daily_loss_pct", bot_instance.max_daily_loss_pct)
                bot_instance.breakeven_usd = cfg.get("breakeven_usd", bot_instance.breakeven_usd)
                bot_instance.max_daily_trades = cfg.get("max_daily_trades", bot_cfg.get("max_trades", bot_instance.max_daily_trades))
                raw_dd = cfg.get("max_drawdown_pct", bot_instance.max_drawdown_pct)
                bot_instance.max_drawdown_pct = raw_dd / 100.0 if raw_dd > 1 else raw_dd
                # New rapid-scalper parameters (optional, defaults are sane)
                bot_instance.ema_fast = cfg.get("ema_fast", bot_instance.ema_fast)
                bot_instance.ema_slow = cfg.get("ema_slow", bot_instance.ema_slow)
                bot_instance.cooldown_bars = cfg.get("cooldown_bars", bot_instance.cooldown_bars)
                bot_instance.rsi_ob = cfg.get("rsi_ob", bot_instance.rsi_ob)
                bot_instance.rsi_os = cfg.get("rsi_os", bot_instance.rsi_os)

            # Run one scheduler cycle
            results = await run_scheduler_cycle(bot_id, bot_instance, bot_cfg)

            # Check if STOP_TRADING was returned — break if so
            if any(r.get("action") == "STOP_TRADING" for r in results):
                logger.warning(f"[scalp_fvg {bot_id}] Drawdown kill switch triggered -- halting loop")
                stop_breakeven_monitor(bot_id)
                break

            # Start breakeven monitor if not already running
            if results:
                start_breakeven_monitor(bot_id, bot_instance)

            await asyncio.sleep(15)

    except asyncio.CancelledError:
        stop_breakeven_monitor(bot_id)
    except Exception as e:
        logger.error(f"[scalp_fvg {bot_id}] Fatal: {e}")
        stop_breakeven_monitor(bot_id)
        try:
            supabase.table("bot_settings").update({"status": "error"}).eq("id", bot_id).execute()
        except Exception as e:

            logger.error(f'Database operation failed: {e}')


async def resume_running_bots():
    """On startup, ONLY resume bots whose owner actively matches the live MT5 terminal login."""
    try:
        result = await asyncio.to_thread(
            lambda: supabase.table("bot_settings").select("*").eq("status", "running").execute()
        )
        for bot in result.data or []:
            ok, _, deny_reason = await _verify_bot_terminal_ownership(bot)
            if not ok:
                logger.warning(
                    f"[SECURITY GUARD] Skipping startup resume of bot {bot['id']} "
                    f"(user={bot.get('user_id')}): {deny_reason}. Setting status=stopped."
                )
                try:
                    await asyncio.to_thread(
                        lambda bid=bot["id"]: supabase.table("bot_settings")
                        .update({"status": "stopped", "updated_at": datetime.utcnow().isoformat()})
                        .eq("id", bid)
                        .execute()
                    )
                except Exception:
                    pass
                continue

            try:
                acc = await mt5.get_account_info(bot.get("account_id", ""))
                balance = acc.get("balance", 0)
            except Exception:
                balance = "unknown"
            logger.warning(
                f"[RESUME WARNING] Resuming bot {bot['id']} ({bot.get('strategy', '?')}) on startup. "
                f"Live balance: ${balance}. Verify this is intentional."
            )
            await start_bot(bot["id"])
    except Exception as e:
        logger.error(f"Failed to resume bots: {e}")
def _insert_trade(supabase_module, bot_id, user_id, account_id, symbol, direction, volume, open_price, status, reason, ticket, strategy: str = "signal_strength_hedge"):
    """Insert a trade row using the new schema (with ticket column)."""
    try:
        from uuid import uuid4
        supabase_module.table("trades").insert({
            "id": str(uuid4()),
            "user_id": user_id,
            "account_id": account_id,
            "bot_id": bot_id,
            "strategy": strategy,
            "symbol": symbol,
            "direction": direction.lower(),
            "volume": volume,
            "open_price": open_price,
            "stop_loss": 0,
            "take_profit": 0,
            "status": status,
            "reason": reason,
            "opened_at": datetime.utcnow().isoformat(),
            "ticket": str(ticket),
        }).execute()
    except Exception as e:
        logger.warning(f"[{strategy}] trade insert failed: {e}")


def _mark_closed(supabase_module, user_id, close_price, ticket):
    """DB mark-closed using exact ticket."""
    try:
        supabase_module.table("trades").update({
            "status": "closed",
            "closed_at": datetime.utcnow().isoformat(),
            "close_price": close_price,
        }).eq("user_id", user_id).eq("ticket", str(ticket)).execute()
    except Exception as e:

        logger.error(f'Database operation failed: {e}')


async def _run_signal_strength_cycle(bot, bot_cfg, mt5_module, supabase_module, bot_id):
    """
    One cycle for SignalStrengthHedgeBot. Executes the strategy's action-dict
    protocol: ENTER, OPEN_HEDGE, CLOSE, PARTIAL_CLOSE, MODIFY_SL,
    CLOSE_ALL_AND_PAUSE. OPEN_HEDGE tags the new position with chain metadata
    (chain_id/hedge_level/chain_anchor_loss/cycle_num) exactly as the
    strategy's usage pseudocode specifies.
    Returns a list of per-action result dicts.
    """
    results = []
    pair = bot_cfg["pair"]
    timeframe = bot_cfg.get("timeframe", "M5")
    account_id = bot_cfg.get("account_id", "")
    user_id = bot_cfg.get("user_id")

    candles = await mt5_module.get_candles(pair, timeframe, count=120)
    if not candles or len(candles) < 30:
        return [{"action": "SKIP", "success": False, "error": "insufficient candle data"}]
    df = pd.DataFrame(candles)

    acc = await mt5_module.get_account_info(account_id)
    balance = acc.get("balance", 0) or 0
    equity = acc.get("equity", 0) or balance

    all_positions = await mt5_module.get_positions(account_id)
    positions = []
    for p in all_positions:
        if not _symbols_match(p.get("symbol", ""), pair):
            continue
        positions.append({
            "ticket": p["ticket"],
            "direction": p["type"],  # 'BUY' / 'SELL'
            "entry_price": p["open_price"],
            "lot": p["volume"],
            "profit": p.get("profit", 0),
            "open_time": datetime.fromisoformat(p["time"]) if p.get("time") else None,
        })

    # Current spread in points; 0 when unavailable (atr-ratio guard governs)
    current_spread_points = 0
    try:
        mod = mt5_module._ensure_mt5()
        resolved = mt5_module._resolve_symbol(pair)
        tick = mod.symbol_info_tick(resolved)
        if tick is not None:
            point = getattr(tick, "point", None) or 0.0001
            current_spread_points = round((tick.ask - tick.bid) / point, 2)
    except Exception as e:

        logger.error(f'Database operation failed: {e}')

    actions = bot.generate_signal(
        df=df,
        open_positions=positions,
        account_balance=balance,
        account_equity=equity,
        current_spread_points=current_spread_points,
        lot_size=bot_cfg.get("lot_size", 0.01),
    )

    for action in actions:
        atype = action["action"]
        try:
            if atype == "ENTER":
                order = await mt5_module.place_order(account_id, pair, action["direction"], action.get("lot", 0.01))
                if order and order.get("success"):
                    bot.on_position_opened(order["ticket"], action.get("pending_initial_score"))
                    _insert_trade(supabase_module, bot_id, user_id, account_id, pair, action["direction"],
                                  action.get("lot", 0.01), order.get("price", 0), "open",
                                  f"{action.get('reason', 'ENTER')} | ticket {order['ticket']}", order["ticket"])
                    results.append({"action": atype, "success": True, "ticket": order["ticket"]})
                else:
                    results.append({"action": atype, "success": False, "error": order.get("error", "order failed")})
            elif atype == "OPEN_HEDGE":
                order = await mt5_module.place_order(account_id, pair, action["direction"], action.get("lot", 0.01))
                if order and order.get("success"):
                    bot.position_state[order["ticket"]] = {
                        "chain_id": action.get("chain_id"),
                        "hedge_level": action.get("hedge_level"),
                        "chain_anchor_loss": action.get("chain_anchor_loss"),
                        "cycle_num": action.get("cycle_num"),
                        "initial_score": None,
                        "partial_level": 0,
                        "breakeven_done": False,
                        "no_rehedge": False,
                    }
                    _insert_trade(supabase_module, bot_id, user_id, account_id, pair, action["direction"],
                                  action.get("lot", 0.01), order.get("price", 0), "open",
                                  f"{action.get('reason', 'OPEN_HEDGE')} | chain {action.get('chain_id')} L{action.get('hedge_level')} | ticket {order['ticket']}", order["ticket"])
                    results.append({"action": atype, "success": True, "ticket": order["ticket"],
                                    "chain_id": action.get("chain_id")})
                else:
                    results.append({"action": atype, "success": False, "error": order.get("error", "order failed")})
            elif atype == "CLOSE":
                res = await mt5_module.close_position(account_id, str(action["ticket"]))
                if res.get("success"):
                    _mark_closed(supabase_module, user_id, res.get("price"), action["ticket"])
                    results.append({"action": atype, "success": True, "ticket": action["ticket"]})
                else:
                    results.append({"action": atype, "success": False, "error": res.get("error", "close failed")})
            elif atype == "PARTIAL_CLOSE":
                res = await mt5_module.partial_close_position(account_id, str(action["ticket"]),
                                                              action.get("close_pct", 0.25))
                results.append({"action": atype, "success": res.get("success", False), "ticket": action["ticket"],
                                "error": res.get("error") if not res.get("success") else None,
                                "closed_volume": res.get("closed_volume")})
            elif atype == "MODIFY_SL":
                res = await mt5_module.modify_sl_tp(account_id, str(action["ticket"]), stop_loss=action.get("new_sl"))
                results.append({"action": atype, "success": res.get("success", False), "ticket": action["ticket"],
                                "error": res.get("error") if not res.get("success") else None})
            elif atype == "CLOSE_ALL_AND_PAUSE":
                closed = 0
                for p in positions:
                    res = await mt5_module.close_position(account_id, str(p["ticket"]))
                    if res.get("success"):
                        closed += 1
                results.append({"action": atype, "success": True, "closed": closed,
                                "reason": action.get("reason", "basket stop")})
            else:
                results.append({"action": atype, "success": False, "error": f"unhandled action {atype}"})
        except Exception as e:
            logger.error(f"[signal_strength_hedge {bot_id}] action {atype} error: {e}")
            results.append({"action": atype, "success": False, "error": str(e)})
    return results


async def _bot_loop_signal_strength_hedge(bot_id: str):
    """Dedicated loop for SignalStrengthHedgeBot (action-dict protocol incl. OPEN_HEDGE)."""
    from app.services.strategies.signal_strength_hedge import SignalStrengthHedgeBot

    bot = SignalStrengthHedgeBot()
    _config_loaded = False

    try:
        while True:
            result = supabase.table("bot_settings").select("*").eq("id", bot_id).single().execute()
            if not result.data or result.data.get("status") != "running":
                break
            bot_cfg = result.data

            ok, _, deny_reason = await _verify_bot_terminal_ownership(bot_cfg)
            if not ok:
                logger.warning(f"[SECURITY GUARD] signal_strength_hedge {bot_id} paused: {deny_reason}")
                await asyncio.sleep(_get_poll_interval("signal_strength_hedge"))
                continue

            if not _config_loaded:
                _config_loaded = True
                cfg = bot_cfg.get("config", {}) or {}
                for key, value in cfg.items():
                    if hasattr(bot, key):
                        setattr(bot, key, value)
                if "max_daily_trades" not in cfg and bot_cfg.get("max_trades", 0) > 1:
                    bot.max_daily_trades = bot_cfg["max_trades"]
                logger.info(f"[signal_strength_hedge {bot_id}] config applied: {len(cfg)} override(s)")

            results = await _run_signal_strength_cycle(bot, bot_cfg, mt5, supabase, bot_id)
            for r in results:
                if r.get("success"):
                    logger.info(f"[signal_strength_hedge {bot_id}] {r['action']} OK - {r.get('reason', r.get('ticket', ''))}")
                else:
                    logger.warning(f"[signal_strength_hedge {bot_id}] {r['action']} FAIL - {r.get('error', '')}")

            # Respect the strategy's own pause window after a basket stop / drawdown pause
            if bot.paused_until is not None:
                wait_sec = max(0, (bot.paused_until - datetime.now(timezone.utc)).total_seconds())
                logger.warning(f"[signal_strength_hedge {bot_id}] paused for {wait_sec:.0f}s")
                await asyncio.sleep(min(wait_sec, 900))
            else:
                await asyncio.sleep(_get_poll_interval("signal_strength_hedge"))

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"[signal_strength_hedge {bot_id}] Fatal: {e}")
        try:
            supabase.table("bot_settings").update({"status": "error"}).eq("id", bot_id).execute()
        except Exception as e:

            logger.error(f'Database operation failed: {e}')


def _calculate_nyao_indicators(df: pd.DataFrame, fast_period: int = 9, slow_period: int = 21, rsi_period: int = 14, atr_period: int = 14):
    """Calculate EMA Fast, EMA Slow, RSI, and ATR for Nyao Scalper Bot."""
    import numpy as np

    ema_fast = df['close'].ewm(span=fast_period, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow_period, adjust=False).mean()

    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=rsi_period - 1, min_periods=rsi_period).mean()
    avg_loss = loss.ewm(com=rsi_period - 1, min_periods=rsi_period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = (100 - (100 / (1 + rs))).fillna(50)

    high, low, close = df['high'], df['low'], df['close']
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.rolling(atr_period).mean().fillna(0.0)

    return ema_fast, ema_slow, rsi, atr


def _calculate_signal_score(df: pd.DataFrame, is_buy: bool, ema_fast: pd.Series, ema_slow: pd.Series, rsi: pd.Series, atr: pd.Series) -> float:
    """Calculate signal strength score (0.0 to 10.0) for the specified direction."""
    if len(df) < 5:
        return 5.0

    score = 0.0

    # Trend alignment (up to 3.5 points)
    fast_val = ema_fast.iloc[-1]
    slow_val = ema_slow.iloc[-1]
    trend_aligned = (fast_val > slow_val) if is_buy else (fast_val < slow_val)
    if trend_aligned:
        score += 2.0
        if len(ema_fast) >= 2:
            slope_aligned = (ema_fast.iloc[-1] > ema_fast.iloc[-2]) if is_buy else (ema_fast.iloc[-1] < ema_fast.iloc[-2])
            if slope_aligned:
                score += 1.5

    # RSI Zone (up to 3.0 points)
    r = rsi.iloc[-1]
    if is_buy:
        if 40.0 <= r <= 70.0:
            score += 2.0
        if 50.0 <= r <= 65.0:
            score += 1.0
    else:
        if 30.0 <= r <= 60.0:
            score += 2.0
        if 35.0 <= r <= 50.0:
            score += 1.0

    # Momentum / Candle body (up to 2.0 points)
    candle = df.iloc[-1]
    body = abs(candle['close'] - candle['open'])
    recent_bodies = [abs(df.iloc[j]['close'] - df.iloc[j]['open']) for j in range(max(0, len(df) - 6), len(df) - 1)]
    avg_body = sum(recent_bodies) / len(recent_bodies) if recent_bodies else body
    if body >= avg_body:
        score += 1.0
    candle_aligned = (candle['close'] > candle['open']) if is_buy else (candle['close'] < candle['open'])
    if candle_aligned:
        score += 1.0

    # Volatility / ATR health (up to 1.5 points)
    cur_atr = atr.iloc[-1]
    recent_atr = atr.iloc[max(0, len(df) - 10):].mean()
    if recent_atr > 0 and (cur_atr / recent_atr) >= 0.8:
        score += 1.5

    return max(0.0, min(10.0, score))


async def _bot_loop_nyao_scalper(bot_id: str):
    """
    Dedicated loop for NyaoScalperBot.
    Manages existing positions across MT5 accounts:
      1. Fetches open MT5 positions for the configured pair
      2. Calculates EMA Fast, EMA Slow, RSI, and ATR
      3. For each position, calls manage_partial_closes() and evaluate_position_health()
      4. If health decay triggers a close, evaluates check_virtual_sl_reentry() and executes re-entry
    """
    from app.services.strategies.nyao_scalper import NyaoScalperBot
    import MetaTrader5 as raw_mt5

    bot = NyaoScalperBot()
    _config_loaded = False

    try:
        while True:
            result = supabase.table("bot_settings").select("*").eq("id", bot_id).single().execute()
            if not result.data or result.data.get("status") != "running":
                break
            bot_cfg = result.data
            pair = bot_cfg["pair"]
            timeframe = bot_cfg.get("timeframe", "M1")

            ok, _, deny_reason = await _verify_bot_terminal_ownership(bot_cfg)
            if not ok:
                logger.warning(f"[SECURITY GUARD] nyao_scalper {bot_id} paused: {deny_reason}")
                await asyncio.sleep(_get_poll_interval("nyao_scalper"))
                continue
            account_id = bot_cfg.get("account_id", "")
            user_id = bot_cfg.get("user_id")

            if not _config_loaded:
                _config_loaded = True
                cfg = bot_cfg.get("config", {}) or {}
                if "magic_number" in cfg:
                    bot.magic_number = int(cfg["magic_number"])
                logger.info(f"[nyao_scalper {bot_id}] started management for {pair} (magic={bot.magic_number})")

            # 1. Fetch candles for indicator calculation
            candles = await mt5.get_candles(pair, timeframe, count=100)
            if not candles or len(candles) < 30:
                logger.warning(f"[nyao_scalper {bot_id}] Insufficient candle data for {pair}")
                await asyncio.sleep(_get_poll_interval("nyao_scalper"))
                continue

            df = pd.DataFrame(candles)
            ema_fast_series, ema_slow_series, rsi_series, atr_series = _calculate_nyao_indicators(df)

            cur_ema_fast = float(ema_fast_series.iloc[-1])
            cur_ema_slow = float(ema_slow_series.iloc[-1])
            cur_rsi = float(rsi_series.iloc[-1])
            cur_atr = float(atr_series.iloc[-1])

            # 2. Fetch raw MT5 position objects (native MT5 namedtuple / object)
            mod = mt5._ensure_mt5()
            raw_positions = mod.positions_get()
            if raw_positions is None:
                raw_positions = ()

            matching_positions = [p for p in raw_positions if _symbols_match(p.symbol, pair)]
            open_tickets = {p.ticket for p in matching_positions}

            # 3. Process each open position
            for pos in matching_positions:
                is_buy = (pos.type == raw_mt5.POSITION_TYPE_BUY or pos.type == 0)
                current_score = _calculate_signal_score(df, is_buy, ema_fast_series, ema_slow_series, rsi_series, atr_series)

                # Determine initial score for decay comparison
                if pos.ticket in bot.position_state:
                    initial_score = bot.position_state[pos.ticket].get("initial_score", current_score)
                else:
                    initial_score = max(current_score, 8.0)
                    bot.position_state[pos.ticket] = {"level": 0, "initial_score": initial_score}

                # a. Scaled Partial Close on signal decay
                await bot.manage_partial_closes(pos, current_score, initial_score)

                # b. Position Health Evaluation (Hard Virtual SL if health < 0.40)
                health = await bot.evaluate_position_health(pos, cur_atr, cur_rsi, cur_ema_fast, cur_ema_slow)

                # c. Check Virtual SL Re-entry if position was closed due to health decay
                if health < 0.40:
                    should_reenter, reenter_params = await bot.check_virtual_sl_reentry(pos, current_score, initial_score)
                    if should_reenter and reenter_params:
                        # Execute re-entry order via MT5
                        reenter_req = {
                            "action": raw_mt5.TRADE_ACTION_DEAL,
                            "symbol": reenter_params["symbol"],
                            "volume": reenter_params["volume"],
                            "type": reenter_params["order_type"],
                            "price": reenter_params["price"],
                            "deviation": 20,
                            "magic": bot.magic_number,
                            "comment": "Nyao Re-entry",
                            "type_time": raw_mt5.ORDER_TIME_GTC,
                            "type_filling": raw_mt5.ORDER_FILLING_IOC,
                        }
                        reenter_res = raw_mt5.order_send(reenter_req)
                        if reenter_res and reenter_res.retcode == raw_mt5.TRADE_RETCODE_DONE:
                            new_ticket = reenter_res.order
                            bot.position_state[new_ticket] = {
                                "level": 0,
                                "initial_score": reenter_params.get("signal_score", current_score),
                            }
                            _insert_trade(
                                supabase,
                                bot_id,
                                user_id,
                                account_id,
                                pair,
                                "buy" if is_buy else "sell",
                                reenter_params["volume"],
                                getattr(reenter_res, "price", reenter_params["price"]),
                                "open",
                                f"Nyao Virtual SL Re-entry | ticket {new_ticket}",
                                new_ticket,
                                strategy="nyao_scalper",
                            )
                            logger.info(f"[nyao_scalper {bot_id}] Re-entry executed successfully: ticket {new_ticket}")
                        else:
                            err_msg = getattr(reenter_res, 'comment', 'order_send failed')
                            logger.warning(f"[nyao_scalper {bot_id}] Re-entry order failed: {err_msg}")

            # 4. State cleanup for closed positions
            for ticket in list(bot.position_state.keys()):
                if ticket not in open_tickets:
                    bot.cleanup_state(ticket)



            await asyncio.sleep(_get_poll_interval("nyao_scalper"))

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"[nyao_scalper {bot_id}] Fatal: {e}")
        try:
            supabase.table("bot_settings").update({"status": "error"}).eq("id", bot_id).execute()
        except Exception as e:
            logger.error(f'Database operation failed: {e}')


async def _bot_loop_pipstep_reversal(bot_id: str):
    """
    1:1 Async Port of PipStep_Reversal_EA.mq5:
      - CanSend() gate & OnSendFail() exponential backoff
      - NormLots(), NormPrice(tick_size), MinStopDist() + spread widening, MarginOk()
      - BuyStop + SellStop symmetrical straddle pair (no TP)
      - Step trailing SL + initial SL recovery if missing
      - Cancel opposite pending orders when position triggers & periodically every 2s
      - Up to 3s history lag wait on close, DEAL_REASON_SL-only instant reversal (with magic & deviation)
      - Daily loss/profit halt closing only this EA's magic+symbol positions/pendings
      - Delete pending orders on stop/removal when delete_on_remove=True
    """
    from app.services.strategies.pipstep_reversal import PipStepReversalBot
    from uuid import uuid4
    import time

    bot = PipStepReversalBot()
    _config_loaded = False
    _last_pair = ""
    _last_resolved_sym = ""
    _recorded_open_tickets: set[str] = set()

    async def _delete_my_stop_pendings(sym: str):
        pendings = await mt5.get_pending_orders(symbol=sym, magic=bot.magic_number)
        for p in pendings:
            if p.get("type") in ("BUY_STOP", "SELL_STOP"):
                await mt5.delete_pending_order(p["ticket"])

    async def _close_all_mine(acc_id: str, sym_pair: str):
        positions = await mt5.get_positions(acc_id)
        for pos in positions:
            if pos.get("magic") == bot.magic_number and _symbols_match(pos.get("symbol", ""), sym_pair):
                await mt5.close_position(acc_id, str(pos["ticket"]))

    async def _ensure_trade_recorded(acc_id: str, uid: str, sym: str, direction_str: str, vol: float, price: float, sl: float, ticket_id: int, reason_txt: str):
        t_str = str(ticket_id)
        if not uid or t_str in _recorded_open_tickets:
            return
        _recorded_open_tickets.add(t_str)
        try:
            existing = await asyncio.to_thread(
                lambda: supabase.table("trades").select("id").eq("user_id", uid).eq("ticket", t_str).limit(1).execute()
            )
            if existing.data:
                return
            trade_row = {
                "id": str(uuid4()),
                "user_id": uid,
                "account_id": acc_id,
                "bot_id": bot_id,
                "strategy": "pipstep_reversal",
                "symbol": sym,
                "direction": direction_str.lower(),
                "volume": float(vol),
                "open_price": float(price),
                "stop_loss": float(sl or 0.0),
                "take_profit": 0.0,
                "status": "open",
                "reason": reason_txt,
                "opened_at": datetime.utcnow().isoformat(),
                "ticket": t_str,
            }
            await asyncio.to_thread(lambda: supabase.table("trades").insert(trade_row).execute())
        except Exception as ins_err:
            logger.debug(f"[pipstep_reversal {bot_id}] Trade record note: {ins_err}")

    try:
        while True:
            result = await asyncio.to_thread(
                lambda: supabase.table("bot_settings").select("*").eq("id", bot_id).single().execute()
            )
            if not result.data or result.data.get("status") != "running":
                break

            bot_cfg = result.data
            pair = bot_cfg["pair"]
            _last_pair = pair
            account_id = bot_cfg.get("account_id", "")
            user_id = bot_cfg.get("user_id")

            ok, resolved_acc_id, deny_reason = await _verify_bot_terminal_ownership(bot_cfg)
            if not ok:
                bot.set_msg(deny_reason, time.time())
                _set_bot_runtime(bot_id, bot.state, deny_reason, None, bot.reversals_count)
                logger.warning(f"[SECURITY GUARD] pipstep_reversal {bot_id} paused: {deny_reason}")
                await asyncio.sleep(10)
                continue
            account_id = resolved_acc_id or account_id

            if not _config_loaded:
                _config_loaded = True
                cfg = bot_cfg.get("config", {}) or {}
                bot.lots = max(0.01, float(cfg.get("lots", bot_cfg.get("lot_size", bot.lots)) or 0.01))
                bot.entry_pips = max(0.1, float(cfg.get("entry_pips", 10.0) or 10.0))
                bot.sl_pips = max(0.1, float(cfg.get("sl_pips", 10.0) or 10.0))
                bot.step_pips = max(0.1, float(cfg.get("step_pips", 10.0) or 10.0))
                bot.pip_price = float(cfg.get("pip_price", 0.0) or 0.0)
                bot.max_spread_pips = float(cfg.get("max_spread_pips", 0.0) or 0.0)
                bot.deviation_pips = float(cfg.get("deviation_pips", 3.0) or 3.0)
                bot.daily_loss_pct = max(0.1, float(cfg.get("daily_loss_pct", 10.0) or 10.0))
                bot.daily_profit_pct = max(0.1, float(cfg.get("daily_profit_pct", 20.0) or 20.0))
                bot.retry_cooldown_sec = max(1, int(cfg.get("retry_cooldown_sec", 15) or 15))
                bot.max_backoff_sec = max(bot.retry_cooldown_sec, int(cfg.get("max_backoff_sec", 1800) or 1800))
                bot.delete_on_remove = bool(cfg.get("delete_on_remove", True))
                bot.magic_number = int(cfg.get("magic_number", 26110401) or 26110401)
                bot.comment = str(cfg.get("comment", "PIPSTEP") or "PIPSTEP")
                msg = (
                    f"Armed for {pair} (lots={bot.lots}, entry={bot.entry_pips}p, "
                    f"sl={bot.sl_pips}p, step={bot.step_pips}p, magic={bot.magic_number})"
                )
                bot.set_msg(msg, time.time())
                _set_bot_runtime(bot_id, bot.state, msg, None, bot.reversals_count)
                logger.info(f"[pipstep_reversal {bot_id}] {msg}")

            # 1. MT5 terminal, account, and symbol snapshot
            mod = mt5._ensure_mt5()
            resolved = mt5._ensure_symbol_visible(pair)
            _last_resolved_sym = resolved
            tick = mod.symbol_info_tick(resolved)
            sym_info = mod.symbol_info(resolved)
            t_info = mod.terminal_info()
            a_info = mod.account_info()

            if tick is None or sym_info is None or a_info is None:
                err = f"Waiting for MT5 market data on {resolved}..."
                _set_bot_runtime(bot_id, bot.state, err, None, bot.reversals_count)
                await asyncio.sleep(2)
                continue

            now_ts = time.time()
            server_now = datetime.fromtimestamp(tick.time, tz=timezone.utc) if getattr(tick, "time", 0) else datetime.now(timezone.utc)
            equity = float(getattr(a_info, "equity", 0.0) or 0.0)
            margin_free = float(getattr(a_info, "margin_free", 0.0) or 0.0)

            # UpdateDay & ManageDailyRisk
            bot.update_day(equity, server_now)
            limit_breached = bot.check_daily_limits(equity)
            if limit_breached:
                bot.set_msg(limit_breached, now_ts)
                logger.warning(f"[pipstep_reversal {bot_id}] {limit_breached}")
                bot.state = "HALTED"
                await _close_all_mine(account_id, pair)
                await _delete_my_stop_pendings(resolved)
                _set_bot_runtime(bot_id, bot.state, limit_breached, None, bot.reversals_count)
                await asyncio.sleep(30)
                continue

            if bot.state == "HALTED":
                _set_bot_runtime(bot_id, bot.state, bot.last_msg or "Halted until next server day.", None, bot.reversals_count)
                await asyncio.sleep(15)
                continue

            digits = int(getattr(sym_info, "digits", 5) or 5)
            point = float(getattr(sym_info, "point", 10 ** -digits) or (10 ** -digits))
            tick_size = float(getattr(sym_info, "trade_tick_size", 0.0) or 0.0)
            stops_level = int(getattr(sym_info, "trade_stops_level", 0) or 0)
            freeze_level = int(getattr(sym_info, "trade_freeze_level", 0) or 0)
            vol_min = float(getattr(sym_info, "volume_min", 0.01) or 0.01)
            vol_max = float(getattr(sym_info, "volume_max", 100.0) or 100.0)
            vol_step = float(getattr(sym_info, "volume_step", 0.01) or 0.01)
            trade_mode_full = (getattr(sym_info, "trade_mode", 0) == mod.SYMBOL_TRADE_MODE_FULL)

            pip_unit = bot.detect_pip(resolved, digits, point)
            min_d = bot.min_stop_dist(stops_level, freeze_level, point)
            lots = bot.norm_lots(vol_min, vol_max, vol_step)
            dev_pts = bot.deviation_points(pip_unit, point)
            spread = float(tick.ask - tick.bid)

            terminal_allowed = bool(getattr(t_info, "trade_allowed", False)) if t_info else False
            tradeapi_disabled = bool(getattr(t_info, "tradeapi_disabled", False)) if t_info else False
            acct_trade_allowed = bool(getattr(a_info, "trade_allowed", False))
            acct_trade_expert = bool(getattr(a_info, "trade_expert", False))

            # 2. Check active positions matching BOTH symbol AND magic
            positions = await mt5.get_positions(account_id)
            my_positions = [
                p for p in positions
                if p.get("magic") == bot.magic_number and _symbols_match(p.get("symbol", ""), pair)
            ]

            # --- STEP 1: POSITION EXISTS (IN_TRADE) ---
            if my_positions:
                pos = my_positions[0]
                pos_ticket = int(pos["ticket"])
                pos_identifier = int(pos.get("identifier") or pos_ticket)
                pos_dir = 1 if pos["type"].upper() == "BUY" else -1
                pos_open = float(pos["open_price"])
                cur_sl = float(pos.get("stop_loss", 0.0) or 0.0)

                if bot.state != "IN_TRADE":
                    bot.state = "IN_TRADE"
                    bot.pos_id = pos_identifier
                    bot.last_dir = pos_dir
                    bot.open_price = pos_open
                    bot.close_start_time = 0.0
                    open_msg = f"Position #{pos_identifier} opened ({pos['type']} @ {pos_open})."
                    bot.set_msg(open_msg, now_ts)
                    await _delete_my_stop_pendings(resolved)
                    await _ensure_trade_recorded(
                        account_id, user_id, resolved, pos["type"], float(pos["volume"]), pos_open, cur_sl, pos_identifier,
                        f"PipStep {'Reversal #' + str(bot.reversals_count) if bot.reversals_count > 0 else 'Straddle Fill'}"
                    )

                # Periodic cleanup of any leftover stop pending orders while in trade
                if now_ts >= bot.next_clean_time:
                    bot.next_clean_time = now_ts + 2.0
                    await _delete_my_stop_pendings(resolved)

                # Step Trailing SL (plus initial SL recovery if SL==0)
                if now_ts >= bot.next_modify_time:
                    cur_price = float(tick.bid) if pos_dir > 0 else float(tick.ask)
                    desired_sl = bot.calculate_step_trailing_sl(
                        direction=pos_dir,
                        open_price=pos_open,
                        current_sl=cur_sl,
                        current_price=cur_price,
                        pip_unit=pip_unit,
                        min_stop_dist=min_d,
                        tick_size=tick_size,
                        digits=digits,
                        cur_bid=float(tick.bid),
                        cur_ask=float(tick.ask),
                    )
                    if desired_sl is not None:
                        mod_res = await mt5.modify_sl_tp(account_id, str(pos_ticket), stop_loss=desired_sl)
                        if mod_res.get("success"):
                            msg = f"Trailing SL moved to {desired_sl} on #{pos_ticket}"
                            bot.set_msg(msg, now_ts)
                        else:
                            bot.next_modify_time = now_ts + 5.0
                            bot.set_msg(f"SL modify rejected: {mod_res.get('error')}", now_ts)

                _set_bot_runtime(bot_id, bot.state, bot.last_msg, None, bot.reversals_count)
                await asyncio.sleep(1)
                continue

            # --- STEP 2: POSITION CLOSED (CLASSIFY REASON, WAIT UP TO 3s FOR HISTORY LAG) ---
            if bot.state == "IN_TRADE":
                if bot.close_start_time == 0.0:
                    bot.close_start_time = now_ts
                close_info = await mt5.get_history_deal_close_details(bot.pos_id)
                if close_info is None and (now_ts - bot.close_start_time) < 3.0:
                    await asyncio.sleep(0.5)
                    continue

                bot.close_start_time = 0.0

                # Update closed trade record in DB
                if close_info and user_id:
                    try:
                        await asyncio.to_thread(
                            lambda: supabase.table("trades").update({
                                "status": "closed",
                                "close_price": close_info.get("close_price"),
                                "profit": close_info.get("profit"),
                                "closed_at": datetime.utcnow().isoformat(),
                            }).eq("user_id", user_id).eq("ticket", str(bot.pos_id)).execute()
                        )
                    except Exception:
                        pass

                deal_reason = close_info.get("reason") if close_info else -1
                if close_info is not None and deal_reason == getattr(mod, "DEAL_REASON_SL", 4):
                    bot.next_dir = -bot.last_dir
                    bot.state = "NEED_REVERSAL"
                    bot.reversals_count += 1
                    msg = f"SL hit on #{bot.pos_id}. Reversing immediately to {'BUY' if bot.next_dir > 0 else 'SELL'}."
                    bot.set_msg(msg, now_ts)
                else:
                    bot.state = "ARMED"
                    msg = f"Position #{bot.pos_id} closed (reason={deal_reason}). Re-arming pending pair."
                    bot.set_msg(msg, now_ts)
                _set_bot_runtime(bot_id, bot.state, msg, None, bot.reversals_count)

            # --- STEP 3: NEED_REVERSAL -> OPEN MARKET ORDER ---
            if bot.state == "NEED_REVERSAL":
                can_ok, block_msg = bot.can_send(
                    now_ts, terminal_allowed, tradeapi_disabled,
                    acct_trade_allowed, acct_trade_expert, trade_mode_full, spread, pip_unit
                )
                if not can_ok:
                    _set_bot_runtime(bot_id, bot.state, block_msg or bot.last_msg, bot.last_fail_retcode, bot.reversals_count)
                    await asyncio.sleep(2)
                    continue

                rev_type = "BUY" if bot.next_dir > 0 else "SELL"
                price = float(tick.ask) if bot.next_dir > 0 else float(tick.bid)
                sld = bot.sl_pips * pip_unit
                min_sld = min_d + spread
                if sld < min_sld:
                    sld = min_sld + point
                sl_price = bot.norm_price(price - bot.next_dir * sld, tick_size, digits)

                ot_enum = mod.ORDER_TYPE_BUY if bot.next_dir > 0 else mod.ORDER_TYPE_SELL
                req_margin = mod.order_calc_margin(ot_enum, resolved, lots, price)
                if req_margin is None or req_margin > margin_free * 0.9:
                    bot.next_try_time = now_ts + 60.0
                    msg = "Not enough free margin for reversal."
                    bot.set_msg(msg, now_ts)
                    _set_bot_runtime(bot_id, bot.state, msg, 10019, bot.reversals_count)
                    await asyncio.sleep(2)
                    continue

                order_res = await mt5.place_order(
                    account_id=account_id,
                    pair=resolved,
                    order_type=rev_type,
                    volume=lots,
                    stop_loss=sl_price,
                    take_profit=0.0,
                    comment=f"{bot.comment} Rev#{bot.reversals_count}",
                    magic=bot.magic_number,
                    deviation=dev_pts,
                )

                if order_res.get("success"):
                    bot.on_send_ok()
                    # Re-check SelectMyPosition to capture true POSITION_IDENTIFIER just like EA
                    after_positions = await mt5.get_positions(account_id)
                    mine_after = [
                        p for p in after_positions
                        if p.get("magic") == bot.magic_number and _symbols_match(p.get("symbol", ""), pair)
                    ]
                    if mine_after:
                        p0 = mine_after[0]
                        pos_ident = int(p0.get("identifier") or p0["ticket"])
                        bot.state = "IN_TRADE"
                        bot.last_dir = 1 if p0["type"].upper() == "BUY" else -1
                        bot.pos_id = pos_ident
                        bot.open_price = float(p0["open_price"])
                        bot.close_start_time = 0.0
                        msg = f"Reversal {p0['type']} #{pos_ident} opened @ {bot.open_price} (SL {sl_price})."
                    else:
                        pos_ident = int(order_res.get("ticket") or 0)
                        bot.state = "IN_TRADE"
                        bot.last_dir = bot.next_dir
                        bot.pos_id = pos_ident
                        bot.open_price = price
                        bot.close_start_time = 0.0
                        msg = f"Reversal {rev_type} #{pos_ident} opened @ {price} (SL {sl_price})."

                    bot.set_msg(msg, now_ts)
                    await _delete_my_stop_pendings(resolved)
                    await _ensure_trade_recorded(
                        account_id, user_id, resolved, rev_type, lots, bot.open_price, sl_price, pos_ident,
                        f"PipStep Reversal #{bot.reversals_count}"
                    )
                    _set_bot_runtime(bot_id, bot.state, msg, None, bot.reversals_count)
                else:
                    bot.on_send_fail(order_res.get("retcode"), order_res.get("error", "order failed"), now_ts)
                    _set_bot_runtime(bot_id, bot.state, bot.last_msg, order_res.get("retcode"), bot.reversals_count)

                await asyncio.sleep(1)
                continue

            # --- STEP 4: ARMED -> ENSURE SYMMETRICAL BUYSTOP + SELLSTOP PAIR ---
            if bot.state == "ARMED":
                pendings = await mt5.get_pending_orders(symbol=resolved, magic=bot.magic_number)
                buy_stops = [p for p in pendings if p.get("type") == "BUY_STOP"]
                sell_stops = [p for p in pendings if p.get("type") == "SELL_STOP"]
                other_stops = [p for p in pendings if p.get("type") not in ("BUY_STOP", "SELL_STOP")]

                if len(buy_stops) == 1 and len(sell_stops) == 1 and not other_stops:
                    pair_msg = (
                        f"Armed & waiting for trigger: BuyStop @ {buy_stops[0]['price_open']}, "
                        f"SellStop @ {sell_stops[0]['price_open']}"
                    )
                    _set_bot_runtime(bot_id, bot.state, pair_msg, None, bot.reversals_count)
                    await asyncio.sleep(2)
                    continue

                if buy_stops or sell_stops:
                    await _delete_my_stop_pendings(resolved)
                    await asyncio.sleep(0.5)

                can_ok, block_msg = bot.can_send(
                    now_ts, terminal_allowed, tradeapi_disabled,
                    acct_trade_allowed, acct_trade_expert, trade_mode_full, spread, pip_unit
                )
                if not can_ok:
                    _set_bot_runtime(bot_id, bot.state, block_msg or bot.last_msg, bot.last_fail_retcode, bot.reversals_count)
                    await asyncio.sleep(2)
                    continue

                dist = bot.entry_pips * pip_unit
                sld = bot.sl_pips * pip_unit
                min_sld = min_d + spread
                if dist < min_sld:
                    dist = min_sld + point
                if sld < min_sld:
                    sld = min_sld + point

                buy_p = bot.norm_price(float(tick.ask) + dist, tick_size, digits)
                sell_p = bot.norm_price(float(tick.bid) - dist, tick_size, digits)
                buy_sl = bot.norm_price(buy_p - sld, tick_size, digits)
                sell_sl = bot.norm_price(sell_p + sld, tick_size, digits)

                m_buy = mod.order_calc_margin(mod.ORDER_TYPE_BUY, resolved, lots, buy_p)
                m_sell = mod.order_calc_margin(mod.ORDER_TYPE_SELL, resolved, lots, sell_p)
                if m_buy is None or m_sell is None or m_buy > margin_free * 0.9 or m_sell > margin_free * 0.9:
                    bot.next_try_time = now_ts + 60.0
                    msg = "Not enough free margin for the pending pair."
                    bot.set_msg(msg, now_ts)
                    _set_bot_runtime(bot_id, bot.state, msg, 10019, bot.reversals_count)
                    await asyncio.sleep(2)
                    continue

                res1 = await mt5.place_pending_order(
                    account_id=account_id,
                    pair=resolved,
                    order_type="BUY_STOP",
                    volume=lots,
                    price=buy_p,
                    stop_loss=buy_sl,
                    take_profit=0.0,
                    magic=bot.magic_number,
                    comment=bot.comment,
                    deviation=dev_pts,
                )

                if res1.get("success"):
                    res2 = await mt5.place_pending_order(
                        account_id=account_id,
                        pair=resolved,
                        order_type="SELL_STOP",
                        volume=lots,
                        price=sell_p,
                        stop_loss=sell_sl,
                        take_profit=0.0,
                        magic=bot.magic_number,
                        comment=bot.comment,
                        deviation=dev_pts,
                    )
                    if not res2.get("success"):
                        await mt5.delete_pending_order(res1["ticket"])
                        bot.on_send_fail(res2.get("retcode"), res2.get("error", "SellStop failed"), now_ts)
                        _set_bot_runtime(bot_id, bot.state, bot.last_msg, res2.get("retcode"), bot.reversals_count)
                    else:
                        bot.on_send_ok()
                        msg = f"Pair placed: BuyStop @ {buy_p} (SL {buy_sl}), SellStop @ {sell_p} (SL {sell_sl})"
                        bot.set_msg(msg, now_ts)
                        _set_bot_runtime(bot_id, bot.state, msg, None, bot.reversals_count)
                else:
                    bot.on_send_fail(res1.get("retcode"), res1.get("error", "BuyStop failed"), now_ts)
                    _set_bot_runtime(bot_id, bot.state, bot.last_msg, res1.get("retcode"), bot.reversals_count)

            await asyncio.sleep(1)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"[pipstep_reversal {bot_id}] Fatal: {e}")
        _set_bot_runtime(bot_id, "ERROR", str(e), None, bot.reversals_count)
        try:
            supabase.table("bot_settings").update({"status": "error"}).eq("id", bot_id).execute()
        except Exception as db_e:
            logger.error(f"Database error: {db_e}")
    finally:
        _bot_runtime_status.pop(bot_id, None)
        if bot.delete_on_remove and _last_resolved_sym:
            try:
                await _delete_my_stop_pendings(_last_resolved_sym)
            except Exception:
                pass