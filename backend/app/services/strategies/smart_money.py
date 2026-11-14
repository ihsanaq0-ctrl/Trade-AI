import pandas as pd
import numpy as np
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Optional, List, Tuple, Iterator

from .base import BaseStrategy, Signal


class SmartMoneyStrategy(BaseStrategy):
    """
    Smart Money Concepts (SMC) strategy — v2 (corrected).

    Pipeline, per setup:
      1. Swing structure: fractal highs/lows, vectorised, non-repainting.
         A swing at bar j only becomes VISIBLE at bar j + swing_lookback,
         so live and backtest see exactly the same levels (no look-ahead).
      2. Liquidity sweep (Judas swing): a candle wicks through one or more
         POOLED swing levels but closes back on the origin side. ALL levels
         between wick and close are checked (not just the most recent one),
         and the swept level must be a real liquidity pool
         (>= min_pool_touches clustered swing points).
      3. Displacement / BOS-MSS: within displacement_search_bars after the
         sweep, a candle with body >= displacement_atr_mult x ATR that
         closes beyond the most recent CONFIRMED swing (a real structure
         break, not a rolling max/min).
      4. Imbalance: the whole leg is scanned for Fair Value Gaps (any
         3-candle imbalance, unmitigated). Fallback: the last opposite
         candle strictly BETWEEN the sweep and the displacement — never
         the sweep candle itself.
      5. OTE confluence: the 62-79% Fib retracement of the
         sweep-wick -> displacement-close leg, anchored at the LEG END
         (i.e. the DEEP retracement zone near the origin, where the
         FVG/OB actually sits). The FVG/OB zone must geometrically
         overlap the OTE band — both must agree on the same zone.
      6. Entry: only on a CLOSED bar strictly after the zone finished
         forming. Price must TAP the zone/OTE overlap and HOLD (close back
         on the right side). A candle that slices through the zone does
         not trigger entry; a close beyond the sweep wick at any point
         kills the setup permanently; setups older than
         max_setup_age_bars after displacement are dropped.
      7. Risk: stop just beyond the sweep wick (ATR-padded, not a fixed
         % of price), target the nearest opposing liquidity pool that
         predates the sweep, gated by a minimum R:R discounted for spread.

    NOTE: one strategy instance must persist between calls (dedup state
    and config live on the instance). Do not re-instantiate per candle.
    """

    name = "smart_money"
    description = "Advanced SMC: Sweep, Displacement, FVG Entry"
    timeframe = "M5"

    def __init__(self,
                 min_rr: float = 1.5,
                 swing_lookback: int = 5,
                 atr_period: int = 14,
                 displacement_atr_mult: float = 1.3,
                 sweep_lookback_bars: int = 30,
                 displacement_search_bars: int = 5,
                 ote_fib_low: float = 0.62,
                 ote_fib_high: float = 0.79,
                 zone_entry_buffer_pct: float = 0.0005,
                 liquidity_cluster_pct: float = 0.0008,
                 # --- v2 additions ---
                 max_setup_age_bars: int = 12,
                 min_pool_touches: int = 2,
                 stop_padding_atr_mult: float = 0.20,
                 drop_forming_bar: bool = True,
                 spread_pct: float = 0.0001,
                 sessions: Optional[List[Tuple[int, int]]] = None,
                 digits: Optional[int] = None):
        """
        --- Core parameters (v1 defaults kept) ---
        min_rr: minimum acceptable risk-to-reward ratio
        swing_lookback: candles on each side to confirm a fractal swing
        atr_period: lookback for the ATR volatility baseline
        displacement_atr_mult: ATR multiples a candle body must exceed
                               to count as displacement
        sweep_lookback_bars: how far back to search for sweep candles
        displacement_search_bars: bars after a sweep to find the
                                  confirming displacement/BOS candle
        ote_fib_low / ote_fib_high: OTE retracement band (0.62 / 0.79).
                                    NOTE: now anchored at the leg END —
                                    the DEEP zone near the origin.
        zone_entry_buffer_pct: tolerance (% of price) for zone taps
        liquidity_cluster_pct: tolerance (% of price) for grouping equal
                               highs/lows into one liquidity pool

        --- v2 additions ---
        max_setup_age_bars: max bars between displacement and the entry
                            tap; older setups are dropped (staleness guard)
        min_pool_touches: swing points that must cluster at a level for it
                          to count as a liquidity pool worth sweeping.
                          Set to 1 to restore v1 behaviour (more signals,
                          weaker sweeps).
        stop_padding_atr_mult: stop distance beyond the sweep wick, in ATRs
        drop_forming_bar: True if your feed includes the currently FORMING
                          (unclosed) candle as the last row — its OHLC
                          repaints and signals would flicker. Set False
                          when backtesting over closed bars only.
        spread_pct: assumed spread as a fraction of price, used to
                    conservatively discount R:R (BUY fills at ask, SELL
                    exits at ask). 0.0 disables.
        sessions: optional killzone windows [(start_hour, end_hour), ...],
                  e.g. [(7, 10), (13, 16)] for London/NY opens. Hours are
                  interpreted in the timezone of your candle timestamps —
                  MT5 server time is usually UTC+2/+3, NOT UTC. None = off.
        digits: rounding digits for prices; None = auto-detect
        """
        self.min_rr = float(min_rr)
        self.swing_lookback = max(1, int(swing_lookback))
        self.atr_period = max(2, int(atr_period))
        self.displacement_atr_mult = float(displacement_atr_mult)
        self.sweep_lookback_bars = max(self.swing_lookback + 1, int(sweep_lookback_bars))
        self.displacement_search_bars = max(1, int(displacement_search_bars))
        self.ote_fib_low = float(ote_fib_low)
        self.ote_fib_high = float(ote_fib_high)
        if self.ote_fib_low > self.ote_fib_high:      # normalise ordering
            self.ote_fib_low, self.ote_fib_high = self.ote_fib_high, self.ote_fib_low
        self.zone_entry_buffer_pct = float(zone_entry_buffer_pct)
        self.liquidity_cluster_pct = float(liquidity_cluster_pct)
        self.max_setup_age_bars = max(1, int(max_setup_age_bars))
        self.min_pool_touches = max(1, int(min_pool_touches))
        self.stop_padding_atr_mult = max(0.0, float(stop_padding_atr_mult))
        self.drop_forming_bar = bool(drop_forming_bar)
        self.spread_pct = max(0.0, float(spread_pct))
        self.sessions = [(float(s), float(e)) for s, e in sessions] if sessions else None
        self.digits = digits

        # Internal state: fired-setup fingerprints for de-duplication.
        # Requires a persistent instance (see class docstring).
        self._fired_setups = OrderedDict()
        self._max_fired_setups = 200

    # ---------------------------------------------------------------
    # SWING STRUCTURE (vectorised, non-repainting)
    # ---------------------------------------------------------------
    def _find_swings(self, df: pd.DataFrame) -> pd.DataFrame:
        n = self.swing_lookback
        window = 2 * n + 1
        df = df.copy()
        if len(df) < window:
            df['swing_high'] = False
            df['swing_low'] = False
            return df
        roll_high = df['high'].rolling(window, center=True, min_periods=window).max()
        roll_low = df['low'].rolling(window, center=True, min_periods=window).min()
        df['swing_high'] = df['high'] == roll_high
        df['swing_low'] = df['low'] == roll_low
        return df

    def _atr(self, df: pd.DataFrame) -> pd.Series:
        high, low, close = df['high'], df['low'], df['close']
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs()
        ], axis=1).max(axis=1)
        return tr.rolling(self.atr_period).mean()

    # ---------------------------------------------------------------
    # SESSION FILTER (killzones). Hours are in the timezone of the
    # candle timestamps — MT5 server time is usually UTC+2/+3!
    # ---------------------------------------------------------------
    def _session_ok(self, df: pd.DataFrame) -> bool:
        if not self.sessions:
            return True
        if 'time' not in df.columns or len(df) == 0:
            return True
        t = df['time'].iloc[-1]
        try:
            if isinstance(t, (int, float, np.integer, np.floating)) and not isinstance(t, bool):
                ts = float(t)
                if ts > 1e12:          # milliseconds epoch
                    ts /= 1000.0
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            else:
                dt = pd.to_datetime(t)
            hour = dt.hour + dt.minute / 60.0
        except Exception:
            return True                # can't parse time -> don't block trading

        for start_h, end_h in self.sessions:
            if start_h <= end_h:
                if start_h <= hour < end_h:
                    return True
            else:                      # window wraps midnight, e.g. (22, 6)
                if hour >= start_h or hour < end_h:
                    return True
        return False

    # ---------------------------------------------------------------
    # STEP 1: LIQUIDITY SWEEP (Judas Swing / Stop Hunt)
    # Checks EVERY pool level between the wick and the close, requires
    # the swept level to be a genuine pool, and only uses swings that
    # were already confirmed at that bar (no look-ahead).
    # Yields sweeps newest-first so the freshest setup is evaluated first.
    # ---------------------------------------------------------------
    def _iter_sweeps(self, df: pd.DataFrame) -> Iterator[dict]:
        n = self.swing_lookback
        start = max(n, len(df) - self.sweep_lookback_bars)
        hi_pos = np.flatnonzero(df['swing_high'].to_numpy())
        lo_pos = np.flatnonzero(df['swing_low'].to_numpy())
        lows = df['low'].to_numpy()
        highs = df['high'].to_numpy()
        closes = df['close'].to_numpy()

        for i in range(len(df) - 1, start - 1, -1):
            c_low, c_high, c_close = lows[i], highs[i], closes[i]
            tol = c_close * self.liquidity_cluster_pct

            # SELL-SIDE sweep -> bullish: wick under swing lows, close back above
            # (only swings already confirmed by bar i: swing at j visible at j+n)
            vis_lo = lo_pos[lo_pos <= i - n]
            if len(vis_lo):
                levels = lows[vis_lo]
                swept = levels[(c_low < levels) & (levels < c_close)]
                if swept.size:
                    level = float(swept.max())
                    touches = max(int(np.count_nonzero(np.abs(levels - L) <= tol))
                                  for L in swept)
                    if touches >= self.min_pool_touches:
                        yield {'direction': 'bullish', 'level': level,
                               'index': i, 'touches': touches}
                        continue

            # BUY-SIDE sweep -> bearish: wick over swing highs, close back below
            vis_hi = hi_pos[hi_pos <= i - n]
            if len(vis_hi):
                levels = highs[vis_hi]
                swept = levels[(c_high > levels) & (levels > c_close)]
                if swept.size:
                    level = float(swept.min())
                    touches = max(int(np.count_nonzero(np.abs(levels - L) <= tol))
                                  for L in swept)
                    if touches >= self.min_pool_touches:
                        yield {'direction': 'bearish', 'level': level,
                               'index': i, 'touches': touches}
        return

    # ---------------------------------------------------------------
    # STEP 2: DISPLACEMENT / BOS-MSS
    # Structure to break = most recent CONFIRMED swing before the sweep
    # (a real structural level, not a rolling max/min).
    # ---------------------------------------------------------------
    def _detect_displacement(self, df: pd.DataFrame, sweep: dict, atr: pd.Series) -> Optional[dict]:
        sweep_idx = sweep['index']
        direction = sweep['direction']
        n = self.swing_lookback
        search_end = min(sweep_idx + self.displacement_search_bars, len(df) - 1)

        if direction == 'bullish':
            pos = np.flatnonzero(df['swing_high'].to_numpy())
        else:
            pos = np.flatnonzero(df['swing_low'].to_numpy())
        visible = pos[pos <= sweep_idx - n]
        if len(visible):
            j = int(visible[-1])
            structure_level = float(df['high'].iloc[j] if direction == 'bullish'
                                    else df['low'].iloc[j])
        else:
            pre = df.iloc[max(0, sweep_idx - n):sweep_idx + 1]
            structure_level = float(pre['high'].max() if direction == 'bullish'
                                    else pre['low'].min())

        opens = df['open'].to_numpy()
        closes = df['close'].to_numpy()
        atr_vals = atr.to_numpy()

        for i in range(sweep_idx, search_end + 1):
            a = atr_vals[i]
            if np.isnan(a) or a <= 0:
                continue
            body = abs(closes[i] - opens[i])
            if body < a * self.displacement_atr_mult:
                continue
            if direction == 'bullish':
                if closes[i] > opens[i] and closes[i] > structure_level:
                    return {'index': i, 'structure_level': structure_level}
            else:
                if closes[i] < opens[i] and closes[i] < structure_level:
                    return {'index': i, 'structure_level': structure_level}
        return None

    # ---------------------------------------------------------------
    # STEP 3a: Fair Value Gaps — scan the WHOLE leg (not just the
    # displacement candle), direction-matched and unmitigated.
    # ---------------------------------------------------------------
    def _find_fvgs(self, df: pd.DataFrame, sweep_idx: int, displacement_idx: int,
                   direction: str) -> list:
        fvgs = []
        last_scannable = min(displacement_idx + 1, len(df) - 2)
        for m in range(max(1, sweep_idx), last_scannable + 1):
            c1 = df.iloc[m - 1]
            c3 = df.iloc[m + 1]
            if direction == 'bullish' and float(c1['high']) < float(c3['low']):
                gap = {'bottom': float(c1['high']), 'top': float(c3['low']),
                       'formed_at': m + 1}
            elif direction == 'bearish' and float(c1['low']) > float(c3['high']):
                gap = {'bottom': float(c3['high']), 'top': float(c1['low']),
                       'formed_at': m + 1}
            else:
                continue
            # Mitigated = already fully traded through (close beyond far side)
            after = df['close'].iloc[m + 2:]
            if direction == 'bullish':
                ok = not (after < gap['bottom']).any()
            else:
                ok = not (after > gap['top']).any()
            if ok:
                fvgs.append(gap)
        return fvgs

    # ---------------------------------------------------------------
    # STEP 3b: Order Block — last opposite candle strictly BETWEEN the
    # sweep and the displacement. Can never be the sweep candle itself
    # (v1 bug: OB hugging the invalidation wick => inflated R:R).
    # ---------------------------------------------------------------
    def _find_order_block(self, df: pd.DataFrame, sweep_idx: int, displacement_idx: int,
                          direction: str) -> Optional[dict]:
        for j in range(displacement_idx - 1, sweep_idx, -1):   # excludes sweep candle
            c = df.iloc[j]
            if direction == 'bullish' and c['close'] < c['open']:
                ob = {'bottom': float(c['low']), 'top': float(c['open']),
                      'formed_at': displacement_idx}
            elif direction == 'bearish' and c['close'] > c['open']:
                ob = {'bottom': float(c['open']), 'top': float(c['high']),
                      'formed_at': displacement_idx}
            else:
                continue
            after = df['close'].iloc[displacement_idx + 1:]
            if direction == 'bullish' and (after < ob['bottom']).any():
                continue                                   # OB already violated
            if direction == 'bearish' and (after > ob['top']).any():
                continue
            return ob
        return None

    # ---------------------------------------------------------------
    # STEP 4: OTE ZONE — 62-79% retracement anchored at the LEG END.
    # (v1 bug: anchored at the origin => the 21-38% band, which almost
    # never coincides with the FVG/OB. This is the deep pullback zone.)
    # ---------------------------------------------------------------
    def _calculate_ote_zone(self, df: pd.DataFrame, sweep: dict,
                            displacement: dict) -> Optional[dict]:
        if sweep['direction'] == 'bullish':
            leg_start = float(df['low'].iloc[sweep['index']])    # sweep wick low
        else:
            leg_start = float(df['high'].iloc[sweep['index']])   # sweep wick high
        leg_end = float(df['close'].iloc[displacement['index']])
        leg_range = abs(leg_end - leg_start)
        if leg_range <= 0:
            return None

        if sweep['direction'] == 'bullish':
            upper = leg_end - leg_range * self.ote_fib_low    # 62% = shallow edge
            lower = leg_end - leg_range * self.ote_fib_high   # 79% = deep edge
        else:
            lower = leg_end + leg_range * self.ote_fib_low
            upper = leg_end + leg_range * self.ote_fib_high
        return {'lower': float(min(lower, upper)), 'upper': float(max(lower, upper))}

    # ---------------------------------------------------------------
    # LIQUIDITY POOLS (for take-profit) — clusters of equal highs/lows.
    # By default only pools that PREDATE the sweep are used as targets
    # (the "draw on liquidity"), not internal highs formed since.
    # ---------------------------------------------------------------
    def _liquidity_pools(self, df: pd.DataFrame, ref_price: float,
                         before_position: Optional[int] = None):
        tol = ref_price * self.liquidity_cluster_pct
        hi_pos = np.flatnonzero(df['swing_high'].to_numpy())
        lo_pos = np.flatnonzero(df['swing_low'].to_numpy())
        if before_position is not None:
            hi_pos = hi_pos[hi_pos < before_position]
            lo_pos = lo_pos[lo_pos < before_position]
        highs = df['high'].to_numpy()
        lows = df['low'].to_numpy()

        def cluster(positions, prices):
            if len(positions) == 0:
                return []
            vals = np.sort(prices[positions])
            pools, chunk = [], [vals[0]]
            for p in vals[1:]:
                if p - chunk[-1] <= tol:
                    chunk.append(p)
                else:
                    pools.append({'price': float(np.mean(chunk)), 'touches': len(chunk)})
                    chunk = [p]
            pools.append({'price': float(np.mean(chunk)), 'touches': len(chunk)})
            return pools

        return cluster(hi_pos, highs), cluster(lo_pos, lows)

    def _find_target(self, high_pools, low_pools, direction: str, current_price: float):
        if direction == 'bullish':
            above = [p['price'] for p in high_pools if p['price'] > current_price]
            return min(above) if above else None
        below = [p['price'] for p in low_pools if p['price'] < current_price]
        return max(below) if below else None

    # ---------------------------------------------------------------
    # HELPERS
    # ---------------------------------------------------------------
    def _round_price(self, price: float) -> float:
        if self.digits is not None:
            return round(price, self.digits)
        if price >= 500:
            return round(price, 2)     # indices, gold, BTC, ...
        if price >= 20:
            return round(price, 3)     # JPY pairs, silver, ...
        return round(price, 5)         # FX majors

    def _setup_key(self, df: pd.DataFrame, sweep: dict, trade_direction: str):
        """Fingerprint identifying one unique setup (for de-duplication)."""
        level = round(float(sweep['level']), 10)
        if 'time' in df.columns:
            try:
                return (trade_direction, level, str(df['time'].iloc[sweep['index']]))
            except Exception:
                pass
        return (trade_direction, level)

    def _confidence_score(self, zone_type: str, pool_touches: int, rr: float) -> float:
        conf = 0.55
        if zone_type == 'FVG':
            conf += 0.10                                    # imbalance present
        if pool_touches >= 3:
            conf += 0.10                                    # swept a major pool
        conf += max(0.0, min(0.10, (rr - self.min_rr) * 0.05))  # R:R headroom
        return round(min(conf, 0.95), 2)

    # ---------------------------------------------------------------
    # MAIN SIGNAL PIPELINE
    # ---------------------------------------------------------------
    def generate_signal(self, df: pd.DataFrame) -> Optional[dict]:
        """
        'df' is a DataFrame with columns:
        ['time', 'open', 'high', 'low', 'close', 'tick_volume'].
        Evaluates the most recent CLOSED candle. Returns a signal dict
        or None.
        """
        if df is None or len(df) < 60:
            return None
        if not {'open', 'high', 'low', 'close'}.issubset(df.columns):
            return None

        df = df.reset_index(drop=True)

        # If the feed appends the currently-forming bar as the last row,
        # drop it: its OHLC repaints mid-candle and signals would flicker.
        # (Set drop_forming_bar=False for backtests over closed bars.)
        if self.drop_forming_bar and len(df) > 1:
            df = df.iloc[:-1].reset_index(drop=True)

        if not self._session_ok(df):
            return None

        df = self._find_swings(df)
        atr = self._atr(df)

        current_idx = len(df) - 1
        current = df.iloc[current_idx]
        current_price = float(current['close'])
        buffer = current_price * self.zone_entry_buffer_pct

        atr_now = atr.iloc[-1]
        if pd.isna(atr_now) or atr_now <= 0:
            return None

        # Evaluate every recent sweep, newest first; first valid setup wins.
        for sweep in self._iter_sweeps(df):
            direction = sweep['direction']

            # STEP 2: displacement / BOS confirming the sweep
            displacement = self._detect_displacement(df, sweep, atr)
            if displacement is None:
                continue
            disp_idx = displacement['index']

            # Entry is evaluated on closed bars AFTER the displacement bar
            if current_idx <= disp_idx:
                continue

            # Staleness: a displacement older than max_setup_age_bars is dead
            if current_idx - disp_idx > self.max_setup_age_bars:
                continue

            sweep_candle = df.iloc[sweep['index']]

            # INVALIDATION: any close beyond the sweep wick kills the setup
            # (v1 bug: the bot kept buying zones of already-dead setups)
            post_sweep = df['close'].iloc[sweep['index'] + 1: current_idx + 1]
            if direction == 'bullish' and (post_sweep < sweep_candle['low']).any():
                continue
            if direction == 'bearish' and (post_sweep > sweep_candle['high']).any():
                continue

            # STEP 3: imbalance zones
            fvgs = self._find_fvgs(df, sweep['index'], disp_idx, direction)
            ob = self._find_order_block(df, sweep['index'], disp_idx, direction)

            # STEP 4: OTE band (deep 62-79% retracement of the leg)
            ote = self._calculate_ote_zone(df, sweep, displacement)
            if ote is None:
                continue

            # Confluence: zone must overlap the OTE band — both must agree
            candidates = [('FVG', z) for z in fvgs]
            if ob is not None:
                candidates.append(('OrderBlock', ob))
            overlapping = []
            for ztype, zone in candidates:
                ov_low = max(zone['bottom'], ote['lower'])
                ov_high = min(zone['top'], ote['upper'])
                if ov_high >= ov_low - buffer:
                    overlapping.append((ztype, zone, ov_low, ov_high))
            if not overlapping:
                continue

            # FVG preferred; the deepest FVG gives the best R:R. Else the OB.
            fvg_only = [o for o in overlapping if o[0] == 'FVG']
            if fvg_only:
                if direction == 'bullish':
                    ztype, zone, ov_low, ov_high = min(fvg_only, key=lambda o: o[1]['top'])
                else:
                    ztype, zone, ov_low, ov_high = max(fvg_only, key=lambda o: o[1]['bottom'])
            else:
                ztype, zone, ov_low, ov_high = overlapping[0]

            # The entry bar must come AFTER the zone finished forming
            # (a candle can't retrace into a gap it is itself creating)
            if current_idx <= zone['formed_at']:
                continue

            # STEP 5: tap-and-hold entry.
            # TAP: the bar trades into the zone/OTE overlap.
            # HOLD: the bar closes back on the right side of the zone.
            # (v1 bug: pure range-overlap bought straight-through breakdowns)
            if direction == 'bullish':
                tapped = float(current['low']) <= ov_high + buffer
                held = float(current['close']) > zone['bottom']
            else:
                tapped = float(current['high']) >= ov_low - buffer
                held = float(current['close']) < zone['top']
            if not (tapped and held):
                continue

            # STEP 6: target = nearest opposing pool that predates the sweep
            high_pools, low_pools = self._liquidity_pools(
                df, current_price, before_position=sweep['index'])
            target = self._find_target(high_pools, low_pools, direction, current_price)
            if target is None:
                continue

            # STEP 7: risk — ATR-padded stop beyond the sweep wick
            if direction == 'bullish':
                trade_direction = 'BUY'
                stop_loss = float(sweep_candle['low']) - atr_now * self.stop_padding_atr_mult
                take_profit = float(target)
                if not (stop_loss < current_price < take_profit):
                    continue
                if float(current['low']) <= stop_loss:
                    continue          # entry bar already spiked through the stop
            else:
                trade_direction = 'SELL'
                stop_loss = float(sweep_candle['high']) + atr_now * self.stop_padding_atr_mult
                take_profit = float(target)
                if not (take_profit < current_price < stop_loss):
                    continue
                if float(current['high']) >= stop_loss:
                    continue

            # R:R gate, discounted for spread (BUY fills at ask; SELL exits
            # at ask — either way spread widens risk and shrinks reward)
            spread = current_price * self.spread_pct
            risk = abs(current_price - stop_loss) + spread
            reward = abs(take_profit - current_price) - spread
            if risk <= 0 or reward <= 0:
                continue
            rr = reward / risk
            if rr < self.min_rr:
                continue

            # De-dup: one signal per unique setup (v1 fired on every bar
            # price sat in the zone)
            key = self._setup_key(df, sweep, trade_direction)
            if key in self._fired_setups:
                continue
            self._fired_setups[key] = True
            if len(self._fired_setups) > self._max_fired_setups:
                self._fired_setups.popitem(last=False)

            return {
                'direction': trade_direction,
                'entry': self._round_price(current_price),
                'stop_loss': self._round_price(stop_loss),
                'take_profit': self._round_price(take_profit),
                'risk_reward': round(rr, 2),
                'sweep_level': self._round_price(sweep['level']),
                'zone_type': ztype,
                'zone': (self._round_price(zone['bottom']),
                         self._round_price(zone['top'])),
                'ote_zone': (self._round_price(ote['lower']),
                             self._round_price(ote['upper'])),
                'pool_touches': sweep['touches'],
                'setup_age_bars': current_idx - disp_idx,
                'confidence': self._confidence_score(ztype, sweep['touches'], rr),
            }

        return None

    # -----------------------------------------------------------------
    # LIVE TRADING WRAPPER (DO NOT CHANGE)
    # -----------------------------------------------------------------
    async def analyze(self, pair: str, candles: list, config: dict) -> Optional[Signal]:
        """
        LIVE TRADING WRAPPER (DO NOT CHANGE)
        """
        df = pd.DataFrame(candles)
        if len(df) < 100:
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
            confidence=0.85,
            reason=f"SMC Setup Triggered"
        )