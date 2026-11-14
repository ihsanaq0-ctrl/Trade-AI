"""
Bot: Signal Strength Scalper + Hedge Chain (Rolling Martingale Recovery)
Python port matching the reviewed MT5 EA's architecture, including the
hedge chain recovery system this time, as requested.

WARNING (factual, not a lecture): EnableHedgeChain opens larger opposite-
direction positions when a trade is losing, and can roll again if that
doesn't recover. Lot size compounds with each roll up to hedge_max_lot.
A sustained one-directional trend can exhaust the chain's recovery capacity
before price reverses. This is a known, real property of the mechanism.

Requires: pandas, numpy
Input: OHLCV DataFrame with columns: ['time', 'open', 'high', 'low', 'close']
"""

import pandas as pd
import numpy as np
from datetime import timedelta, timezone


class SignalStrengthHedgeBot:
    name = "signal_strength_hedge"
    description = "Multi-factor signal scoring + health-based management + hedge chain recovery"
    timeframe = "M5"

    def __init__(self,
                 # -- Signal scoring --
                 trend_period_fast=12,
                 trend_period_slow=26,
                 rsi_period=14,
                 atr_period=14,
                 body_lookback=10,
                 signal_smoothing_candles=3,
                 current_candle_blend=0.4,
                 min_buy_score=5.5,
                 min_sell_score=5.5,
                 # -- Health management --
                 min_health_score=0.40,
                 max_adverse_atr=1.5,
                 health_grace_bars=2,
                 swing_lookback=20,
                 # -- Partial close --
                 enable_partial_close=True,
                 partial_close_75pct=0.25,
                 partial_close_50pct=0.50,
                 # -- Breakeven --
                 breakeven_trigger_usd=0.5,
                 # -- Guardrails --
                 max_daily_trades=15,
                 max_open_positions=3,
                 max_spread_points=0,
                 max_spread_atr_ratio=0.25,
                 basket_max_loss_pct=8.0,
                 drawdown_pause_pct=5.0,
                 pause_minutes=15,
                 # -- HEDGE CHAIN (martingale-family recovery) --
                 enable_hedge_chain=True,
                 hedge_trigger_atr=1.5,          # adverse move (in ATR) that starts a chain
                 hedge_require_signal=True,      # only hedge if reverse-direction score confirms
                 hedge_min_signal_score=4.5,
                 hedge_recovery_atr=1.0,         # favorable move (ATR) the hedge is sized to recover within
                 hedge_recovery_pct=110.0,       # close older leg once hedge covers this % of its loss
                 hedge_roll_min_profit=0.5,      # min profit ($) on recovered older leg to allow a roll
                 hedge_cycle_levels=2,           # max hedge levels per cycle before reseed/stop
                 hedge_max_cycles=3,             # max reseed cycles before releasing chain to loss mgmt
                 hedge_max_lot=0.10,             # hard lot ceiling per hedge leg
                 hedge_max_chain_loss_usd=0.0,   # 0 = disabled; close chain if combined loss exceeds this
                 hedge_max_chain_loss_pct=0.0):  # 0 = disabled; same, as % of equity
        self.trend_period_fast = trend_period_fast
        self.trend_period_slow = trend_period_slow
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        self.body_lookback = body_lookback
        self.signal_smoothing_candles = signal_smoothing_candles
        self.current_candle_blend = current_candle_blend
        self.min_buy_score = min_buy_score
        self.min_sell_score = min_sell_score

        self.min_health_score = min_health_score
        self.max_adverse_atr = max_adverse_atr
        self.health_grace_bars = health_grace_bars
        self.swing_lookback = swing_lookback

        self.enable_partial_close = enable_partial_close
        self.partial_close_75pct = partial_close_75pct
        self.partial_close_50pct = partial_close_50pct

        self.breakeven_trigger_usd = breakeven_trigger_usd

        self.max_daily_trades = max_daily_trades
        self.max_open_positions = max_open_positions
        self.max_spread_points = max_spread_points
        self.max_spread_atr_ratio = max_spread_atr_ratio
        self.basket_max_loss_pct = basket_max_loss_pct
        self.drawdown_pause_pct = drawdown_pause_pct
        self.pause_minutes = pause_minutes

        self.enable_hedge_chain = enable_hedge_chain
        self.hedge_trigger_atr = hedge_trigger_atr
        self.hedge_require_signal = hedge_require_signal
        self.hedge_min_signal_score = hedge_min_signal_score
        self.hedge_recovery_atr = hedge_recovery_atr
        self.hedge_recovery_pct = hedge_recovery_pct
        self.hedge_roll_min_profit = hedge_roll_min_profit
        self.hedge_cycle_levels = hedge_cycle_levels
        self.hedge_max_cycles = hedge_max_cycles
        self.hedge_max_lot = hedge_max_lot
        self.hedge_max_chain_loss_usd = hedge_max_chain_loss_usd
        self.hedge_max_chain_loss_pct = hedge_max_chain_loss_pct

        # -- State --
        self.current_date = None
        self.trades_today = 0
        self.peak_equity = None
        self.paused_until = None
        self.position_state: dict[int, dict] = {}
        # ticket -> {'initial_score', 'partial_level', 'breakeven_done',
        #            'chain_id', 'hedge_level', 'chain_anchor_loss', 'cycle_num', 'no_rehedge'}

    # ---------------------------------------------------------------
    # DAILY LIMIT / INDICATORS / SCORING / HEALTH — identical to the non-hedge version
    # ---------------------------------------------------------------
    def check_and_update_daily_limit(self, timestamp_utc) -> bool:
        trading_day = timestamp_utc.date()
        if trading_day != self.current_date:
            self.current_date = trading_day
            self.trades_today = 0
        return self.trades_today < self.max_daily_trades

    def register_trade_executed(self):
        self.trades_today += 1

    def calculate_emas(self, df):
        fast = df['close'].ewm(span=self.trend_period_fast, adjust=False).mean()
        slow = df['close'].ewm(span=self.trend_period_slow, adjust=False).mean()
        return fast, slow

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

    def compute_raw_score(self, df, ema_fast, ema_slow, rsi, atr, direction, index):
        if index + self.body_lookback + 2 >= len(df):
            return 0.0
        i = len(df) - 1 - index
        if i < self.body_lookback + 1:
            return 0.0

        is_buy = direction == 'BUY'
        candle = df.iloc[i]

        trend_score = 0.0
        aligned = (ema_fast.iloc[i] > ema_slow.iloc[i]) if is_buy else (ema_fast.iloc[i] < ema_slow.iloc[i])
        if aligned:
            trend_score += 1.5
            slope_ok = (ema_fast.iloc[i] > ema_fast.iloc[i - 1]) if is_buy else (ema_fast.iloc[i] < ema_fast.iloc[i - 1])
            if slope_ok:
                trend_score += 1.5

        body = abs(candle['close'] - candle['open'])
        recent_bodies = [abs(df.iloc[j]['close'] - df.iloc[j]['open']) for j in range(i - self.body_lookback, i)]
        avg_body = sum(recent_bodies) / len(recent_bodies) if recent_bodies else body

        momentum_score = 0.0
        r = rsi.iloc[i]
        if is_buy:
            if 50 < r < 80:
                momentum_score += 1.0
            if r > 55:
                momentum_score += 0.5
        else:
            if 20 < r < 50:
                momentum_score += 1.0
            if r < 45:
                momentum_score += 0.5
        if body > avg_body:
            momentum_score += 1.5
        momentum_score = min(momentum_score, 3.0)

        current_atr = atr.iloc[i]
        recent_atrs = atr.iloc[max(0, i - 10):i]
        avg_atr = recent_atrs.mean() if len(recent_atrs) else current_atr
        vol_ratio = (current_atr / avg_atr) if avg_atr and avg_atr > 0 else 1.0
        chop_score = 2.0 if vol_ratio > 1.0 else (1.0 if vol_ratio > 0.8 else 0.0)
        volatility_score = 1.0 if vol_ratio > 1.2 else 0.0

        window = df.iloc[max(0, i - 5):i]
        breakout_score = 0.0
        if not window.empty:
            if is_buy and candle['close'] > window['high'].max():
                breakout_score = 1.0
            elif not is_buy and candle['close'] < window['low'].min():
                breakout_score = 1.0

        upper_wick = candle['high'] - max(candle['open'], candle['close'])
        lower_wick = min(candle['open'], candle['close']) - candle['low']
        safe_body = max(body, avg_body * 1.5) if avg_body > 0 else body
        penalty = 0.0
        if safe_body > 0:
            rejection = (upper_wick if is_buy else lower_wick) / safe_body
            penalty = rejection * 1.0

        raw = trend_score + momentum_score + chop_score + volatility_score + breakout_score - penalty
        return max(0.0, min(10.0, raw))

    def get_signal_strength(self, df, ema_fast, ema_slow, rsi, atr, direction):
        n = max(1, min(10, self.signal_smoothing_candles))
        weighted_sum, weight_total = 0.0, 0.0
        for k in range(1, n + 1):
            score = self.compute_raw_score(df, ema_fast, ema_slow, rsi, atr, direction, k)
            weight = n - k + 1
            weighted_sum += score * weight
            weight_total += weight
        base_score = weighted_sum / weight_total if weight_total > 0 else 0.0
        current_score = self.compute_raw_score(df, ema_fast, ema_slow, rsi, atr, direction, 0)
        blend = max(0.0, min(1.0, self.current_candle_blend))
        return base_score * (1 - blend) + current_score * blend

    def evaluate_position_health(self, df, ema_fast, ema_slow, rsi, atr, position, bars_since_open):
        if bars_since_open < self.health_grace_bars:
            return {'health_score': 1.0, 'in_grace': True, 'reason': 'Grace period'}

        is_buy = position['direction'] == 'BUY'
        entry_price = position['entry_price']
        current_price = df['close'].iloc[-1]
        current_atr = atr.iloc[-1]

        trend_ok = (ema_fast.iloc[-1] > ema_slow.iloc[-1]) if is_buy else (ema_fast.iloc[-1] < ema_slow.iloc[-1])
        trend_score = 1.0 if trend_ok else 0.0

        r = rsi.iloc[-1]
        if is_buy:
            rsi_score = 1.0 if r >= 40 else max(0.0, (r - 25) / 15)
        else:
            rsi_score = 1.0 if r <= 60 else max(0.0, (75 - r) / 15)

        adverse_move = (entry_price - current_price) if is_buy else (current_price - entry_price)
        atr_score = 1.0
        adverse_atr = 0.0
        if current_atr and current_atr > 0 and adverse_move > 0:
            adverse_atr = adverse_move / current_atr
            atr_score = max(0.0, 1.0 - (adverse_atr / self.max_adverse_atr))

        lookback = min(self.swing_lookback, len(df) - 2)
        swing_score = 1.0
        if lookback >= 5:
            recent = df.iloc[-(lookback + 2):-2]
            if is_buy:
                if current_price < recent['low'].min():
                    swing_score = 0.0
            else:
                if current_price > recent['high'].max():
                    swing_score = 0.0

        health = (trend_score * 0.40) + (rsi_score * 0.25) + (atr_score * 0.25) + (swing_score * 0.10)
        reasons = []
        if not trend_ok:
            reasons.append('trend flipped')
        if rsi_score < 0.5:
            reasons.append('RSI weakening')
        if adverse_atr > self.max_adverse_atr:
            reasons.append(f'adverse move {adverse_atr:.1f}x ATR')
        if swing_score == 0:
            reasons.append('structure broken')

        return {'health_score': health, 'in_grace': False, 'reason': ', '.join(reasons) if reasons else 'healthy'}

    # ---------------------------------------------------------------
    # GUARDRAILS
    # ---------------------------------------------------------------
    def check_spread_ok(self, current_spread_points, atr_points):
        cap = self.max_spread_points
        if cap <= 0:
            cap = atr_points * self.max_spread_atr_ratio if atr_points else float('inf')
        return current_spread_points <= cap

    def check_basket_stop(self, open_positions, account_balance):
        """Excludes active hedge-chain legs — those are bounded by their own chain-loss stop instead."""
        if self.basket_max_loss_pct <= 0 or account_balance <= 0:
            return False
        non_chain = [p for p in open_positions if not self.position_state.get(p['ticket'], {}).get('chain_id')]
        floating_pl = sum(p.get('profit', 0) for p in non_chain)
        if floating_pl >= 0:
            return False
        loss_pct = (-floating_pl / account_balance) * 100
        return loss_pct >= self.basket_max_loss_pct

    def check_drawdown_pause(self, account_equity, now_utc):
        if self.peak_equity is None or account_equity > self.peak_equity:
            self.peak_equity = account_equity
            self.paused_until = None
            return False
        if self.paused_until is not None:
            if now_utc < self.paused_until:
                return True
            self.paused_until = None
        drop_pct = ((self.peak_equity - account_equity) / self.peak_equity) * 100
        if drop_pct >= self.drawdown_pause_pct:
            self.paused_until = now_utc + timedelta(minutes=self.pause_minutes)
            return True
        return False

    # ---------------------------------------------------------------
    # HEDGE CHAIN LOGIC
    # ---------------------------------------------------------------
    def compute_hedge_lot(self, older_lot, older_loss, atr_value, tick_value_per_lot=10.0):
        """
        Sizes the hedge so a favorable move of hedge_recovery_atr x ATR produces
        profit covering hedge_recovery_pct% of the older leg's current loss.
        Falls back to a simple 2x multiplier if the ATR-based calc is invalid.
        """
        target_price_move = self.hedge_recovery_atr * atr_value
        if target_price_move <= 0 or tick_value_per_lot <= 0:
            lot = older_lot * 2.0
        else:
            money_per_lot = target_price_move * tick_value_per_lot * 10000  # rough pip-value scaling
            p = self.hedge_recovery_pct / 100.0
            lot = p * older_lot + (p * older_loss / money_per_lot if money_per_lot > 0 else older_lot)
            if lot <= older_lot:
                lot = older_lot * 2.0

        min_lot = older_lot + 0.01
        lot = max(lot, min_lot)
        lot = min(lot, self.hedge_max_lot)
        return round(lot, 2)

    def chain_loss_stop_threshold(self, account_equity):
        usd = self.hedge_max_chain_loss_usd if self.hedge_max_chain_loss_usd > 0 else 0
        pct = (account_equity * self.hedge_max_chain_loss_pct / 100.0) if self.hedge_max_chain_loss_pct > 0 else 0
        if usd > 0 and pct > 0:
            return min(usd, pct)
        return max(usd, pct)

    def manage_hedge_chains(self, df, ema_fast, ema_slow, rsi, atr, open_positions, account_equity):
        """
        Returns a list of hedge-related actions. Mirrors the EA's chain logic:
        COVERED -> close older, graduate hedge to normal trailing.
        ROLL    -> close older (recovered), open next hedge level.
        RESEED / STOP -> release to normal management or close chain, per caps.
        Also scans standalone losing positions to START new chains.
        """
        if not self.enable_hedge_chain:
            return []

        actions = []
        current_atr = atr.iloc[-1]
        if pd.isna(current_atr) or current_atr <= 0:
            return actions

        by_ticket = {p['ticket']: p for p in open_positions}

        # Group legs by chain_id
        chains: dict[int, list] = {}
        for ticket, state in self.position_state.items():
            chain_id = state.get('chain_id')
            if chain_id and ticket in by_ticket:
                chains.setdefault(chain_id, []).append(ticket)

        # ---- Phase A: manage existing chains ----
        for chain_id, tickets in chains.items():
            legs = [(t, self.position_state[t], by_ticket[t]) for t in tickets]
            legs.sort(key=lambda x: x[1]['hedge_level'])
            older_ticket, older_state, older_pos = legs[0]
            hedge_ticket, hedge_state, hedge_pos = legs[-1]

            older_pl = older_pos.get('profit', 0)
            hedge_pl = hedge_pos.get('profit', 0)
            total_pl = sum(l[2].get('profit', 0) for l in legs)

            if len(legs) == 1:
                # orphan leg — graduate it, chain dissolved
                self.position_state[hedge_ticket]['chain_id'] = None
                continue

            # COVERED
            if older_pl < 0:
                cover_needed = (self.hedge_recovery_pct / 100.0) * (-older_pl)
                if hedge_pl >= cover_needed:
                    actions.append({'action': 'CLOSE', 'ticket': older_ticket,
                                     'reason': f'Hedge covered {self.hedge_recovery_pct}% of loss'})
                    self.position_state[hedge_ticket]['chain_id'] = None
                    self.position_state[hedge_ticket]['breakeven_done'] = True
                    continue

            # ROLL
            if hedge_pl < 0 and older_pl >= self.hedge_roll_min_profit:
                level_ok = hedge_state['hedge_level'] < self.hedge_cycle_levels
                new_lot = self.compute_hedge_lot(hedge_pos['lot'], -hedge_pl, current_atr) if level_ok else 0
                lot_ok = new_lot > hedge_pos['lot']

                if level_ok and lot_ok:
                    actions.append({'action': 'CLOSE', 'ticket': older_ticket, 'reason': 'Hedge roll: older recovered'})
                    actions.append({
                        'action': 'OPEN_HEDGE',
                        'direction': 'SELL' if hedge_pos['direction'] == 'BUY' else 'BUY',
                        'lot': new_lot, 'chain_id': chain_id,
                        'hedge_level': hedge_state['hedge_level'] + 1,
                        'chain_anchor_loss': hedge_state['chain_anchor_loss'],
                        'cycle_num': hedge_state['cycle_num'],
                        'reason': f'Roll to hedge level {hedge_state["hedge_level"] + 1}',
                    })
                    continue
                else:
                    # cycle limit or lot ceiling reached — release to normal management, no reseed here
                    for t, st, _ in legs:
                        st['chain_id'] = None
                        st['no_rehedge'] = True
                    continue

            # STOP: combined chain loss stop
            stop_thr = self.chain_loss_stop_threshold(account_equity)
            if stop_thr > 0 and total_pl <= -stop_thr:
                for t, st, _ in legs:
                    actions.append({'action': 'CLOSE', 'ticket': t, 'reason': 'Hedge chain loss stop hit'})
                    st['chain_id'] = None
                continue
            # else: hold, let it ride

        # ---- Phase B: start new chains on qualifying standalone losers ----
        for pos in open_positions:
            ticket = pos['ticket']
            state = self.position_state.get(ticket, {})
            if state.get('chain_id') or state.get('no_rehedge'):
                continue
            profit = pos.get('profit', 0)
            if profit >= 0:
                continue

            entry = pos['entry_price']
            current_price = df['close'].iloc[-1]
            is_buy = pos['direction'] == 'BUY'
            adverse = (entry - current_price) if is_buy else (current_price - entry)
            if adverse <= 0 or (adverse / current_atr) < self.hedge_trigger_atr:
                continue

            if self.hedge_require_signal:
                reverse_dir = 'SELL' if is_buy else 'BUY'
                reverse_score = self.get_signal_strength(df, ema_fast, ema_slow, rsi, atr, reverse_dir)
                if reverse_score < self.hedge_min_signal_score:
                    continue  # likely a spike, not a real reversal — wait for confirmation

            anchor_loss = -profit
            hedge_lot = self.compute_hedge_lot(pos['lot'], anchor_loss, current_atr)
            if hedge_lot <= pos['lot']:
                continue  # can't size a meaningful hedge within the lot ceiling

            new_chain_id = ticket
            self.position_state.setdefault(ticket, {}).update({
                'chain_id': new_chain_id, 'hedge_level': 0,
                'chain_anchor_loss': anchor_loss, 'cycle_num': 0, 'no_rehedge': False,
            })
            actions.append({
                'action': 'OPEN_HEDGE',
                'direction': 'SELL' if is_buy else 'BUY',
                'lot': hedge_lot, 'chain_id': new_chain_id, 'hedge_level': 1,
                'chain_anchor_loss': anchor_loss, 'cycle_num': 0,
                'reason': f'Hedge chain started: {adverse / current_atr:.1f} ATR adverse move',
            })

        return actions

    # ---------------------------------------------------------------
    # MAIN PIPELINE
    # ---------------------------------------------------------------
    def generate_signal(self, df, open_positions=None, account_balance=100.0,
                         account_equity=None, current_spread_points=0, lot_size=0.01):
        actions = []
        open_positions = open_positions or []
        if account_equity is None:
            account_equity = account_balance + sum(p.get('profit', 0) for p in open_positions)

        if len(df) < max(self.trend_period_slow + 5, self.atr_period + 5, 30):
            return actions

        df = df.copy()
        last_time = pd.to_datetime(df['time'].iloc[-1])
        if last_time.tzinfo is None:
            last_time = last_time.replace(tzinfo=timezone.utc)

        ema_fast, ema_slow = self.calculate_emas(df)
        atr = self.calculate_atr(df)
        rsi = self.calculate_rsi(df)
        current_atr_points = (atr.iloc[-1] / 0.0001) if not pd.isna(atr.iloc[-1]) else 0

        # Basket stop (excludes active chain legs — they have their own stop)
        if self.check_basket_stop(open_positions, account_balance):
            self.paused_until = last_time + timedelta(minutes=self.pause_minutes)
            return [{'action': 'CLOSE_ALL_AND_PAUSE',
                     'reason': f'Basket floating loss (non-chain) >= {self.basket_max_loss_pct}%'}]

        # Hedge chain management runs before normal position management,
        # so chain legs are skipped by health/partial-close/breakeven below.
        hedge_actions = self.manage_hedge_chains(df, ema_fast, ema_slow, rsi, atr, open_positions, account_equity)
        actions.extend(hedge_actions)

        chained_tickets = {p['ticket'] for p in open_positions
                            if self.position_state.get(p['ticket'], {}).get('chain_id')}

        for pos in open_positions:
            ticket = pos['ticket']
            if ticket in chained_tickets:
                continue  # chain logic exclusively manages these legs

            state = self.position_state.setdefault(ticket, {
                'initial_score': None, 'partial_level': 0, 'breakeven_done': False,
                'chain_id': None, 'hedge_level': 0, 'chain_anchor_loss': 0,
                'cycle_num': 0, 'no_rehedge': False,
            })

            open_time = pos.get('open_time')
            bars_since_open = 999
            if open_time is not None:
                if open_time.tzinfo is None:
                    open_time = open_time.replace(tzinfo=timezone.utc)
                bars_since_open = int(((last_time - open_time).total_seconds() / 60) / 5)

            health = self.evaluate_position_health(df, ema_fast, ema_slow, rsi, atr, pos, bars_since_open)
            if health['in_grace']:
                continue

            profit = pos.get('profit', 0)

            if not state['breakeven_done'] and profit > self.breakeven_trigger_usd:
                actions.append({'action': 'MODIFY_SL', 'ticket': ticket, 'new_sl': pos['entry_price'],
                                 'reason': f'Breakeven lock at ${profit:.2f}'})
                state['breakeven_done'] = True

            if self.enable_partial_close and state['initial_score']:
                current_score = self.get_signal_strength(df, ema_fast, ema_slow, rsi, atr, pos['direction'])
                ratio = current_score / state['initial_score'] if state['initial_score'] > 0 else 1.0
                if state['partial_level'] == 0 and ratio <= 0.75:
                    actions.append({'action': 'PARTIAL_CLOSE', 'ticket': ticket,
                                     'close_pct': self.partial_close_75pct, 'reason': f'Signal at {ratio*100:.0f}%'})
                    state['partial_level'] = 1
                elif state['partial_level'] == 1 and ratio <= 0.50:
                    actions.append({'action': 'PARTIAL_CLOSE', 'ticket': ticket,
                                     'close_pct': self.partial_close_50pct, 'reason': f'Signal at {ratio*100:.0f}%'})
                    state['partial_level'] = 2

            if health['health_score'] < self.min_health_score:
                actions.append({'action': 'CLOSE', 'ticket': ticket,
                                 'reason': f"Health {health['health_score']:.2f} ({health['reason']})"})
                self.position_state.pop(ticket, None)

        if self.check_drawdown_pause(account_equity, last_time):
            return actions
        if not self.check_and_update_daily_limit(last_time):
            return actions
        if len(open_positions) >= self.max_open_positions:
            return actions
        if not self.check_spread_ok(current_spread_points, current_atr_points):
            return actions

        buy_score = self.get_signal_strength(df, ema_fast, ema_slow, rsi, atr, 'BUY')
        sell_score = self.get_signal_strength(df, ema_fast, ema_slow, rsi, atr, 'SELL')

        direction, score, threshold = None, 0, 0
        if buy_score > sell_score and buy_score >= self.min_buy_score:
            direction, score, threshold = 'BUY', buy_score, self.min_buy_score
        elif sell_score > buy_score and sell_score >= self.min_sell_score:
            direction, score, threshold = 'SELL', sell_score, self.min_sell_score

        if direction:
            actions.append({'action': 'ENTER', 'direction': direction, 'lot': lot_size,
                             'reason': f'{direction} score {score:.1f} >= {threshold:.1f}',
                             'pending_initial_score': score})

        return actions

    def on_position_opened(self, ticket, initial_score):
        self.position_state[ticket] = {
            'initial_score': initial_score, 'partial_level': 0, 'breakeven_done': False,
            'chain_id': None, 'hedge_level': 0, 'chain_anchor_loss': 0,
            'cycle_num': 0, 'no_rehedge': False,
        }


# Example usage inside your scheduler loop (pseudocode):
#
# bot = SignalStrengthHedgeBot(enable_hedge_chain=True, hedge_max_lot=0.10,
#                               hedge_cycle_levels=2, hedge_max_cycles=3)
#
# df = fetch_latest_candles(symbol, timeframe='M5')
# open_positions = fetch_open_positions(symbol)
# actions = bot.generate_signal(df, open_positions, account_balance=balance, account_equity=equity)
#
# for action in actions:
#     if action['action'] == 'ENTER':
#         result = call_backend_open_trade(symbol, action['direction'], action['lot'])
#         if result.get('success'):
#             bot.on_position_opened(result['ticket'], action['pending_initial_score'])
#     elif action['action'] == 'OPEN_HEDGE':
#         result = call_backend_open_trade(symbol, action['direction'], action['lot'])
#         if result.get('success'):
#             bot.position_state[result['ticket']] = {
#                 'chain_id': action['chain_id'], 'hedge_level': action['hedge_level'],
#                 'chain_anchor_loss': action['chain_anchor_loss'], 'cycle_num': action['cycle_num'],
#                 'initial_score': None, 'partial_level': 0, 'breakeven_done': False, 'no_rehedge': False,
#             }
#     elif action['action'] == 'CLOSE':
#         call_backend_close_trade(action['ticket'])
#     elif action['action'] == 'PARTIAL_CLOSE':
#         call_backend_partial_close(action['ticket'], action['close_pct'])
#     elif action['action'] == 'MODIFY_SL':
#         call_backend_modify_sl(action['ticket'], action['new_sl'])
#     elif action['action'] == 'CLOSE_ALL_AND_PAUSE':
#         call_backend_close_all(symbol)
