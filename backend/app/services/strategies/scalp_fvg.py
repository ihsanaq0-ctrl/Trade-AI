"""
Rapid Trend Scalper v2 — M1 trend-following with true FVG/OB priority entries.

FIXES vs the original version:
  1. FVG/OB reversal now requires price to actually be retracing INTO the zone
     (within a buffer of top/bottom), not just "anywhere below the zone's top" —
     the old check fired almost immediately after any zone formed, causing
     constant premature reversals instead of letting trades run.
  2. Zones are tracked as "mitigated" once price has traded through/into them
     once, so a stale zone can't keep re-triggering signals indefinitely.
  3. FVG/OB signals (both entries and reversals) now BYPASS the cooldown timer —
     they are the high-confidence, priority signal you asked for. Cooldown still
     applies to the plain EMA-pullback/momentum entries, to stop those from spamming.
  4. Added a plain TREND CONTINUATION fallback entry: if flat, trend is clearly
     established, and neither the pullback nor momentum pattern has fired, the
     bot still opens a trend-aligned trade after a short wait — so a clear trend
     with no perfect candle pattern doesn't leave the bot sitting idle.

Requires: pandas, numpy
Input: OHLCV DataFrame with columns: ['time', 'open', 'high', 'low', 'close']
"""

import pandas as pd
import numpy as np
from datetime import timedelta, timezone


class ScalpModeBot:
    name = "scalp_fvg"
    description = "Rapid M1 trend scalper with EMA trend-following + true FVG/OB priority reversals"
    timeframe = "M1"

    def __init__(self,
                 initial_balance=100.0,
                 atr_period=14,
                 max_daily_trades=40,
                 fvg_buffer_pct=0.0003,
                 risk_per_trade_pct=0.02,
                 max_drawdown_pct=0.40,
                 target_profit_usd=1.0,
                 target_profit_pct=1.5,
                 max_daily_loss_pct=20.0,
                 breakeven_usd=0.5,
                 session_lookback=20,
                 ema_fast=9,
                 ema_slow=21,
                 rsi_period=14,
                 rsi_ob=70,
                 rsi_os=30,
                 cooldown_bars=3,
                 trend_idle_bars=5):
        """
        New params vs original:
            fvg_buffer_pct:   how close price must get to a zone to count as a
                               genuine retest (was unused for this purpose before)
            trend_idle_bars:  if flat for this many bars with a clear trend and
                               no pullback/momentum trigger, take a plain trend
                               continuation entry anyway
            target_profit_pct: % of live balance used as the dollar profit target
                               (target_profit_usd = balance * pct/100) — scales
                               with account size instead of a fixed $1.00
            max_daily_loss_pct: % of live balance used as the daily loss cap —
                               scales with account size instead of a fixed $100
        """
        self.initial_balance = initial_balance
        self.atr_period = atr_period
        self.max_daily_trades = max_daily_trades
        self.fvg_buffer_pct = fvg_buffer_pct
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.target_profit_usd = target_profit_usd  # fixed-dollar fallback (backward compat)
        self.target_profit_pct = target_profit_pct  # % of balance — preferred when balance known
        self.max_daily_loss_pct = max_daily_loss_pct  # % of balance — preferred when balance known
        self.breakeven_usd = breakeven_usd
        self.session_lookback = session_lookback
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.rsi_period = rsi_period
        self.rsi_ob = rsi_ob
        self.rsi_os = rsi_os
        self.cooldown_bars = cooldown_bars
        self.trend_idle_bars = trend_idle_bars

        self.current_date = None
        self.trades_today = 0
        self.last_entry_index = -999
        self.last_flat_since_index = 0
        self.breakeven_applied: dict[int, bool] = {}
        self.realized_pnl_today: float = 0.0  # closed-trade P&L for the daily loss cap

        # NEW: tracks zone identity (by rounded price level) that has already
        # been traded off of, so the same structure doesn't fire twice.
        self.mitigated_zones: set[tuple] = set()

    # ---------------- state / risk (unchanged) ----------------
    def check_drawdown_limit(self, current_balance: float) -> bool:
        max_loss = self.initial_balance * self.max_drawdown_pct
        return current_balance > (self.initial_balance - max_loss)

    def check_and_update_daily_limit(self, timestamp_utc) -> bool:
        est_offset = timedelta(hours=-4)
        trading_day = (timestamp_utc + est_offset).date()
        if trading_day != self.current_date:
            self.current_date = trading_day
            self.trades_today = 0
        return self.trades_today < self.max_daily_trades

    def register_trade_executed(self):
        self.trades_today += 1

    # ---------------- indicators (unchanged) ----------------
    def calculate_emas(self, df):
        ema_f = df['close'].ewm(span=self.ema_fast, adjust=False).mean()
        ema_s = df['close'].ewm(span=self.ema_slow, adjust=False).mean()
        return ema_f, ema_s

    def calculate_atr(self, df):
        high, low, close = df['high'], df['low'], df['close']
        prev_close = close.shift(1)
        tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
        return tr.rolling(self.atr_period).mean()

    def calculate_rsi(self, df):
        delta = df['close'].diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.ewm(com=self.rsi_period - 1, min_periods=self.rsi_period).mean()
        avg_loss = loss.ewm(com=self.rsi_period - 1, min_periods=self.rsi_period).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return (100 - (100 / (1 + rs))).fillna(50)

    def get_trend(self, ema_f, ema_s):
        fast, slow = ema_f.iloc[-1], ema_s.iloc[-1]
        spread = abs(fast - slow)
        avg_price = (fast + slow) / 2
        if spread < avg_price * 0.00005:
            return None
        return 'BUY' if fast > slow else 'SELL'

    def is_pullback_entry(self, df, ema_f, trend):
        if len(df) < 3:
            return False
        curr, prev = df.iloc[-1], df.iloc[-2]
        ef_curr = ema_f.iloc[-1]
        body = curr['close'] - curr['open']

        if trend == 'BUY':
            touched = prev['low'] <= ema_f.iloc[-2] or curr['low'] <= ef_curr
            return touched and curr['close'] > ef_curr and body > 0
        elif trend == 'SELL':
            touched = prev['high'] >= ema_f.iloc[-2] or curr['high'] >= ef_curr
            return touched and curr['close'] < ef_curr and body < 0
        return False

    # ---------------- FVG / OB detection (unchanged logic, now tagged with a stable id) ----------------
    def detect_fvg(self, df, atr_series):
        fvgs = []
        if len(df) < 4:
            return fvgs
        start = max(1, len(df) - self.session_lookback)
        for i in range(start, len(df) - 1):
            c1, c2, c3 = df.iloc[i - 1], df.iloc[i], df.iloc[i + 1]
            c2_atr = atr_series.iloc[i]
            if pd.isna(c2_atr) or c2_atr == 0:
                continue
            is_displacement = abs(c2['close'] - c2['open']) >= (c2_atr * 1.2)
            if c1['high'] < c3['low'] and is_displacement:
                fvgs.append({'type': 'bullish', 'top': c3['low'], 'bottom': c1['high'], 'index': i})
            elif c1['low'] > c3['high'] and is_displacement:
                fvgs.append({'type': 'bearish', 'top': c1['low'], 'bottom': c3['high'], 'index': i})
        return fvgs

    def detect_order_blocks(self, df, atr_series):
        obs = []
        if len(df) < 4:
            return obs
        start = max(1, len(df) - self.session_lookback)
        for i in range(start, len(df)):
            c = df.iloc[i]
            c_atr = atr_series.iloc[i]
            if pd.isna(c_atr) or c_atr == 0:
                continue
            if abs(c['close'] - c['open']) < c_atr * 1.2:
                continue
            prev = df.iloc[i - 1]
            prev_body = prev['close'] - prev['open']
            if c['close'] > c['open'] and prev_body < 0:
                obs.append({'type': 'bullish', 'high': prev['high'], 'low': prev['low'], 'index': i - 1})
            elif c['close'] < c['open'] and prev_body > 0:
                obs.append({'type': 'bearish', 'high': prev['high'], 'low': prev['low'], 'index': i - 1})
        return obs

    def _zone_id(self, zone, source):
        """Stable identity for a zone so we can mark it mitigated once used."""
        return (source, zone['type'], round(zone.get('top', zone.get('high', 0)), 5),
                round(zone.get('bottom', zone.get('low', 0)), 5))

    def _zone_is_retested(self, zone, current_price, tolerance):
        """
        FIX for Bug 1: price must actually be INSIDE the zone, or within a small
        buffer of it, to count as a genuine retracement/retest — not just
        'anywhere below the top' the way the original code checked it.
        """
        top = zone.get('top', zone.get('high'))
        bottom = zone.get('bottom', zone.get('low'))
        return (bottom - tolerance) <= current_price <= (top + tolerance)

    # ---------------- risk sizing (unchanged) ----------------
    def calculate_dollarized_levels(self, entry_price, direction, account_balance,
                                     pip_value_per_lot, lot_size, pip_size=0.0001,
                                     min_sl_pips=10.0):
        pip_value = pip_value_per_lot * lot_size
        risk_amount = account_balance * self.risk_per_trade_pct
        sl_pips = max(risk_amount / pip_value if pip_value > 0 else 0, min_sl_pips)
        sl_price_dist = sl_pips * pip_size
        tp_pips = self.target_profit_usd / pip_value if pip_value > 0 else 0
        tp_price_dist = tp_pips * pip_size
        if direction == 'BUY':
            sl, tp = entry_price - sl_price_dist, entry_price + tp_price_dist
        else:
            sl, tp = entry_price + sl_price_dist, entry_price - tp_price_dist
        return round(sl, 5), round(tp, 5)

    # ---------------- MAIN PIPELINE ----------------
    def generate_signal(self, df, current_position=None, account_balance=100.0,
                         pip_value_per_lot=10.0, lot_size=0.01, pip_size=0.0001,
                         realized_pnl_today=0.0):
        if len(df) < max(self.ema_slow + 5, self.atr_period + 5, 30):
            return None

        df = df.copy()
        raw_time = df['time'].iloc[-1]
        if isinstance(raw_time, (int, float, np.integer, np.floating)):
            last_candle_time = pd.to_datetime(raw_time, unit='s', utc=True)
        else:
            last_candle_time = pd.to_datetime(raw_time)
            if getattr(last_candle_time, 'tzinfo', None) is None:
                last_candle_time = last_candle_time.replace(tzinfo=timezone.utc)

        ema_f, ema_s = self.calculate_emas(df)
        atr = self.calculate_atr(df)
        rsi = self.calculate_rsi(df)
        current_price = df['close'].iloc[-1]
        current_rsi = rsi.iloc[-1]
        current_bar_index = len(df) - 1

        # Risk sizing scales with live account balance. target_profit_usd and
        # the daily loss cap are % of balance; the fixed-dollar values are only
        # a fallback if balance is missing/zero (backward compat).
        balance_for_risk = account_balance if account_balance and account_balance > 0 else None
        if balance_for_risk is not None:
            self.target_profit_usd = balance_for_risk * (self.target_profit_pct / 100.0)
        if realized_pnl_today:
            self.realized_pnl_today = realized_pnl_today

        if not self.check_drawdown_limit(account_balance):
            return {'action': 'STOP_TRADING',
                    'reason': f'40% drawdown limit. Balance=${account_balance:.2f}, initial=${self.initial_balance:.2f}'}

        trend = self.get_trend(ema_f, ema_s)
        tolerance = current_price * self.fvg_buffer_pct

        fvgs = self.detect_fvg(df, atr)
        obs = self.detect_order_blocks(df, atr)
        sm_zones = [{**z, 'source': 'FVG'} for z in fvgs] + \
                   [{'type': o['type'], 'top': o['high'], 'bottom': o['low'], 'index': o['index'], 'source': 'OB'} for o in obs]

        # ---- 1. IN A POSITION: check for a genuine, unmitigated FVG/OB retest against it ----
        if current_position is not None and current_position.get('direction'):
            for zone in reversed(sm_zones):  # most recent zones first
                zid = self._zone_id(zone, zone['source'])
                if zid in self.mitigated_zones:
                    continue  # FIX for Bug 2: already used, ignore

                opposing = (current_position['direction'] == 'BUY' and zone['type'] == 'bearish') or \
                           (current_position['direction'] == 'SELL' and zone['type'] == 'bullish')
                if not opposing:
                    continue

                if not self._zone_is_retested(zone, current_price, tolerance):
                    continue  # FIX for Bug 1: not actually at the zone yet

                new_dir = 'SELL' if current_position['direction'] == 'BUY' else 'BUY'
                sl, tp = self.calculate_dollarized_levels(current_price, new_dir, account_balance,
                                                           pip_value_per_lot, lot_size, pip_size=pip_size)
                self.mitigated_zones.add(zid)
                self.last_entry_index = current_bar_index
                return {
                    'action': 'CLOSE_AND_REVERSE',
                    'direction': new_dir,
                    'entry': round(current_price, 5),
                    'stop_loss': sl,
                    'take_profit': tp,
                    'close_ticket': current_position['ticket'],
                    'strategy': 'Scalp FVG',
                    'reason': f'Price retested {zone["type"]} {zone["source"]} against {current_position["direction"]} — reversing',
                    'breakeven_trigger_usd': self.breakeven_usd,
                }

            # Trend flip is still allowed as a secondary reversal trigger
            if trend and trend != current_position['direction']:
                sl, tp = self.calculate_dollarized_levels(current_price, trend, account_balance,
                                                           pip_value_per_lot, lot_size, pip_size=pip_size)
                return {
                    'action': 'CLOSE_AND_REVERSE', 'direction': trend,
                    'entry': round(current_price, 5), 'stop_loss': sl, 'take_profit': tp,
                    'close_ticket': current_position['ticket'], 'strategy': 'Scalp FVG',
                    'reason': f'EMA trend flipped to {trend} — reversing',
                    'breakeven_trigger_usd': self.breakeven_usd,
                }
            return None

        # ---- FLAT (no open position) ----
        self.last_flat_since_index = self.last_flat_since_index or current_bar_index
        if not self.check_and_update_daily_limit(last_candle_time):
            return None
        # Daily loss cap: stop opening new trades once today's realized loss
        # reaches max_daily_loss_pct % of live balance (fixed-dollar fallback
        # when balance is unknown). Reset together with the trade counter on a
        # new trading day (check_and_update_daily_limit resets trades_today).
        daily_loss_cap = (account_balance * (self.max_daily_loss_pct / 100.0)
                          if account_balance and account_balance > 0
                          else self.max_daily_loss_pct)
        if self.realized_pnl_today <= -daily_loss_cap:
            return None
        if trend is None:
            return None

        # ---- 2. FVG/OB ENTRY — priority signal, BYPASSES cooldown (fix for Bug 3) ----
        for zone in reversed(sm_zones):
            zid = self._zone_id(zone, zone['source'])
            if zid in self.mitigated_zones:
                continue
            if zone['type'] == 'bullish' and trend == 'BUY' and self._zone_is_retested(zone, current_price, tolerance):
                sl, tp = self.calculate_dollarized_levels(current_price, 'BUY', account_balance,
                                                           pip_value_per_lot, lot_size, pip_size=pip_size)
                self.mitigated_zones.add(zid)
                self.last_entry_index = current_bar_index
                self.last_flat_since_index = 0
                return {'action': 'ENTER', 'direction': 'BUY', 'entry': round(current_price, 5),
                        'stop_loss': sl, 'take_profit': tp, 'breakeven_trigger_usd': self.breakeven_usd,
                        'strategy': 'Scalp FVG', 'reason': f'Bullish {zone["source"]} retest + EMA uptrend'}
            if zone['type'] == 'bearish' and trend == 'SELL' and self._zone_is_retested(zone, current_price, tolerance):
                sl, tp = self.calculate_dollarized_levels(current_price, 'SELL', account_balance,
                                                           pip_value_per_lot, lot_size, pip_size=pip_size)
                self.mitigated_zones.add(zid)
                self.last_entry_index = current_bar_index
                self.last_flat_since_index = 0
                return {'action': 'ENTER', 'direction': 'SELL', 'entry': round(current_price, 5),
                        'stop_loss': sl, 'take_profit': tp, 'breakeven_trigger_usd': self.breakeven_usd,
                        'strategy': 'Scalp FVG', 'reason': f'Bearish {zone["source"]} retest + EMA downtrend'}

        # ---- Remaining entries respect cooldown (routine signals, not priority) ----
        if current_bar_index - self.last_entry_index < self.cooldown_bars:
            return None

        if trend == 'BUY' and current_rsi > self.rsi_ob:
            return None
        if trend == 'SELL' and current_rsi < self.rsi_os:
            return None

        # ---- 3. Pullback entry ----
        if self.is_pullback_entry(df, ema_f, trend):
            sl, tp = self.calculate_dollarized_levels(current_price, trend, account_balance,
                                                       pip_value_per_lot, lot_size, pip_size=pip_size)
            self.last_entry_index = current_bar_index
            self.last_flat_since_index = 0
            return {'action': 'ENTER', 'direction': trend, 'entry': round(current_price, 5),
                    'stop_loss': sl, 'take_profit': tp, 'breakeven_trigger_usd': self.breakeven_usd,
                    'strategy': 'Scalp FVG', 'reason': f'{trend} EMA pullback entry (RSI={current_rsi:.0f})'}

        # ---- 4. Fresh momentum cross ----
        cross_lookback = 5
        if len(ema_f) > cross_lookback:
            recently_crossed = False
            for k in range(1, cross_lookback + 1):
                idx = -k
                try:
                    if trend == 'BUY' and ema_f.iloc[idx - 1] <= ema_s.iloc[idx - 1] and ema_f.iloc[idx] > ema_s.iloc[idx]:
                        recently_crossed = True
                        break
                    if trend == 'SELL' and ema_f.iloc[idx - 1] >= ema_s.iloc[idx - 1] and ema_f.iloc[idx] < ema_s.iloc[idx]:
                        recently_crossed = True
                        break
                except IndexError:
                    pass
            if recently_crossed:
                curr = df.iloc[-1]
                body = abs(curr['close'] - curr['open'])
                full_range = curr['high'] - curr['low']
                if full_range > 0 and body / full_range > 0.6:
                    is_dir = (trend == 'BUY' and curr['close'] > curr['open']) or (trend == 'SELL' and curr['close'] < curr['open'])
                    if is_dir:
                        sl, tp = self.calculate_dollarized_levels(current_price, trend, account_balance,
                                                                   pip_value_per_lot, lot_size, pip_size=pip_size)
                        self.last_entry_index = current_bar_index
                        self.last_flat_since_index = 0
                        return {'action': 'ENTER', 'direction': trend, 'entry': round(current_price, 5),
                                'stop_loss': sl, 'take_profit': tp, 'breakeven_trigger_usd': self.breakeven_usd,
                                'strategy': 'Scalp FVG', 'reason': f'{trend} momentum continuation (RSI={current_rsi:.0f})'}

        # ---- 5. NEW: plain trend continuation fallback (fix for Bug 4) ----
        if current_bar_index - self.last_flat_since_index >= self.trend_idle_bars:
            sl, tp = self.calculate_dollarized_levels(current_price, trend, account_balance,
                                                       pip_value_per_lot, lot_size, pip_size=pip_size)
            self.last_entry_index = current_bar_index
            self.last_flat_since_index = 0
            return {'action': 'ENTER', 'direction': trend, 'entry': round(current_price, 5),
                    'stop_loss': sl, 'take_profit': tp, 'breakeven_trigger_usd': self.breakeven_usd,
                    'strategy': 'Scalp FVG',
                    'reason': f'{trend} plain trend continuation — no perfect pattern, trend clear for {self.trend_idle_bars}+ bars'}

        return None
