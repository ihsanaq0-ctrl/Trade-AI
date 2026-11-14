"""
Bot 4: Full Confluence Mode — Research-Grounded Version
Requires: pandas, numpy, datetime, and instances of Bot 1, Bot 2, and Bot 3
Input: OHLCV DataFrame with columns: ['time', 'open', 'high', 'low', 'close']
        * Note: 'time' must be timezone-aware (UTC) for Kill Zone calculation.

Definitions used here are grounded in how professional multi-factor confluence and
ICT methodology actually work:

1. Uncorrelated Confluence: Combines SMC (Institutional), MMC (Geometric), and SNR
   (Historical Horizontal). They must all agree on direction.
2. Daily Bias: Derived from where today's session opened relative to yesterday's 50%
   midpoint. If open > yesterday's midpoint -> Bullish Bias. If open < -> Bearish Bias.
3. Kill Zones: Trades are ONLY executed during London (02:00-05:00 EST) or New York
   (07:00-10:00 EST) Kill Zones, when algorithmic liquidity is highest.
4. Spatial Overlap: The zones identified by the 3 bots must physically overlap.
   A buy signal from SMC at 1.1000 and a buy signal from SNR at 1.0900 is NOT confluence.
"""

from typing import Optional
from datetime import time, datetime, timezone, timedelta
import pandas as pd
import numpy as np
from .base import BaseStrategy, Signal


class FullConfluenceStrategy(BaseStrategy):
    name = "full_confluence"
    description = "All strategies combined — SMC+MMC+SNR must agree on direction AND overlap spatially during Kill Zones"
    timeframe = "H4"

    def __init__(self, smart_money_bot=None, mirror_bot=None, classic_bot=None, min_rr=2.0):
        """
        Pass in initialized instances of the other three bots.
        If not provided, creates default instances.
        """
        self.sm_bot = smart_money_bot
        self.mmc_bot = mirror_bot
        self.snr_bot = classic_bot
        self.min_rr = min_rr

    def _to_df(self, candles: list) -> pd.DataFrame:
        df = pd.DataFrame(candles)
        return df

    # ---------------------------------------------------------------
    # TIME FILTER: ICT KILL ZONES
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

    def is_kill_zone(self, timestamp_utc) -> bool:
        """Check if timestamp falls into either London or NY Kill Zone."""
        return self.get_kill_zone(timestamp_utc) is not None

    # ---------------------------------------------------------------
    # HIGHER TIMEFRAME BIAS
    # ---------------------------------------------------------------
    def calculate_daily_bias(self, df):
        """
        Determines daily bias using Previous Day High/Low Midpoint.
        If today's open is above yesterday's midpoint -> Bullish.
        If below -> Bearish.
        """
        df = df.copy()
        if 'time' in df.columns:
            df['time'] = pd.to_datetime(df['time'])

            # Resample to Daily to get yesterday's High/Low and today's Open
            daily_df = df.resample('D', on='time').agg({
                'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
            }).dropna()

            if len(daily_df) < 2:
                return 'neutral'

            prev_day = daily_df.iloc[-2]
            today = daily_df.iloc[-1]

            prev_midpoint = (prev_day['high'] + prev_day['low']) / 2
            today_open = today['open']

            if today_open > prev_midpoint:
                return 'bullish'
            elif today_open < prev_midpoint:
                return 'bearish'

        return 'neutral'

    def get_daily_bias(self, df: pd.DataFrame) -> str:
        """Legacy method that works without datetime index."""
        return self.calculate_daily_bias(df)

    # ---------------------------------------------------------------
    # ZONE OVERLAP LOGIC
    # ---------------------------------------------------------------
    def zones_overlap(self, zone1, zone2, tolerance_pct=0.0005):
        """
        Checks if two price zones physically overlap.
        zone format: (bottom_price, top_price)
        """
        if not zone1 or not zone2:
            return False

        z1_bottom, z1_top = zone1
        z2_bottom, z2_top = zone2

        # Add a tiny tolerance for floating point near-misses
        current_price = (z1_bottom + z1_top) / 2
        tolerance = current_price * tolerance_pct

        # Standard overlap logic: z1 starts before z2 ends, AND z1 ends after z2 starts
        overlap = (z1_bottom - tolerance) <= z2_top and (z1_top + tolerance) >= z2_bottom
        return overlap

    # ---------------------------------------------------------------
    # MAIN SIGNAL PIPELINE
    # ---------------------------------------------------------------
    def generate_signal(self, df, current_time_est: Optional[time] = None):
        """
        Full Confluence Pipeline:
        1. Check Daily Bias (must be clearly bullish or bearish).
        2. Check Kill Zone (must be London or NY).
        3. Run Bot 1, Bot 2, Bot 3 simultaneously.
        4. All three must return a signal in the SAME direction as Daily Bias.
        5. The entry zones identified by the bots must physically overlap.
        6. Calculate composite Risk/Reward.
        """
        df = df.copy()

        # ---- Make sure we have bot instances (lazy init) ----
        if self.sm_bot is None or self.mmc_bot is None or self.snr_bot is None:
            return None

        # ---- 1. Kill Zone Check ----
        active_kz = None
        if 'time' in df.columns:
            last_ts = pd.to_datetime(df['time'].iloc[-1])
            active_kz = self.get_kill_zone(last_ts)

        if active_kz is None:
            return None

        # ---- 2. Daily Bias Check ----
        daily_bias = self.calculate_daily_bias(df)
        if daily_bias == 'neutral':
            return None

        # ---- 3. Run all three bots ----
        sm_signal = self.sm_bot.generate_signal(df)
        mmc_signal = self.mmc_bot.generate_signal(df)
        snr_signal = self.snr_bot.generate_signal(df)

        if not sm_signal or not mmc_signal or not snr_signal:
            return None

        # ---- 4. Directional Confluence Check ----
        directions = [sm_signal['direction'], mmc_signal['direction'], snr_signal['direction']]
        if len(set(directions)) != 1:
            return None

        trade_direction = directions[0]
        bias_direction = 'BUY' if daily_bias == 'bullish' else 'SELL'

        if trade_direction != bias_direction:
            return None  # Bots agree, but against the Daily Bias. Reject.

        # ---- 5. Spatial Confluence Check (The Professional Filter) ----
        # Extract zone from SMC (SmartMoneyStrategy returns 'zone' or 'ote_zone')
        sm_zone = sm_signal.get('zone') or sm_signal.get('order_block_zone') or sm_signal.get('ote_zone')
        if not sm_zone and 'entry' in sm_signal:
            atr = sm_signal.get('atr', sm_signal['entry'] * 0.001)
            sm_zone = (sm_signal['entry'] - atr * 0.5, sm_signal['entry'] + atr * 0.5)

        # Extract zone from MMC (MirrorStrategy returns 'anchor_leg' or 'entry')
        mmc_zone = None
        anchor_leg = mmc_signal.get('anchor_leg', {})
        setup_type = mmc_signal.get('setup_type', '')
        if setup_type == 'eq_continuation' and 'eq_price' in anchor_leg:
            trig_price = anchor_leg['eq_price']
        elif setup_type == 'mirror_reversal' and 'mirror_price' in anchor_leg:
            trig_price = anchor_leg['mirror_price']
        else:
            trig_price = mmc_signal.get('entry') or mmc_signal.get('equilibrium') or mmc_signal.get('mirror_target')

        if trig_price:
            atr = mmc_signal.get('atr', trig_price * 0.001)
            mmc_zone = (trig_price - atr * 0.5, trig_price + atr * 0.5)

        # Extract zone from SNR (ClassicStrategy returns 'zone_boundaries')
        snr_zone = snr_signal.get('zone_boundaries')
        if not snr_zone and 'entry' in snr_signal:
            entry_p = snr_signal['entry']
            snr_zone = (entry_p * 0.999, entry_p * 1.001)

        # Check overlap between SMC & SNR, and SMC & MMC
        sm_snr_overlap = self.zones_overlap(sm_zone, snr_zone)
        sm_mmc_overlap = self.zones_overlap(sm_zone, mmc_zone)

        if not sm_snr_overlap or not sm_mmc_overlap:
            return None

        # ---- 6. Construct Composite Trade ----
        # Most conservative stop loss (furthest away) and TP (closest)
        if trade_direction == 'BUY':
            stop_loss = min(sm_signal['stop_loss'], mmc_signal['stop_loss'], snr_signal['stop_loss'])
            take_profit = min(sm_signal['take_profit'], mmc_signal['take_profit'], snr_signal['take_profit'])
        else:
            stop_loss = max(sm_signal['stop_loss'], mmc_signal['stop_loss'], snr_signal['stop_loss'])
            take_profit = max(sm_signal['take_profit'], mmc_signal['take_profit'], snr_signal['take_profit'])

        entry = df['close'].iloc[-1]
        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry)
        if risk == 0:
            return None
        rr_ratio = reward / risk

        if rr_ratio < self.min_rr:
            return None

        return {
            'strategy': 'Full Confluence Mode',
            'direction': trade_direction,
            'entry': round(entry, 5),
            'stop_loss': round(stop_loss, 5),
            'take_profit': round(take_profit, 5),
            'risk_reward': round(rr_ratio, 2),
            'daily_bias': daily_bias,
            'active_kill_zone': active_kz,
            'confluences': {
                'smart_money': f"{sm_signal.get('zone_type', 'SMC')} at {sm_zone}",
                'mirror': f"{mmc_signal.get('setup_type', 'MMC')} at {mmc_signal.get('entry', 'N/A')}",
                'classic': f"{snr_signal.get('zone_polarity', 'SNR')} zone {snr_signal.get('zone_boundaries', 'N/A')}"
            },
            'spatial_overlap_confirmed': True,
        }

    async def analyze(self, pair: str, candles: list, config: dict) -> Optional[Signal]:
        """Adapt generate_signal to our framework."""
        df = self._to_df(candles)
        # Require enough bars for MirrorStrategy (min 205 bars) and other sub-strategies
        if len(df) < 210:
            return None

        # Kill zone check in UTC
        active_kz = None
        if 'time' in df.columns:
            try:
                last_ts = pd.to_datetime(df['time'].iloc[-1])
                active_kz = self.get_kill_zone(last_ts)
            except Exception:
                pass

        if active_kz is None:
            return None

        # Use the async analyze methods of the sub-bots
        if self.sm_bot and self.mmc_bot and self.snr_bot:
            smc_result = await self.sm_bot.analyze(pair, candles, config)
            if smc_result is None:
                return None

            classic_result = await self.snr_bot.analyze(pair, candles, config)
            if classic_result is None or classic_result.action != smc_result.action:
                return None

            mirror_result = await self.mmc_bot.analyze(pair, candles, config)
            if mirror_result is None or mirror_result.action != smc_result.action:
                return None

            action = smc_result.action
            daily_bias = self.calculate_daily_bias(df)
            direction_matches_bias = (
                (daily_bias == 'bullish' and action == 'buy') or
                (daily_bias == 'bearish' and action == 'sell') or
                (daily_bias == 'neutral')
            )
            if not direction_matches_bias:
                return None

            # Conservative SL/TP
            stops = [smc_result.stop_loss, classic_result.stop_loss, mirror_result.stop_loss]
            tps = [smc_result.take_profit, classic_result.take_profit, mirror_result.take_profit]

            stop_loss = max(stops) if action == 'sell' else min(stops)
            take_profit = max(tps) if action == 'sell' else min(tps)

            entry = df['close'].iloc[-1]  # current price
            risk = abs(entry - stop_loss)
            reward = abs(take_profit - entry)
            if risk == 0:
                return None
            rr_ratio = reward / risk

            if rr_ratio < self.min_rr:
                return None

            return Signal(
                action=action,
                pair=pair,
                lot_size=config.get('lot_size', 0.01),
                stop_loss=round(stop_loss, 5),
                take_profit=round(take_profit, 5),
                confidence=0.9,
                reason=f"Full Confluence: {action.upper()} — 3/3 strategies align "
                       f"during {active_kz}, daily bias {daily_bias}, RR: {rr_ratio:.2f}"
            )

        return None