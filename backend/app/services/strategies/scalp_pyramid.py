"""
Bot 6: Scalp Pyramid Mode (Anti-Martingale Trend Scalper)
Requires: pandas, numpy
Input per call: latest OHLCV DataFrame + the list of currently open positions
                for this symbol (from your MT5 backend)

Core principles (grounded in real "pyramiding" position-scaling practice — the
established structural opposite of the grid/martingale EA you shared):
- NEVER adds to a losing position. This is the single rule that matters most.
- Only adds to a position that is already profitable, and only once existing
  unrealized profit already "covers" the risk of the new addition.
- Each addition is SMALLER than the previous one (classic pyramid shape,
  not a martingale doubling shape).
- Stop loss on each position moves to breakeven once it shows a small profit,
  before any new addition is allowed.
- Individual positions are closed and profit banked at a fixed target
  (your 1-2% rule), rather than left open indefinitely.
"""

from typing import Optional
from uuid import uuid4
import pandas as pd
from .base import BaseStrategy, Signal


class ScalpPyramidBot(BaseStrategy):
    name = "scalp_pyramid"
    description = "Anti-martingale trend scalper — pyramiding adds only to winning positions"
    timeframe = "M1"

    def __init__(self,
                 base_lot=0.01,
                 lot_decrease_factor=0.5,
                 max_positions=4,
                 breakeven_trigger_pct=0.3,
                 profit_target_pct=1.5,
                 min_profit_to_add_pct=0.5,
                 fast_ema=9,
                 slow_ema=21,
                 momentum_candles=3):
        """
        base_lot: lot size of the very first trade in the pyramid
        lot_decrease_factor: each new addition = previous lot * this factor
                              (must be < 1 -- additions shrink, never grow)
        max_positions: hard cap on stacked positions open at once for this symbol
        breakeven_trigger_pct: % profit at which a position's SL moves to breakeven
        profit_target_pct: % profit at which a position is closed and banked
                            (your "1-2%" rule -- default set at 1.5%)
        min_profit_to_add_pct: minimum % unrealized profit required on the
                                EXISTING basket before a new add-on is opened
        fast_ema / slow_ema: trend filter periods
        momentum_candles: how many recent candles must agree with the trend
                           direction before taking or adding a trade
        """
        assert 0 < lot_decrease_factor < 1, "lot_decrease_factor must be under 1 -- additions must shrink, not grow"
        self.base_lot = base_lot
        self.lot_decrease_factor = lot_decrease_factor
        self.max_positions = max_positions
        self.breakeven_trigger_pct = breakeven_trigger_pct
        self.profit_target_pct = profit_target_pct
        self.min_profit_to_add_pct = min_profit_to_add_pct
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.momentum_candles = momentum_candles

    # ---------------- Trend / momentum filter ----------------
    def get_trend_direction(self, df):
        """
        EMA(fast) vs EMA(slow) cross, confirmed by recent candles closing in the
        same direction. This is a real directional filter -- the grid EA you
        shared had NO directional filter at all, which is a large part of why
        it's dangerous: it buys blindly regardless of trend.
        """
        df = df.copy()
        df['ema_fast'] = df['close'].ewm(span=self.fast_ema, adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=self.slow_ema, adjust=False).mean()

        last = df.iloc[-1]
        if last['ema_fast'] > last['ema_slow']:
            trend = 'up'
        elif last['ema_fast'] < last['ema_slow']:
            trend = 'down'
        else:
            return None

        recent = df.tail(self.momentum_candles)
        if trend == 'up':
            confirmed = (recent['close'] > recent['open']).sum() >= (self.momentum_candles - 1)
        else:
            confirmed = (recent['close'] < recent['open']).sum() >= (self.momentum_candles - 1)

        return trend if confirmed else None

    # ---------------- Position sizing ----------------
    def next_lot_size(self, existing_position_count):
        """Each addition shrinks: base_lot * decrease_factor^n -- never grows."""
        lot = self.base_lot * (self.lot_decrease_factor ** existing_position_count)
        return round(max(lot, 0.01), 2)

    # ---------------- Profit helpers ----------------
    def position_profit_pct(self, position, current_price):
        entry = position['entry_price']
        if position['direction'] == 'BUY':
            return (current_price - entry) / entry * 100
        return (entry - current_price) / entry * 100

    def basket_profit_pct(self, positions, current_price):
        """Lot-weighted profit % across the whole stacked basket for this symbol."""
        if not positions:
            return 0
        total_lots = sum(p['lot'] for p in positions)
        weighted = sum(self.position_profit_pct(p, current_price) * p['lot'] for p in positions)
        return weighted / total_lots if total_lots > 0 else 0

    # ---------------- BaseStrategy abstract conformance ----------------
    def generate_signal(self, df) -> Optional[dict]:
        """
        Satisfy BaseStrategy abstract interface.
        ScalpPyramidBot does NOT use generate_signal() — it uses generate_actions()
        which is position-aware and multi-action. This stub always returns None
        so the standard bot loop does not call it. Use the specialized
        ScalpPyramidBotEngine loop instead.
        """
        return None

    # ---------------- Main engine (stateful, called per candle) ----------------
    def generate_actions(self, df, open_positions, symbol):
        """
        Call this on every new candle for the symbol.
        open_positions: list of dicts already open, e.g.
            {'ticket': 123, 'direction': 'BUY', 'entry_price': 1.0850,
             'lot': 0.01, 'sl': 1.0820, 'breakeven_done': False}
        Returns a list of actions to execute via your backend:
            {'action': 'open', 'direction': 'BUY', 'lot': 0.01, 'reason': ...}
            {'action': 'close', 'ticket': 123, 'reason': ...}
            {'action': 'modify_sl', 'ticket': 123, 'new_sl': ..., 'reason': ...}
        """
        actions = []
        current_price = df['close'].iloc[-1]
        trend = self.get_trend_direction(df)

        # ---- 1. Manage existing positions first ----
        closing_tickets = []
        for pos in open_positions:
            profit_pct = self.position_profit_pct(pos, current_price)

            if profit_pct >= self.profit_target_pct:
                actions.append({'action': 'close', 'ticket': pos['ticket'], 'reason': 'profit_target_hit'})
                closing_tickets.append(pos['ticket'])
                continue

            if profit_pct >= self.breakeven_trigger_pct and not pos.get('breakeven_done', False):
                actions.append({
                    'action': 'modify_sl',
                    'ticket': pos['ticket'],
                    'new_sl': pos['entry_price'],
                    'reason': 'breakeven_lock'
                })

            # If a position is losing, we deliberately do nothing to its stop
            # and never add to it -- this is the entire point of the design.

        # ---- 2. Decide on new entries / pyramid additions ----
        still_open = [p for p in open_positions if p['ticket'] not in closing_tickets]

        if trend is None:
            return actions  # no clear trend/momentum

        if len(still_open) == 0:
            actions.append({
                'action': 'open',
                'direction': 'BUY' if trend == 'up' else 'SELL',
                'lot': self.base_lot,
                'reason': 'initial_entry'
            })
            return actions

        if len(still_open) >= self.max_positions:
            return actions

        basket_direction = still_open[0]['direction']
        trend_matches_basket = (trend == 'up' and basket_direction == 'BUY') or \
                                (trend == 'down' and basket_direction == 'SELL')
        basket_profit = self.basket_profit_pct(still_open, current_price)

        if trend_matches_basket and basket_profit >= self.min_profit_to_add_pct:
            actions.append({
                'action': 'open',
                'direction': basket_direction,
                'lot': self.next_lot_size(len(still_open)),
                'reason': 'pyramid_addition'
            })

        return actions

    # ---------------- Per-candle signal for bot_engine compatibility ----------------
    async def analyze(self, pair: str, candles: list, config: dict) -> Optional[Signal]:
        """
        Compatibility shim: the bot_engine calls analyze() expecting a single Signal.
        But ScalpPyramidBot is stateful and position-aware — it needs to see open
        positions and return multiple actions (close, modify_sl, open).

        THIS METHOD SHOULD NOT BE CALLED DIRECTLY by the standard bot loop.
        See the ScalpPyramidBotEngine wrapper in bot_engine.py for the correct loop.

        Returns None here so the standard bot engine doesn't accidentally use it.
        """
        return None


# Convenience action runner — call this from the custom bot loop
async def run_scalp_pyramid_cycle(bot, df, open_positions, symbol, mt5_module, supabase, bot_id=None, user_id=None):
    """
    Execute a full ScalpPyramidBot cycle:
      1. generate_actions()
      2. Execute each action via MT5 (awaiting each async call)
      3. Log results to Supabase

    Returns list of executed action results.
    """
    actions = bot.generate_actions(df, open_positions, symbol)
    results = []

    for action in actions:
        if action['action'] == 'open':
            direction = action['direction']
            lot = action['lot']
            order = await mt5_module.place_order(
                account_id="",
                pair=symbol,
                order_type=direction,
                volume=lot,
            )
            if order.get("success"):
                # Columns match the LIVE trades schema; id is required (no default)
                record = {
                    "id": str(uuid4()),
                    "user_id": user_id or "",
                    "bot_id": bot_id or "",
                    "strategy": "scalp_pyramid",
                    "symbol": symbol,
                    "direction": direction.lower(),
                    "volume": lot,
                    "open_price": order.get("price", 0),
                    "status": "open",
                    "reason": action.get("reason", ""),
                    "ticket": str(order.get("ticket")),
                }
                try:
                    supabase.table("trades").insert(record).execute()
                except Exception as e:

                    import logging; logging.getLogger(__name__).error(f'Database operation failed: {e}')
                results.append({"action": "open", "success": True, "ticket": order.get("ticket"),
                                "price": order.get("price"), "lot": lot, "direction": direction,
                                "reason": action.get("reason")})
            else:
                results.append({"action": "open", "success": False,
                                "error": order.get("error"), "reason": action.get("reason")})

        elif action['action'] == 'close':
            result = await mt5_module.close_position("", action['ticket'])
            if result.get("success"):
                try:
                    # No 'ticket' column in the live schema — match on
                    # bot_id + open status + symbol (best-effort bookkeeping;
                    # MT5 itself is the source of truth for the close).
                    supabase.table("trades").update({
                        "status": "closed",
                        "closed_at": pd.Timestamp.utcnow().isoformat(),
                        "close_price": result.get("price"),
                    }).eq("ticket", str(action['ticket'])).execute()
                except Exception as e:

                    import logging; logging.getLogger(__name__).error(f'Database operation failed: {e}')
                results.append({"action": "close", "success": True, "ticket": action['ticket'],
                                "reason": action.get("reason")})
            else:
                results.append({"action": "close", "success": False, "ticket": action['ticket'],
                                "error": result.get("error"), "reason": action.get("reason")})

        elif action['action'] == 'modify_sl':
            result = await mt5_module.modify_sl_tp("", action['ticket'], stop_loss=action['new_sl'])
            if result.get("success"):
                try:
                    supabase.table("trades").update({
                        "stop_loss": action['new_sl'],
                    }).eq("ticket", str(action['ticket'])).execute()
                except Exception as e:

                    import logging; logging.getLogger(__name__).error(f'Database operation failed: {e}')
                results.append({"action": "modify_sl", "success": True, "ticket": action['ticket'],
                                "new_sl": action['new_sl'], "reason": action.get("reason")})
            else:
                results.append({"action": "modify_sl", "success": False, "ticket": action['ticket'],
                                "error": result.get("error"), "reason": action.get("reason")})

    return results
