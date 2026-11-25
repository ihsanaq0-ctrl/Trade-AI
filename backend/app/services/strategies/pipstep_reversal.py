"""
PipStep Reversal Bot (1:1 Python Port of PipStep_Reversal_EA.mq5)
Author: Ihsan Ullah / Trade-AI

Exact EA Logic:
  1. Entry: Symmetrical BuyStop + SellStop pair at EntryPips from price (auto-widened to MinStopDist + spread).
  2. Initial SL: InpSLPips from entry (no Take Profit).
  3. On Fill: Delete opposite pending orders; start trailing stop.
  4. Step Trailing Stop:
     - steps = floor(profit / (StepPips * pip) + 1e-9)
     - steps >= 1 -> desired SL = open + dir * (steps - 1) * stepDist
     - Never moves backwards; respects MinStopDist() and NormalizePrice(tick_size).
     - Safety: if active position somehow has SL == 0.0, sets initial SL immediately.
  5. Close classification (handles MT5 history lag up to 3 seconds):
     - DEAL_REASON_SL (4) -> instant opposite market order (OpenMarket) with InpMagic & InpDeviationPips.
     - Any other close reason -> re-arm BuyStop + SellStop pair.
  6. Send control & backoff:
     - CanSend() checks terminal Algo Trading, API trading, account/EA flags, full symbol trade mode, max spread.
     - OnSendFail() applies exponential backoff (RetryCooldownSec .. MaxBackoffSec, min 600s for 10026/10027/10017),
       while immediately recovering if MT5 terminal Algo Trading flips back ON.
  7. Daily risk management:
     - Halts until next server day when equity P/L <= -DailyLossPct or >= +DailyProfitPct, closing EA's own positions & pendings.
"""

from typing import Optional, Tuple
from datetime import datetime, timezone
import logging
import math
from .base import BaseStrategy, Signal

logger = logging.getLogger(__name__)


class PipStepReversalBot(BaseStrategy):
    name = "pipstep_reversal"
    description = "BuyStop/SellStop straddle pair, dynamic step trailing SL, and instant reversal on SL hit"
    timeframe = "M1"

    def __init__(
        self,
        lots: float = 0.01,
        entry_pips: float = 10.0,
        sl_pips: float = 10.0,
        step_pips: float = 10.0,
        pip_price: float = 0.0,
        max_spread_pips: float = 0.0,
        deviation_pips: float = 3.0,
        daily_loss_pct: float = 10.0,
        daily_profit_pct: float = 20.0,
        retry_cooldown_sec: int = 15,
        max_backoff_sec: int = 1800,
        delete_on_remove: bool = True,
        magic_number: int = 26110401,
        comment: str = "PIPSTEP",
        **kwargs
    ):
        super().__init__(**kwargs)
        self.lots = lots
        self.entry_pips = entry_pips
        self.sl_pips = sl_pips
        self.step_pips = step_pips
        self.pip_price = pip_price
        self.max_spread_pips = max_spread_pips
        self.deviation_pips = deviation_pips
        self.daily_loss_pct = daily_loss_pct
        self.daily_profit_pct = daily_profit_pct
        self.retry_cooldown_sec = max(1, int(retry_cooldown_sec))
        self.max_backoff_sec = max(self.retry_cooldown_sec, int(max_backoff_sec))
        self.delete_on_remove = bool(delete_on_remove)
        self.magic_number = int(magic_number)
        self.comment = str(comment or "PIPSTEP")

        # Runtime State (mirrors ENUM_STATE + EA globals)
        self.state = "ARMED"  # "ARMED" | "IN_TRADE" | "NEED_REVERSAL" | "HALTED"
        self.last_dir = 0     # g_dir (+1 buy, -1 sell)
        self.next_dir = 0     # g_nextDir
        self.open_price = 0.0 # g_open
        self.pos_id = 0       # g_posId (POSITION_IDENTIFIER)
        self.close_start_time = 0.0  # g_closeStart

        self.next_try_time = 0.0     # g_nextTry
        self.next_modify_time = 0.0  # g_nextModify
        self.next_clean_time = 0.0   # g_nextClean
        self.fails = 0               # g_fails
        self.last_fail_retcode: Optional[int] = None

        self.day_key = 0             # g_dayKey
        self.day_start_equity = 0.0  # g_dayEq

        self.reversals_count = 0     # g_reversals
        self.last_msg = ""           # g_msg
        self.last_msg_time = 0.0     # g_msgTime

    def set_msg(self, s: str, now_ts: float = 0.0):
        if now_ts <= 0:
            now_ts = datetime.now(timezone.utc).timestamp()
        if s != self.last_msg or (now_ts - self.last_msg_time) >= 60:
            logger.info("[PIPSTEP] %s", s)
            self.last_msg_time = now_ts
        self.last_msg = s

    def detect_pip(self, symbol: str, digits: int = 5, point: Optional[float] = None) -> float:
        """Exact match to MQL5 DetectPip(), with guard against accidental lot-size-like 0.01 entry on 5-digit forex."""
        s = (symbol or "").upper()
        is_metal = any(m in s for m in ("XAU", "XAG", "GOLD", "SILVER"))
        is_jpy = "JPY" in s
        pt = float(point) if (point is not None and point > 0.0) else (10.0 ** -digits)
        auto_pip = 0.10 if is_metal else ((10.0 * pt) if digits in (3, 5) else pt)

        if self.pip_price > 0.0:
            # Guard: on standard 5-digit non-JPY forex pairs (e.g. EURUSDc where auto_pip = 0.0001),
            # a value >= 0.005 (like 0.01 entered by confusion with 0.01 lots) places orders 100x too far (1,000 pips).
            if digits == 5 and not is_metal and not is_jpy and self.pip_price >= 0.005:
                logger.warning(
                    "[PIPSTEP] Ignoring oversized pip_price=%s on 5-digit forex %s (100x+ real pip); using auto=%s.",
                    self.pip_price, symbol, auto_pip
                )
                return auto_pip
            return float(self.pip_price)
        return auto_pip

    def norm_price(self, p: float, tick_size: float = 0.0, digits: int = 5) -> float:
        """Exact match to MQL5 NormPrice() using SYMBOL_TRADE_TICK_SIZE."""
        if tick_size and tick_size > 0.0:
            return round(round(p / tick_size) * tick_size, digits)
        return round(p, digits)

    def min_stop_dist(self, stops_level: int = 0, freeze_level: int = 0, point: float = 0.00001) -> float:
        """Exact match to MQL5 MinStopDist()."""
        return float(max(int(stops_level or 0), int(freeze_level or 0))) * float(point or 0.0)

    def norm_lots(self, vmin: float = 0.01, vmax: float = 100.0, step: float = 0.01) -> float:
        """Exact match to MQL5 NormLots()."""
        lots = float(self.lots)
        if step and step > 0.0:
            lots = math.floor(lots / step + 1e-9) * step
        if vmin and vmin > 0.0:
            lots = max(vmin, lots)
        if vmax and vmax > 0.0:
            lots = min(vmax, lots)
        dg = int(round(-math.log10(step))) if (step and step > 0.0) else 2
        if dg < 0:
            dg = 0
        return round(lots, dg)

    def deviation_points(self, pip_unit: float, point: float) -> int:
        pt = point if point and point > 0.0 else 0.00001
        return max(1, int(round(self.deviation_pips * pip_unit / pt)))

    def can_send(
        self,
        now_ts: float,
        terminal_trade_allowed: bool,
        tradeapi_disabled: bool,
        account_trade_allowed: bool,
        account_trade_expert: bool,
        symbol_trade_mode_full: bool,
        spread: float,
        pip_unit: float,
    ) -> Tuple[bool, str]:
        """Exact match to MQL5 CanSend(), plus fast recovery when user toggles Algo Trading ON."""
        # If previously blocked only by terminal Algo Trading (10027) and user enabled it, resume immediately
        if (
            self.last_fail_retcode == 10027
            and terminal_trade_allowed
            and not tradeapi_disabled
            and account_trade_allowed
            and account_trade_expert
        ):
            self.on_send_ok()

        if now_ts < self.next_try_time:
            return False, self.last_msg

        if not terminal_trade_allowed or tradeapi_disabled:
            msg = "Algo trading is OFF in MetaTrader 5 terminal (press Ctrl+E or click Algo Trading). No orders sent."
            self.set_msg(msg, now_ts)
            self.last_fail_retcode = 10027
            self.next_try_time = now_ts + 15.0  # responsive terminal-flag check without sending broker orders
            return False, msg

        if not account_trade_allowed or not account_trade_expert:
            msg = "Broker has disabled trading/EA trading on this account (account flags). No orders sent."
            self.set_msg(msg, now_ts)
            self.last_fail_retcode = 10017
            self.next_try_time = now_ts + 60.0
            return False, msg

        if not symbol_trade_mode_full:
            msg = "Symbol trading is not fully enabled right now (market closed?)."
            self.set_msg(msg, now_ts)
            self.next_try_time = now_ts + 30.0
            return False, msg

        if self.max_spread_pips > 0.0 and pip_unit > 0.0:
            if spread > self.max_spread_pips * pip_unit:
                msg = f"Spread ({spread / pip_unit:.1f} pips) above max ({self.max_spread_pips} pips), waiting."
                self.set_msg(msg, now_ts)
                return False, msg

        return True, ""

    def on_send_ok(self):
        self.fails = 0
        self.next_try_time = 0.0
        self.last_fail_retcode = None

    def on_send_fail(self, retcode: Optional[int], desc: str, now_ts: float):
        """Exact match to MQL5 OnSendFail()."""
        self.fails += 1
        self.last_fail_retcode = retcode
        wait = self.retry_cooldown_sec
        for _ in range(1, self.fails):
            if wait >= self.max_backoff_sec:
                break
            wait *= 2
        wait = min(wait, self.max_backoff_sec)
        if retcode in (10026, 10027, 10017):
            wait = max(wait, 600)
        self.next_try_time = now_ts + wait
        rc_txt = str(retcode) if retcode is not None else "?"
        self.set_msg(f"Order failed rc={rc_txt} ({desc}). Next try in {wait} s.", now_ts)

    def update_day(self, equity: float, now: Optional[datetime] = None):
        """Match MQL5 UpdateDay(): track server day and resume from HALTED on new day."""
        if now is None:
            now = datetime.now(timezone.utc)
        key = now.year * 10000 + now.month * 100 + now.day
        if key != self.day_key:
            self.day_key = key
            self.day_start_equity = float(equity)
            if self.state == "HALTED":
                self.state = "ARMED"
                self.set_msg("New server day: trading resumed.", now.timestamp())

    def check_daily_limits(self, current_equity: float) -> Optional[str]:
        """Match MQL5 ManageDailyRisk(): halt if <= -DailyLossPct or >= +DailyProfitPct."""
        if self.state == "HALTED" or self.day_start_equity <= 0.0:
            if self.day_start_equity <= 0.0 and current_equity > 0.0:
                self.day_start_equity = float(current_equity)
            return None
        pnl_pct = ((float(current_equity) - self.day_start_equity) / self.day_start_equity) * 100.0
        if pnl_pct <= -self.daily_loss_pct or pnl_pct >= self.daily_profit_pct:
            return f"Daily limit reached ({pnl_pct:.2f}%). Halted until next server day."
        return None

    def calculate_step_trailing_sl(
        self,
        direction: int,
        open_price: float,
        current_sl: float,
        current_price: float,
        pip_unit: float,
        min_stop_dist: float = 0.0,
        tick_size: float = 0.0,
        digits: int = 5,
        cur_bid: Optional[float] = None,
        cur_ask: Optional[float] = None,
    ) -> Optional[float]:
        """
        Exact match to MQL5 TrailStop() + ModifySL():
          - If current_sl == 0.0, sets initial SL (open - dir * InpSLPips * g_pip)
          - steps = MathFloor(profit / stepD + 1e-9)
          - steps >= 1 -> desired = open + dir * (steps - 1) * stepD
          - Never moves backwards; obeys MinStopDist() and NormPrice().
        """
        if current_sl is None or float(current_sl) == 0.0:
            raw_init = open_price - direction * (self.sl_pips * pip_unit)
            desired = self.norm_price(raw_init, tick_size, digits)
        else:
            profit = (current_price - open_price) if direction > 0 else (open_price - current_price)
            step_dist = self.step_pips * pip_unit
            if step_dist <= 0.0:
                return None
            steps = int(math.floor(profit / step_dist + 1e-9))
            if steps < 1:
                return None
            raw_desired = open_price + direction * (steps - 1) * step_dist
            desired = self.norm_price(raw_desired, tick_size, digits)

        if direction > 0:
            if current_sl and float(current_sl) != 0.0 and desired <= float(current_sl):
                return None
            if cur_bid is not None and desired > (cur_bid - min_stop_dist):
                return None
        else:
            if current_sl and float(current_sl) != 0.0 and desired >= float(current_sl):
                return None
            if cur_ask is not None and desired < (cur_ask + min_stop_dist):
                return None

        return desired

    def generate_signal(self, df) -> Optional[dict]:
        """BaseStrategy compliance."""
        return None

    async def analyze(self, pair: str, candles: list, config: dict) -> Optional[Signal]:
        """Standard BaseStrategy async interface."""
        return None
