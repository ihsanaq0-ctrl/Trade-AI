"""
Bot 5: Scalp Mode (Trend-Pullback Scalper)
Requires: pandas, numpy, datetime
Input: OHLCV DataFrame with columns: ['time', 'open', 'high', 'low', 'close']
        * Note: 'time' must be timezone-aware (UTC).

Strategy Logic:
1. Trend: EMA 50 > EMA 200 (Bullish), EMA 50 < EMA 200 (Bearish)
2. Pullback Exhaustion: RSI(14) drops below 40 in an uptrend, or spikes above 60 in a downtrend.
3. Trigger: Price action confirmation (Pin bar or Engulfing) in the direction of the trend.
4. Risk Management: Stop Loss padded by ATR, Target uses min_rr.
5. Time Filters: London (02:00-05:00 EST) or NY (07:00-10:00 EST) Kill Zones.
6. Trade Cap: Hard maximum of trades per day to prevent overtrading.
"""

from typing import Optional
from datetime import time, datetime, timezone, timedelta
import pandas as pd
import numpy as np
from .base import BaseStrategy, Signal


class ScalpStrategy(BaseStrategy):
    name = "scalp"
    description = "Trend-Pullback Scalper: EMA trend, RSI exhaustion, Price Action trigger, London/NY Kill Zones"
    timeframe = "M5"

    def __init__(self, min_rr=1.5, max_daily_trades=3, atr_period=14, rsi_period=14):
        self.min_rr = min_rr
        self.max_daily_trades = max_daily_trades
        self.atr_period = atr_period
        self.rsi_period = rsi_period

        # State management for daily trade limiting
        self.current_date = None
        self.trades_today = 0

    def _to_df(self, candles: list) -> pd.DataFrame:
        df = pd.DataFrame(candles)
        return df

    # ---------------------------------------------------------------
    # DAILY TRADE LIMIT STATE MACHINE
    # ---------------------------------------------------------------
    def check_and_update_daily_limit(self, timestamp_utc):
        est_offset = timedelta(hours=-4)
        trading_day = (timestamp_utc + est_offset).date()

        if trading_day != self.current_date:
            self.current_date = trading_day
            self.trades_today = 0

        if self.trades_today >= self.max_daily_trades:
            return False

        return True

    def register_trade_executed(self):
        self.trades_today += 1

    # ---------------------------------------------------------------
    # TIME FILTER: KILL ZONES
    # ---------------------------------------------------------------
    def get_kill_zone(self, timestamp_utc):
        """
        Checks if the current time falls within London or NY Kill Zones.
        Input: timestamp_utc (datetime object or pandas Timestamp)
        London Kill Zone: 02:00 - 05:00 EST -> 07:00 - 10:00 UTC
        New York Kill Zone: 07:00 - 10:00 EST -> 12:00 - 15:00 UTC
        """
        if timestamp_utc is None:
            return None
        if isinstance(timestamp_utc, str):
            timestamp_utc = pd.to_datetime(timestamp_utc)

        hour = timestamp_utc.hour

        # London Kill Zone: 7 AM - 10 AM UTC (2 AM - 5 AM EST)
        if 7 <= hour < 10:
            return 'London KZ'
        # New York Kill Zone: 12 PM - 3 PM UTC (7 AM - 10 AM EST)
        elif 12 <= hour < 15:
            return 'New York KZ'

        return None

    # ---------------------------------------------------------------
    # INDICATORS
    # ---------------------------------------------------------------
    def calculate_indicators(self, df: pd.DataFrame):
        df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()

        # ATR
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['atr'] = true_range.rolling(self.atr_period).mean()

        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        return df

    # ---------------------------------------------------------------
    # PRICE ACTION DETECTION
    # ---------------------------------------------------------------
    def is_pin_bar(self, candle, direction):
        body = abs(candle['close'] - candle['open'])
        full_range = candle['high'] - candle['low']
        if full_range == 0:
            return False

        upper_wick = candle['high'] - max(candle['open'], candle['close'])
        lower_wick = min(candle['open'], candle['close']) - candle['low']

        if direction == 'bullish' and lower_wick > 0.6 * full_range and body < 0.3 * full_range:
            return True
        if direction == 'bearish' and upper_wick > 0.6 * full_range and body < 0.3 * full_range:
            return True
        return False

    def is_engulfing(self, df, index, direction):
        pos = index if isinstance(index, int) else df.index.get_loc(index)
        if pos == 0:
            return False
        curr = df.iloc[pos]
        prev = df.iloc[pos - 1]

        if direction == 'bullish':
            if prev['close'] < prev['open'] and curr['close'] > curr['open']:
                if curr['close'] >= prev['open'] and curr['open'] <= prev['close']:
                    return True
        if direction == 'bearish':
            if prev['close'] > prev['open'] and curr['close'] < curr['open']:
                if curr['open'] >= prev['close'] and curr['close'] <= prev['open']:
                    return True
        return False

    def has_price_action(self, df, direction):
        last_idx = df.index[-1]
        last_candle = df.loc[last_idx]
        if self.is_pin_bar(last_candle, direction):
            return True
        if self.is_engulfing(df, last_idx, direction):
            return True
        return False

    # ---------------------------------------------------------------
    # MAIN SIGNAL PIPELINE
    # ---------------------------------------------------------------
    def generate_signal(self, df: pd.DataFrame, current_time_est: Optional[time] = None):
        if len(df) < 200:
            return None

        df = df.copy()
        df = self.calculate_indicators(df)

        # 1. Daily Limit Check
        last_candle_time = pd.to_datetime(df['time'].iloc[-1]) if 'time' in df.columns else None
        if last_candle_time is None:
            return None

        if last_candle_time.tzinfo is None:
            last_candle_time = last_candle_time.replace(tzinfo=timezone.utc)

        if not self.check_and_update_daily_limit(last_candle_time):
            return None

        # 2. Kill Zone Check
        active_kz = self.get_kill_zone(last_candle_time)
        if active_kz is None:
            return None

        last_candle = df.iloc[-1]
        
        ema_50 = last_candle['ema_50']
        ema_200 = last_candle['ema_200']
        rsi = last_candle['rsi']
        atr = last_candle['atr']
        current_price = last_candle['close']

        if pd.isna(ema_200) or pd.isna(rsi) or pd.isna(atr):
            return None

        trade_direction = None
        stop_loss = 0.0

        # Bullish Setup
        if ema_50 > ema_200 and current_price > ema_200:
            # Look back recent 5 candles for an RSI dip
            recent_rsi = df['rsi'].iloc[-5:]
            if recent_rsi.min() < 40 and self.has_price_action(df, 'bullish'):
                trade_direction = 'BUY'
                stop_loss = df['low'].iloc[-2:].min() - (atr * 0.5)

        # Bearish Setup
        elif ema_50 < ema_200 and current_price < ema_200:
            # Look back recent 5 candles for an RSI spike
            recent_rsi = df['rsi'].iloc[-5:]
            if recent_rsi.max() > 60 and self.has_price_action(df, 'bearish'):
                trade_direction = 'SELL'
                stop_loss = df['high'].iloc[-2:].max() + (atr * 0.5)

        if not trade_direction:
            return None

        # 7. Construct Trade
        entry = current_price
        risk = abs(entry - stop_loss)
        if risk == 0:
            return None
            
        # Set target using minimum Risk-Reward ratio
        if trade_direction == 'BUY':
            take_profit = entry + (risk * self.min_rr)
        else:
            take_profit = entry - (risk * self.min_rr)

        return {
            'strategy': 'Scalp Mode (Trend-Pullback)',
            'direction': trade_direction,
            'entry': round(entry, 5),
            'stop_loss': round(stop_loss, 5),
            'take_profit': round(take_profit, 5),
            'risk_reward': round(self.min_rr, 2),
            'active_kill_zone': active_kz,
            'setup_type': 'Trend-Pullback Exhaustion',
            'trades_today': self.trades_today,
        }

    async def analyze(self, pair: str, candles: list, config: dict) -> Optional[Signal]:
        df = self._to_df(candles)
        if len(df) < 200:
            return None

        current_time_est = None
        if 'time' in df.columns:
            try:
                last_ts = pd.to_datetime(df['time'].iloc[-1])
                current_time_est = last_ts.time()
            except Exception as e:
                import logging; logging.getLogger(__name__).error(f'Database operation failed: {e}')

        result = self.generate_signal(df, current_time_est=current_time_est)
        if result is None:
            return None

        return Signal(
            action=result['direction'].lower(),
            pair=pair,
            lot_size=config.get('lot_size', 0.01),
            stop_loss=result['stop_loss'],
            take_profit=result['take_profit'],
            confidence=0.75,
            reason=f"{result['strategy']}: {result['direction']} during {result['active_kill_zone']}, "
                   f"trade #{result['trades_today'] + 1}/day, "
                   f"RR: {result['risk_reward']}"
        )