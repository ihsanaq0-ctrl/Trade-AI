"""
Bot 3: Classic Mode (SNR + Price Action) — Research-Grounded Version
Requires: pandas, numpy
Input: OHLCV DataFrame with columns: ['time', 'open', 'high', 'low', 'close']

Definitions used here are grounded in how professional price action traders
define and trade Support & Resistance (Al Brooks style, Prop-firm SNR methodologies):

1. Clustered Zones: S&R is not a single line. It is a zone formed by multiple
   overlapping swing points. The bot groups these into zones with a top and bottom boundary.
2. Flip Zones (Role Reversal): Broken support becomes resistance; broken resistance
   becomes support. The bot specifically flags these as high-probability zones.
3. False Breakouts (Spring/Upthrust): The bot doesn't blindly enter on a touch.
   It looks for price to pierce the zone boundary (trapping breakout traders),
   but close BACK inside the zone.
4. Price Action Confirmation: Requires a Pin Bar or Engulfing candle at the zone
   edge to trigger the entry.
"""

from typing import Optional
import pandas as pd
import numpy as np
from .base import BaseStrategy, Signal


class ClassicStrategy(BaseStrategy):
    name = "classic"
    description = "SNR + Price Action: clustered zones, flip detection, spring/upthrust trapping, dynamic TP"
    timeframe = "H4"

    def __init__(self, swing_lookback=5, zone_atr_multiplier=0.5, min_touches=2,
                 atr_period=14, min_rr=2.0):
        """
        swing_lookback: candles on each side to confirm a swing high/low
        zone_atr_multiplier: how wide a zone can be (in ATR) to consider swings "clustered"
        min_touches: minimum number of swing points required to validate a zone
        atr_period: lookback for volatility baseline
        min_rr: minimum risk-to-reward ratio required to take the trade
        """
        self.swing_lookback = swing_lookback
        self.zone_atr_multiplier = zone_atr_multiplier
        self.min_touches = min_touches
        self.atr_period = atr_period
        self.min_rr = min_rr

    def _to_df(self, candles: list) -> pd.DataFrame:
        df = pd.DataFrame(candles)
        if 'time' in df.columns:
            df.set_index('time', inplace=True)
        return df

    # ---------------------------------------------------------------
    # VOLATILITY & SWING DETECTION
    # ---------------------------------------------------------------
    def calculate_atr(self, df):
        high, low, close = df['high'], df['low'], df['close']
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs()
        ], axis=1).max(axis=1)
        return tr.rolling(self.atr_period).mean()

    def find_swing_points(self, df):
        n = self.swing_lookback
        df = df.copy()
        df['swing_high'] = False
        df['swing_low'] = False

        for i in range(n, len(df) - n):
            window_high = df['high'].iloc[i - n:i + n + 1]
            window_low = df['low'].iloc[i - n:i + n + 1]

            if df['high'].iloc[i] == window_high.max():
                df.loc[df.index[i], 'swing_high'] = True
            if df['low'].iloc[i] == window_low.min():
                df.loc[df.index[i], 'swing_low'] = True

        return df

    # ---------------------------------------------------------------
    # ZONE MAPPING (Clustering & Flip Detection)
    # ---------------------------------------------------------------
    def build_zones(self, df, atr_series):
        """
        Groups swing highs and lows into clustered Support/Resistance zones.
        Also checks historical data to see if the zone has been "flipped"
        (role reversal).
        """
        current_atr = atr_series.iloc[-1]
        if pd.isna(current_atr) or current_atr == 0:
            return []

        max_zone_width = current_atr * self.zone_atr_multiplier

        swing_highs = df[df['swing_high']]
        swing_lows = df[df['swing_low']]

        # Combine all swings to cluster them spatially
        all_swings = []
        for idx, row in swing_highs.iterrows():
            all_swings.append({'price': row['high'], 'type': 'high', 'index': idx})
        for idx, row in swing_lows.iterrows():
            all_swings.append({'price': row['low'], 'type': 'low', 'index': idx})

        # Sort by price to cluster
        all_swings.sort(key=lambda x: x['price'])

        if not all_swings:
            return []

        # Spatial Clustering Logic
        current_cluster = [all_swings[0]]
        zones_raw = []
        for i in range(1, len(all_swings)):
            if all_swings[i]['price'] - current_cluster[-1]['price'] <= max_zone_width:
                current_cluster.append(all_swings[i])
            else:
                zones_raw.append(current_cluster)
                current_cluster = [all_swings[i]]
        zones_raw.append(current_cluster)

        # Process clusters into formal Zone objects
        valid_zones = []
        for cluster in zones_raw:
            if len(cluster) < self.min_touches:
                continue

            cluster_prices = [c['price'] for c in cluster]
            zone_top = max(cluster_prices)
            zone_bottom = min(cluster_prices)

            # Determine zone polarity (Support, Resistance, or Flipped)
            highs_in_cluster = sum(1 for c in cluster if c['type'] == 'high')
            lows_in_cluster = sum(1 for c in cluster if c['type'] == 'low')

            polarity = 'mixed'
            if highs_in_cluster > 0 and lows_in_cluster == 0:
                polarity = 'resistance'
            elif lows_in_cluster > 0 and highs_in_cluster == 0:
                polarity = 'support'
            else:
                # If we have both highs and lows in the same cluster, it's a Flip Zone
                polarity = 'flipped'

            valid_zones.append({
                'top': zone_top,
                'bottom': zone_bottom,
                'touches': len(cluster),
                'polarity': polarity,
                'is_flipped': polarity == 'flipped',
            })

        # Sort zones by proximity to current price
        current_price = df['close'].iloc[-1]
        valid_zones.sort(key=lambda z: min(abs(current_price - z['top']), abs(current_price - z['bottom'])))

        return valid_zones

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
        # index may be a label (e.g. timestamp) — resolve to positional
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
    def generate_signal(self, df):
        """
        Full Classic S&R Pipeline:
        1. Identify swing points.
        2. Cluster them into Support/Resistance zones.
        3. Flag Flip Zones (role reversals) as priority.
        4. Check if current price has interacted with a zone via a Spring/Upthrust
           (false breakout that closes back inside the zone).
        5. Require strict Price Action confirmation (Pin Bar / Engulfing).
        6. Set targets at the opposite zone and filter by RR.
        """
        df = df.copy()
        df = self.find_swing_points(df)
        atr_series = self.calculate_atr(df)

        zones = self.build_zones(df, atr_series)
        if not zones:
            return None

        current_price = df['close'].iloc[-1]
        last_candle = df.iloc[-1]
        current_atr = atr_series.iloc[-1]

        # Find the nearest valid zone to current price
        active_zone = None
        for z in zones:
            # Check if price is currently inside the zone
            if z['bottom'] <= current_price <= z['top']:
                active_zone = z
                break
            # Spring / Upthrust check: wick through zone, but close back inside
            if last_candle['low'] < z['bottom'] and last_candle['close'] > z['bottom']:
                active_zone = z
                break
            if last_candle['high'] > z['top'] and last_candle['close'] < z['top']:
                active_zone = z
                break

        if not active_zone:
            return None

        # Determine Trade Direction based on zone POLARITY (not relative price).
        # A support zone is always a BUY setup; a resistance zone is always a SELL.
        # (The old logic compared price to zone bounds, which misread zero-width
        #  zones — a spring below a support zone was classified as bearish.)
        direction = None
        stop_loss = None
        take_profit = None

        # Buffer for stop loss just outside the zone
        sl_buffer = current_atr * 0.2

        if active_zone['polarity'] in ('support', 'flipped'):
            # Support (or flipped zone acting as support) -> BUY
            if current_price >= active_zone['bottom'] - sl_buffer:
                direction = 'bullish'
                stop_loss = active_zone['bottom'] - sl_buffer
                # Target the next resistance zone above
                for z in zones:
                    if z['bottom'] > active_zone['top']:
                        take_profit = z['bottom']
                        break

        elif active_zone['polarity'] in ('resistance', 'flipped'):
            # Resistance (or flipped zone acting as resistance) -> SELL
            if current_price <= active_zone['top'] + sl_buffer:
                direction = 'bearish'
                stop_loss = active_zone['top'] + sl_buffer
                # Target the next support zone below
                for z in reversed(zones):
                    if z['top'] < active_zone['bottom']:
                        take_profit = z['top']
                        break

        if not direction or not take_profit:
            return None

        # Price Action Confirmation Filter
        if not self.has_price_action(df, direction):
            return None

        entry = current_price
        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry)
        if risk == 0:
            return None
        rr_ratio = reward / risk

        if rr_ratio < self.min_rr:
            return None

        return {
            'strategy': 'Classic Mode (SNR + PA)',
            'direction': 'BUY' if direction == 'bullish' else 'SELL',
            'entry': round(entry, 5),
            'stop_loss': round(stop_loss, 5),
            'take_profit': round(take_profit, 5),
            'risk_reward': round(rr_ratio, 2),
            'zone_polarity': active_zone['polarity'],
            'zone_touches': active_zone['touches'],
            'zone_boundaries': (round(active_zone['bottom'], 5), round(active_zone['top'], 5)),
        }

    async def analyze(self, pair: str, candles: list, config: dict) -> Optional[Signal]:
        """Adapt generate_signal to our framework."""
        df = self._to_df(candles)
        if len(df) < 30:
            return None

        result = self.generate_signal(df)
        if result is None:
            return None

        return Signal(
            action=result['direction'].lower(),
            pair=pair,
            lot_size=config.get('lot_size', 0.01),
            stop_loss=result['stop_loss'],
            take_profit=result['take_profit'],
            confidence=0.7,
            reason=f"{result['strategy']}: {result['direction']} "
                   f"(polarity: {result['zone_polarity']}, {result['zone_touches']} touches), "
                   f"zone: {result['zone_boundaries']}, RR: {result['risk_reward']}"
        )