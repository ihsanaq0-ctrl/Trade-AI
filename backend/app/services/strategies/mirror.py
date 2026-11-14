"""
mirror.py — Market Mirror Concept (MMC) strategy, v3 (Track-A win-rate build).

Pipeline per anchor leg (most recent confirmed swing leg):
  eq_continuation : retracement into the 50% Eq + PA reversal WITH the leg.
                    SL beyond the leg ORIGIN (structural), TP at a
                    configurable fraction of the measured-move extension.
  mirror_reversal : extension into the 100% Mirror + PA reversal AGAINST
                    the leg. SL beyond the MIRROR LINE (structural), TP at
                    the 50% Eq (or the leg origin).

v3 adds on top of v2 (Track A — raise WR by deleting losers, not by buying WR):
  A1  rejection_mode — how strictly the tap bar must close back on the
      entry side of the zone:
        'inner' : close back inside the zone           (v2 behaviour)
        'mid'   : close back beyond the zone midpoint
        'edge'  : close fully back beyond the far edge (full rejection)
  A2  confirm_next_close — the tap bar only ARMS the setup; the trade fires
      on the NEXT bar only if that bar closes in the trade direction
      without trading through the stop. Pending state is keyed by
      timestamps (backtest windows slide — raw indices go stale) and
      expires if the confirmation bar is missed.
  A3  same-zone re-entry block (zone_reentry_*), post-signal spacing
      (post_signal_cooldown_bars), and loss cooldown driven by the
      backtest runner via on_trade_result().
  A4  trend_ema_period — EMA bias filter, continuation setups only (v2).
  A5  atr_max_median_mult — skip signals when current ATR exceeds a
      multiple of its recent median (news-bar filter). sessions= (v2).
  A6  enable_mirror_setup=False — disable low-WR mirror reversals.

Everything remains non-repainting: swings confirm L bars later, zones /
SL / TP are fixed at signal time, pending confirmations expire after one bar.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    from .base import BaseStrategy, Signal          # same module SmartMoneyStrategy uses
except ImportError:                                 # pragma: no cover — standalone fallback
    try:
        from .base_strategy import BaseStrategy     # alt module name used in v1
    except ImportError:
        class BaseStrategy:                         # minimal stand-in for unit tests
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

    @dataclass
    class Signal:
        action: str
        pair: str
        lot_size: float
        stop_loss: float
        take_profit: float
        confidence: float
        reason: str


# --------------------------------------------------------------------------
# Anchor leg
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class AnchorLeg:
    start_idx: int        # swing bar that ORIGINATES the leg
    end_idx: int          # most recent confirmed swing bar
    start_price: float
    end_price: float
    direction: int        # +1 bullish (low->high), -1 bearish (high->low)
    size: float
    eq_price: float       # 50% midpoint
    mirror_price: float   # 100% projection from leg end


class MirrorStrategy(BaseStrategy):
    name = "mirror"
    description = "MMC: 50% Eq continuation + 100% Mirror reversal (Track-A build)"
    timeframe = "M5"

    def __init__(self,
                 # --- structure ---
                 swing_lookback: int = 5,
                 min_leg_size_atr_mult: float = 3.0,
                 max_leg_age_bars: int = 60,
                 # --- zones ---
                 eq_zone_atr_mult: float = 0.25,
                 mirror_zone_atr_mult: float = 0.25,
                 # --- invalidation ---
                 eq_invalidation_atr_mult: float = 0.5,
                 mirror_invalidation_atr_mult: float = 0.5,
                 origin_break_atr_mult: float = 0.0,
                 # --- reversal candle ---
                 pin_wick_body_ratio: float = 2.0,
                 # --- stops / targets ---
                 atr_period: int = 14,
                 stop_padding_atr_mult: float = 0.3,
                 mirror_sl_leg_frac: float = 0.25,
                 eq_tp_extension: float = 1.0,
                 mirror_tp_mode: str = "eq",           # 'eq' | 'origin'
                 # --- Track A filters (v3) ---
                 rejection_mode: str = "edge",         # 'inner' | 'mid' | 'edge'   (A1)
                 confirm_next_close: bool = False,     # confirmation candle        (A2)
                 post_signal_cooldown_bars: int = 0,   # spacing after ANY signal   (A3)
                 zone_reentry_block_bars: int = 240,   # same-zone re-entry window  (A3)
                 zone_reentry_atr_mult: float = 0.5,   # zone tolerance, in ATR      (A3)
                 atr_median_lookback: int = 500,       # for A5 baseline median
                 atr_max_median_mult: Optional[float] = None,  # e.g. 2.0          (A5)
                 # --- switches ---
                 enable_eq_setup: bool = True,
                 enable_mirror_setup: bool = True,     # A6: set False in WR preset
                 trend_ema_period: Optional[int] = None,   # A4: eq setups only
                 sessions: Optional[List[Tuple[float, float]]] = None,
                 # --- risk ---
                 spread_pct: float = 0.0001,
                 min_rr: float = 1.5,
                 # --- misc ---
                 price_decimals: int = 5,
                 max_fired_cache: int = 500,
                 drop_forming_bar: bool = True,
                 **kwargs):
        super().__init__(**kwargs)

        self.swing_lookback = int(swing_lookback)
        self.min_leg_size_atr_mult = float(min_leg_size_atr_mult)
        self.max_leg_age_bars = int(max_leg_age_bars)
        self.eq_zone_atr_mult = float(eq_zone_atr_mult)
        self.mirror_zone_atr_mult = float(mirror_zone_atr_mult)
        self.eq_invalidation_atr_mult = float(eq_invalidation_atr_mult)
        self.mirror_invalidation_atr_mult = float(mirror_invalidation_atr_mult)
        self.origin_break_atr_mult = float(origin_break_atr_mult)
        self.pin_wick_body_ratio = float(pin_wick_body_ratio)
        self.atr_period = int(atr_period)
        self.stop_padding_atr_mult = float(stop_padding_atr_mult)
        self.mirror_sl_leg_frac = float(mirror_sl_leg_frac)
        self.eq_tp_extension = float(eq_tp_extension)
        self.mirror_tp_mode = str(mirror_tp_mode)
        self.rejection_mode = str(rejection_mode)
        self.confirm_next_close = bool(confirm_next_close)
        self.post_signal_cooldown_bars = int(post_signal_cooldown_bars)
        self.zone_reentry_block_bars = int(zone_reentry_block_bars)
        self.zone_reentry_atr_mult = float(zone_reentry_atr_mult)
        self.atr_median_lookback = int(atr_median_lookback)
        self.atr_max_median_mult = (float(atr_max_median_mult)
                                    if atr_max_median_mult else None)
        self.enable_eq_setup = bool(enable_eq_setup)
        self.enable_mirror_setup = bool(enable_mirror_setup)
        self.trend_ema_period = int(trend_ema_period) if trend_ema_period else None
        self.sessions = [(float(s), float(e)) for s, e in sessions] if sessions else None
        self.spread_pct = float(spread_pct)
        self.min_rr = float(min_rr)
        self.price_decimals = int(price_decimals)
        self.max_fired_cache = int(max_fired_cache)
        self.drop_forming_bar = bool(drop_forming_bar)

        if self.mirror_tp_mode not in ("eq", "origin"):
            raise ValueError("mirror_tp_mode must be 'eq' or 'origin'")
        if self.rejection_mode not in ("inner", "mid", "edge"):
            raise ValueError("rejection_mode must be 'inner', 'mid' or 'edge'")

        self._fired_setups: "OrderedDict[str, int]" = OrderedDict()
        self._fired_zones: List[Tuple[Optional[pd.Timestamp], int, float]] = []
        self._pending: Optional[Dict[str, Any]] = None
        self._cooldown_until: Optional[pd.Timestamp] = None
        self._last_fire_ts: Optional[pd.Timestamp] = None

        self.min_bars_required = max(
            self.atr_period,
            2 * self.swing_lookback + 1,
            self.trend_ema_period or 0,
        ) + 5

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def generate_signal(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        if df is None or len(df) == 0:
            return None
        if self.drop_forming_bar:
            df = df.iloc[:-1]
        if len(df) < self.min_bars_required:
            return None

        df = df.reset_index(drop=True)
        df.columns = [str(c).lower() for c in df.columns]
        if not {"open", "high", "low", "close"}.issubset(df.columns):
            logger.warning("MirrorStrategy: missing OHLC columns")
            return None
        if not self._session_ok(df):
            return None

        i = len(df) - 1  # last CLOSED bar
        atr_series = self._atr(df)
        atr_now = float(atr_series.iat[i]) if i < len(atr_series) else np.nan
        if not np.isfinite(atr_now) or atr_now <= 0:
            return None

        # --- A5: news-bar / volatility filter --------------------------
        if self.atr_max_median_mult is not None:
            lo = max(0, i - self.atr_median_lookback + 1)
            seg = atr_series.values[lo:i + 1]
            seg = seg[np.isfinite(seg)]
            if len(seg) >= 30:
                med = float(np.median(seg))
                if med > 0 and atr_now > self.atr_max_median_mult * med:
                    return None

        bar_sec = self._infer_bar_seconds(df)
        cur_ts = self._now_ts(df, i)

        # --- A3: loss cooldown / post-signal spacing -------------------
        if self._blocked_by_cooldown(cur_ts, bar_sec):
            return None

        # --- A2: resolve an armed confirmation before new setups -------
        # (uses its own stored leg; independent of the current swing state)
        if self._pending is not None:
            sig = self._resolve_pending(df, i, cur_ts, bar_sec)
            if sig is not None:
                return sig

        swing_high, swing_low = self._compute_swings(df)
        leg = self._get_latest_anchor_leg(swing_high.values, swing_low.values, df, i)
        if leg is None:
            return None
        if leg.size < self.min_leg_size_atr_mult * atr_now:
            return None
        if (i - leg.end_idx) > self.max_leg_age_bars:
            return None
        if self._leg_origin_broken(df, leg, i, atr_now):
            return None

        if self.enable_eq_setup:
            sig = self._check_eq_setup(df, leg, i, atr_now, bar_sec)
            if sig is not None:
                return sig
        if self.enable_mirror_setup:
            sig = self._check_mirror_setup(df, leg, i, atr_now, bar_sec)
            if sig is not None:
                return sig
        return None

    def reset_state(self) -> None:
        self._fired_setups.clear()
        self._fired_zones.clear()
        self._pending = None
        self._cooldown_until = None
        self._last_fire_ts = None

    # ------------------------------------------------------------------
    # A3: called by the backtest runner / live executor after a trade
    # closes. A loss activates a cooldown.
    # ------------------------------------------------------------------
    def on_trade_result(self, result: str, exit_time, cooldown_seconds: float = 0.0) -> None:
        if result != "loss" or cooldown_seconds <= 0:
            return
        ts = self._to_ts(exit_time)
        if ts is None:
            return
        until = ts + pd.Timedelta(seconds=float(cooldown_seconds))
        if self._cooldown_until is None or until > self._cooldown_until:
            self._cooldown_until = until

    # ------------------------------------------------------------------
    # Time helpers (timestamp-based state: backtest windows slide)
    # ------------------------------------------------------------------
    def _get_bar_time(self, df, idx):
        for col in ("time", "timestamp", "datetime", "date"):
            if col in df.columns:
                return df[col].iat[idx]
        return int(idx)

    def _to_ts(self, x) -> Optional[pd.Timestamp]:
        try:
            if isinstance(x, (int, float, np.integer, np.floating)) and not isinstance(x, bool):
                ts = float(x)
                if ts > 1e12:
                    ts /= 1000.0
                return pd.Timestamp(ts, unit="s")
            return pd.Timestamp(x)
        except Exception:
            return None

    def _now_ts(self, df, i) -> Optional[pd.Timestamp]:
        return self._to_ts(self._get_bar_time(df, i))

    def _infer_bar_seconds(self, df: pd.DataFrame) -> float:
        if "time" not in df.columns or len(df) < 3:
            return 300.0
        try:
            s = pd.to_datetime(pd.Series(df["time"].values[-60:]))
            d = s.diff().dt.total_seconds().dropna()
            d = d[d > 0]
            return float(d.median()) if len(d) else 300.0
        except Exception:
            return 300.0

    def _time_to_index(self, df, raw_time) -> Optional[int]:
        if raw_time is None or "time" not in df.columns:
            return None
        try:
            hits = df.index[df["time"] == raw_time]
            return int(hits[0]) if len(hits) else None
        except Exception:
            return None

    def _blocked_by_cooldown(self, cur_ts, bar_sec) -> bool:
        if cur_ts is None:
            return False
        if self._cooldown_until is not None and cur_ts < self._cooldown_until:
            return True
        if (self.post_signal_cooldown_bars > 0 and self._last_fire_ts is not None):
            spacing = pd.Timedelta(seconds=self.post_signal_cooldown_bars * bar_sec)
            if cur_ts < self._last_fire_ts + spacing:
                return True
        return False

    # ------------------------------------------------------------------
    # Session filter (hours in YOUR DATA's timezone — MT5 server is
    # usually UTC+2/+3, not UTC). None = disabled.
    # ------------------------------------------------------------------
    def _session_ok(self, df: pd.DataFrame) -> bool:
        if not self.sessions:
            return True
        if "time" not in df.columns or len(df) == 0:
            return True
        t = df["time"].iloc[-1]
        try:
            if isinstance(t, (int, float, np.integer, np.floating)) and not isinstance(t, bool):
                ts = float(t)
                if ts > 1e12:
                    ts /= 1000.0
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            else:
                dt = pd.to_datetime(t)
            hour = dt.hour + dt.minute / 60.0
        except Exception:
            return True
        for s, e in self.sessions:
            if s <= e:
                if s <= hour < e:
                    return True
            else:  # wraps midnight
                if hour >= s or hour < e:
                    return True
        return False

    # ------------------------------------------------------------------
    # Swings (non-repainting: a swing at bar j confirms at bar j+L)
    # ------------------------------------------------------------------
    def _compute_swings(self, df: pd.DataFrame):
        L = self.swing_lookback
        window = 2 * L + 1
        roll_high = df["high"].rolling(window=window, center=True, min_periods=window).max()
        roll_low = df["low"].rolling(window=window, center=True, min_periods=window).min()
        swing_high = (df["high"] == roll_high).fillna(False)
        swing_low = (df["low"] == roll_low).fillna(False)
        return swing_high, swing_low

    def _atr(self, df: pd.DataFrame) -> pd.Series:
        high, low, close = df["high"], df["low"], df["close"]
        prev_close = close.shift(1)
        tr = pd.concat([(high - low), (high - prev_close).abs(),
                        (low - prev_close).abs()], axis=1).max(axis=1)
        return tr.rolling(window=self.atr_period, min_periods=self.atr_period).mean()

    def _get_latest_anchor_leg(self, swing_high: np.ndarray, swing_low: np.ndarray,
                               df: pd.DataFrame, i: int) -> Optional[AnchorLeg]:
        high_idx = np.where(swing_high)[0]
        low_idx = np.where(swing_low)[0]
        if len(high_idx) == 0 or len(low_idx) == 0:
            return None

        last_high, last_low = int(high_idx[-1]), int(low_idx[-1])
        if last_high > last_low:
            end_idx, end_is_high = last_high, True
            cands = low_idx[low_idx < end_idx]
            if len(cands) == 0:
                return None
            start_idx, start_is_high = int(cands[-1]), False
        else:
            end_idx, end_is_high = last_low, False
            cands = high_idx[high_idx < end_idx]
            if len(cands) == 0:
                return None
            start_idx, start_is_high = int(cands[-1]), True

        start_price = float(df["high"].iat[start_idx] if start_is_high else df["low"].iat[start_idx])
        end_price = float(df["high"].iat[end_idx] if end_is_high else df["low"].iat[end_idx])
        size = abs(end_price - start_price)
        if size <= 0:
            return None

        direction = 1 if end_price > start_price else -1
        return AnchorLeg(
            start_idx=start_idx, end_idx=end_idx,
            start_price=start_price, end_price=end_price,
            direction=direction, size=size,
            eq_price=(start_price + end_price) / 2.0,
            mirror_price=end_price + direction * size,
        )

    # ------------------------------------------------------------------
    # Invalidation
    # ------------------------------------------------------------------
    def _zone_invalidated(self, df, zone_price, reject_direction, lo, hi, atr_now, buf_mult):
        if hi <= lo:
            return False
        closes = df["close"].values[lo:hi]
        return bool(np.any(reject_direction * (closes - zone_price) < -(atr_now * buf_mult)))

    def _eq_invalidated(self, df, leg, i, atr_now):
        return self._zone_invalidated(df, leg.eq_price, leg.direction,
                                      leg.end_idx + 1, i, atr_now,
                                      self.eq_invalidation_atr_mult)

    def _mirror_invalidated(self, df, leg, i, atr_now):
        return self._zone_invalidated(df, leg.mirror_price, -leg.direction,
                                      leg.end_idx + 1, i, atr_now,
                                      self.mirror_invalidation_atr_mult)

    def _leg_origin_broken(self, df, leg, i, atr_now):
        closes = df["close"].values[leg.end_idx + 1: i + 1]
        if len(closes) == 0:
            return False
        return bool(np.any(leg.direction * (closes - leg.start_price)
                           < -(atr_now * self.origin_break_atr_mult)))

    # ------------------------------------------------------------------
    # PA reversal candles
    # ------------------------------------------------------------------
    def _reversal_confirmed(self, df, i, d):
        return self._bullish_reversal(df, i) if d == 1 else self._bearish_reversal(df, i)

    def _bullish_reversal(self, df, i):
        o, h, l, c = (float(df[k].iat[i]) for k in ("open", "high", "low", "close"))
        rng = h - l
        if rng <= 0:
            return False
        body = abs(c - o)
        lower = min(o, c) - l
        upper = h - max(o, c)
        is_pin = (lower >= self.pin_wick_body_ratio * max(body, 1e-12)
                  and lower > upper
                  and lower >= 0.5 * rng
                  and c >= l + 0.5 * rng)
        is_engulf = False
        if i > 0:
            po, pc = float(df["open"].iat[i - 1]), float(df["close"].iat[i - 1])
            is_engulf = (pc < po and c > o
                         and min(o, c) <= min(po, pc) and max(o, c) >= max(po, pc))
        return bool(is_pin or is_engulf)

    def _bearish_reversal(self, df, i):
        o, h, l, c = (float(df[k].iat[i]) for k in ("open", "high", "low", "close"))
        rng = h - l
        if rng <= 0:
            return False
        body = abs(c - o)
        lower = min(o, c) - l
        upper = h - max(o, c)
        is_pin = (upper >= self.pin_wick_body_ratio * max(body, 1e-12)
                  and upper > lower
                  and upper >= 0.5 * rng
                  and c <= h - 0.5 * rng)
        is_engulf = False
        if i > 0:
            po, pc = float(df["open"].iat[i - 1]), float(df["close"].iat[i - 1])
            is_engulf = (pc > po and c < o
                         and min(o, c) <= min(po, pc) and max(o, c) >= max(po, pc))
        return bool(is_pin or is_engulf)

    # ------------------------------------------------------------------
    # A4: optional EMA bias — continuation setups only
    # ------------------------------------------------------------------
    def _bias_ok(self, df, i, direction):
        if not self.trend_ema_period:
            return True
        ema = df["close"].ewm(span=self.trend_ema_period, adjust=False).mean().iat[i]
        c = float(df["close"].iat[i])
        return (c > ema) if direction == 1 else (c < ema)

    # ------------------------------------------------------------------
    # A1: rejection strictness of the tap bar's close
    # ------------------------------------------------------------------
    def _rejection_ok(self, close, zone_low, zone_high, mid, d) -> bool:
        if self.rejection_mode == "inner":
            return close >= zone_low if d == 1 else close <= zone_high
        if self.rejection_mode == "mid":
            return close >= mid if d == 1 else close <= mid
        # "edge": close fully back on the entry side of the zone
        return close >= zone_high if d == 1 else close <= zone_low

    # ------------------------------------------------------------------
    # A3: same-zone re-entry block (timestamp-based, ATR tolerance)
    # ------------------------------------------------------------------
    def _register_zone(self, df, i, d, price):
        self._fired_zones.append((self._now_ts(df, i), d, round(float(price), self.price_decimals)))
        while len(self._fired_zones) > 100:
            self._fired_zones.pop(0)

    def _zone_blocked(self, df, i, d, price, atr_now, bar_sec) -> bool:
        if self.zone_reentry_block_bars <= 0 or not self._fired_zones:
            return False
        cur_ts = self._now_ts(df, i)
        if cur_ts is None:
            return False
        window = pd.Timedelta(seconds=self.zone_reentry_block_bars * bar_sec)
        tol = self.zone_reentry_atr_mult * atr_now
        for ts, d0, p0 in reversed(self._fired_zones):     # newest first
            if ts is None:
                continue
            if cur_ts - ts > window:
                break                                      # older than window -> all before are too
            if d0 == d and abs(p0 - price) <= tol:
                return True
        return False

    # ------------------------------------------------------------------
    # A2: pending-confirmation machinery
    # ------------------------------------------------------------------
    def _arm_pending(self, df, i, leg, setup_type, d, stop_loss, take_profit,
                     atr_now, fp, zone_price):
        self._pending = {
            "leg": leg,
            "setup_type": setup_type,
            "direction": d,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "atr": atr_now,
            "fingerprint": fp,
            "zone_price": zone_price,
            "tap_ts": self._now_ts(df, i),
            # raw times (not indices): the backtest window slides every bar
            "leg_start_raw": self._get_bar_time(df, leg.start_idx),
            "leg_end_raw": self._get_bar_time(df, leg.end_idx),
        }

    def _relocate_leg(self, df, leg, start_raw, end_raw) -> Optional[AnchorLeg]:
        si = self._time_to_index(df, start_raw)
        ei = self._time_to_index(df, end_raw)
        if si is None or ei is None or ei <= si:
            return None
        return replace(leg, start_idx=si, end_idx=ei)

    def _resolve_pending(self, df, i, cur_ts, bar_sec) -> Optional[Dict[str, Any]]:
        p = self._pending
        if p is None:
            return None
        tap_ts = p["tap_ts"]
        if cur_ts is not None and tap_ts is not None:
            delta = (cur_ts - tap_ts).total_seconds()
            if delta <= 0:
                return None                       # same bar (live re-poll): keep armed
            if delta > 2.5 * bar_sec:
                self._pending = None              # stale: confirmation bar was missed
                return None
        self._pending = None                      # consume: fire or discard

        o, h, l, c = (float(df[k].iat[i]) for k in ("open", "high", "low", "close"))
        d = p["direction"]
        # confirmation bar must close in the trade direction ...
        if d == 1 and not (c > o):
            return None
        if d == -1 and not (c < o):
            return None
        # ... and must not have traded through the stop
        if d == 1 and l <= p["stop_loss"]:
            return None
        if d == -1 and h >= p["stop_loss"]:
            return None
        leg = self._relocate_leg(df, p["leg"], p["leg_start_raw"], p["leg_end_raw"])
        if leg is None:
            return None
        if p["setup_type"] == "eq_continuation":
            if self._eq_invalidated(df, leg, i, p["atr"]):
                return None
        else:
            if self._mirror_invalidated(df, leg, i, p["atr"]):
                return None

        sig = self._build_signal(df, i, leg, p["setup_type"], d, c,
                                 p["stop_loss"], p["take_profit"], p["atr"])
        if sig is None:
            return None
        self._mark_fired(p["fingerprint"], i)
        self._register_zone(df, i, d, p["zone_price"])
        self._last_fire_ts = cur_ts
        return sig

    # ------------------------------------------------------------------
    # Setups
    # ------------------------------------------------------------------
    def _check_eq_setup(self, df, leg, i, atr_now, bar_sec):
        if self._eq_invalidated(df, leg, i, atr_now):
            return None
        if not self._bias_ok(df, i, leg.direction):
            return None

        half = self.eq_zone_atr_mult * atr_now
        zone_low, zone_high = leg.eq_price - half, leg.eq_price + half
        h, l, c = float(df["high"].iat[i]), float(df["low"].iat[i]), float(df["close"].iat[i])

        # A1: directional tap + rejection close of configurable strictness
        if leg.direction == 1:
            tapped = l <= zone_high
            held = self._rejection_ok(c, zone_low, zone_high, leg.eq_price, 1)
        else:
            tapped = h >= zone_low
            held = self._rejection_ok(c, zone_low, zone_high, leg.eq_price, -1)
        if not (tapped and held):
            return None
        if not self._reversal_confirmed(df, i, leg.direction):
            return None

        fp = f"{self._leg_fingerprint_base(df, leg)}|eq|{leg.direction}"
        if fp in self._fired_setups:
            return None
        if self._zone_blocked(df, i, leg.direction, leg.eq_price, atr_now, bar_sec):
            return None

        pad = atr_now * self.stop_padding_atr_mult
        if leg.direction == 1:
            stop_loss = leg.start_price - pad                       # beyond origin
            take_profit = leg.end_price + self.eq_tp_extension * leg.size
            if l <= stop_loss:                                       # already blew the stop
                return None
        else:
            stop_loss = leg.start_price + pad
            take_profit = leg.end_price - self.eq_tp_extension * leg.size
            if h >= stop_loss:
                return None

        if self.confirm_next_close:                                  # A2: arm only
            self._arm_pending(df, i, leg, "eq_continuation", leg.direction,
                               stop_loss, take_profit, atr_now, fp, leg.eq_price)
            return None

        signal = self._build_signal(df, i, leg, "eq_continuation", leg.direction,
                                    c, stop_loss, take_profit, atr_now)
        if signal is None:
            return None
        self._mark_fired(fp, i)
        self._register_zone(df, i, leg.direction, leg.eq_price)
        self._last_fire_ts = self._now_ts(df, i)
        return signal

    def _check_mirror_setup(self, df, leg, i, atr_now, bar_sec):
        if self._mirror_invalidated(df, leg, i, atr_now):
            return None

        d = -leg.direction
        half = self.mirror_zone_atr_mult * atr_now
        zone_low, zone_high = leg.mirror_price - half, leg.mirror_price + half
        h, l, c = float(df["high"].iat[i]), float(df["low"].iat[i]), float(df["close"].iat[i])

        if d == 1:
            tapped = l <= zone_high
            held = self._rejection_ok(c, zone_low, zone_high, leg.mirror_price, 1)
        else:
            tapped = h >= zone_low
            held = self._rejection_ok(c, zone_low, zone_high, leg.mirror_price, -1)
        if not (tapped and held):
            return None
        if not self._reversal_confirmed(df, i, d):
            return None

        fp = f"{self._leg_fingerprint_base(df, leg)}|mirror|{d}"
        if fp in self._fired_setups:
            return None
        if self._zone_blocked(df, i, d, leg.mirror_price, atr_now, bar_sec):
            return None

        # SL beyond the MIRROR LINE (never beyond the 50% Eq)
        pad = max(atr_now * self.stop_padding_atr_mult,
                  self.mirror_sl_leg_frac * leg.size)
        if d == 1:
            stop_loss = leg.mirror_price - pad
            if l <= stop_loss:
                return None
        else:
            stop_loss = leg.mirror_price + pad
            if h >= stop_loss:
                return None
        take_profit = leg.eq_price if self.mirror_tp_mode == "eq" else leg.start_price

        if self.confirm_next_close:                                  # A2: arm only
            self._arm_pending(df, i, leg, "mirror_reversal", d,
                              stop_loss, take_profit, atr_now, fp, leg.mirror_price)
            return None

        signal = self._build_signal(df, i, leg, "mirror_reversal", d,
                                    c, stop_loss, take_profit, atr_now)
        if signal is None:
            return None
        self._mark_fired(fp, i)
        self._register_zone(df, i, d, leg.mirror_price)
        self._last_fire_ts = self._now_ts(df, i)
        return signal

    # ------------------------------------------------------------------
    # Risk / reward / assembly
    # ------------------------------------------------------------------
    def _risk_reward(self, entry, stop_loss, take_profit, d):
        cost = entry * self.spread_pct
        if d == 1:
            risk, reward = (entry - stop_loss) + cost, (take_profit - entry) - cost
        else:
            risk, reward = (stop_loss - entry) + cost, (entry - take_profit) - cost
        if risk <= 0 or reward <= 0:
            return None, None, None
        return reward / risk, risk, reward

    def _confidence(self, setup_type, rr):
        base = 0.60 if setup_type == "eq_continuation" else 0.50
        bonus = min(0.15, max(0.0, (rr - self.min_rr) * 0.05))
        return round(min(base + bonus, 0.90), 2)

    def _build_signal(self, df, i, leg, setup_type, d, entry, stop_loss, take_profit, atr_now):
        if d == 1 and not (stop_loss < entry < take_profit):
            return None
        if d == -1 and not (take_profit < entry < stop_loss):
            return None
        rr, risk, reward = self._risk_reward(entry, stop_loss, take_profit, d)
        if rr is None or rr < self.min_rr:
            return None
        p = self.price_decimals
        return {
            "strategy": "MMC",
            "setup_type": setup_type,
            "direction": "BUY" if d == 1 else "SELL",
            "entry": round(entry, p),
            "stop_loss": round(stop_loss, p),
            "take_profit": round(take_profit, p),
            "risk_reward": round(rr, 3),
            "risk": round(risk, p),
            "reward": round(reward, p),
            "atr": round(atr_now, p),
            "anchor_leg": {
                "start_price": round(leg.start_price, p),
                "end_price": round(leg.end_price, p),
                "direction": "bullish" if leg.direction == 1 else "bearish",
                "eq_price": round(leg.eq_price, p),
                "mirror_price": round(leg.mirror_price, p),
            },
            "signal_bar_index": i,
            "timestamp": self._get_bar_time(df, i),
            "confidence": self._confidence(setup_type, rr),
        }

    # ------------------------------------------------------------------
    # Dedup helpers
    # ------------------------------------------------------------------
    def _leg_fingerprint_base(self, df, leg):
        return f"{self._get_bar_time(df, leg.start_idx)}|{self._get_bar_time(df, leg.end_idx)}"

    def _mark_fired(self, fp, i):
        self._fired_setups[fp] = i
        while len(self._fired_setups) > self.max_fired_cache:
            self._fired_setups.popitem(last=False)

    # ------------------------------------------------------------------
    # LIVE TRADING WRAPPER — matches SmartMoneyStrategy's interface
    # ------------------------------------------------------------------
    async def analyze(self, pair: str, candles: list, config: dict) -> Optional[Signal]:
        df = pd.DataFrame(candles)
        if len(df) < self.min_bars_required:
            return None
        result = self.generate_signal(df)
        if result is None:
            return None
        return Signal(
            action=result["direction"].lower(),
            pair=pair,
            lot_size=config.get("lot_size", 0.01),
            stop_loss=result["stop_loss"],
            take_profit=result["take_profit"],
            confidence=result.get("confidence", 0.70),
            reason=f"MMC {result['setup_type']} (RR {result['risk_reward']})",
        )


__all__ = ["MirrorStrategy", "AnchorLeg"]


# --------------------------------------------------------------------------
# Quick self-test (safe to delete)
# --------------------------------------------------------------------------
if __name__ == "__main__":
    rng = np.random.default_rng(42)
    n = 800
    t = pd.date_range("2024-01-01", periods=n, freq="5min")
    close = 2000 + rng.normal(0, 1, n).cumsum() * 0.5 + np.sin(np.linspace(0, 20, n)) * 15
    open_ = np.roll(close, 1) + rng.normal(0, 0.3, n)
    open_[0] = close[0]
    high = np.maximum(open_, close) + np.abs(rng.normal(0, 0.8, n))
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 0.8, n))
    data = pd.DataFrame({"time": t, "open": open_, "high": high, "low": low, "close": close})

    strat = MirrorStrategy(drop_forming_bar=False, rejection_mode="inner",
                           confirm_next_close=True)
    signals = []
    for k in range(strat.min_bars_required, n):
        sig = strat.generate_signal(data.iloc[:k + 1].reset_index(drop=True))
        if sig:
            signals.append(sig)
    print(f"{len(signals)} signal(s) over {n} bars (confirm-mode smoke test)")
    for s in signals[:5]:
        print(s["setup_type"], s["direction"], "RR", s["risk_reward"], s["timestamp"])