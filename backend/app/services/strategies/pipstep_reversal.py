"""
PipStep Reversal Bot (Python Port of PipStep_Reversal_EA.mq5)
Author: Ihsan Ullah / Trade-AI
Logic:
  1. Places symmetrical BuyStop + SellStop pending orders at entry_pips from price.
  2. When one triggers into an active position, immediately deletes the opposite pending stop.
  3. Manages Step Trailing Stop:
     - Steps: 1 step profit -> SL to entry (breakeven).
     - 2 steps profit -> SL to entry + 1 step.
     - 3 steps profit -> SL to entry + 2 steps, etc.
  4. On SL hit: Instantly opens market order in opposite direction (reversal).
  5. Daily risk stop and profit cap: halts when daily loss or profit % target is hit.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import logging
from .base import BaseStrategy, Signal

logger = logging.getLogger(__name__)


class PipStepReversalBot(BaseStrategy):
    name = "pipstep_reversal"
    description = "BuyStop/SellStop pair with dynamic step trailing SL, auto-cancellation, and instant reversal on SL hit"
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
        self.magic_number = magic_number
        self.comment = comment

        # Runtime State
        self.state = "ARMED"  # "ARMED" | "IN_TRADE" | "NEED_REVERSAL" | "HALTED"
        self.last_dir = 0     # +1 buy, -1 sell
        self.next_dir = 0     # direction for reversal
        self.pos_id = 0
        self.reversals_count = 0
        self.day_key = 0
        self.day_start_equity = 0.0
        self.fails = 0
        self.next_try_time = 0
        self.next_modify_time = 0

    def detect_pip(self, symbol: str, digits: int = 5) -> float:
        """Determines the pip value in price units."""
        if self.pip_price > 0.0:
            return self.pip_price
        s = symbol.upper()
        if any(m in s for m in ["XAU", "XAG", "GOLD", "SILVER"]):
            return 0.10  # 1 pip = 0.10 ($1.00 = 10 pips)
        if any(c in s for c in ["BTC", "ETH"]):
            return 1.00
        if "JPY" in s:
            return 0.01
        if digits in (3, 5):
            return 10.0 * (10 ** -digits)
        return 10 ** -digits

    def update_day(self, equity: float, now: datetime = None):
        """Update day-start equity and reset halted state at the start of a new calendar day."""
        if now is None:
            now = datetime.now(timezone.utc)
        key = now.year * 10000 + now.month * 100 + now.day
        if key != self.day_key:
            self.day_key = key
            self.day_start_equity = equity
            if self.state == "HALTED":
                self.state = "ARMED"
                logger.info("[PIPSTEP] New day started. Resuming trading.")

    def check_daily_limits(self, current_equity: float) -> Optional[str]:
        """Check if daily equity loss or profit target limit is breached."""
        if self.day_start_equity <= 0:
            self.day_start_equity = current_equity
            return None
        pnl_pct = ((current_equity - self.day_start_equity) / self.day_start_equity) * 100.0
        if pnl_pct <= -self.daily_loss_pct:
            return f"Daily max loss reached ({pnl_pct:.2f}% <= -{self.daily_loss_pct}%)"
        if pnl_pct >= self.daily_profit_pct:
            return f"Daily profit target reached ({pnl_pct:.2f}% >= +{self.daily_profit_pct}%)"
        return None

    def calculate_step_trailing_sl(
        self,
        direction: int,
        open_price: float,
        current_sl: float,
        current_price: float,
        pip_unit: float
    ) -> Optional[float]:
        """
        Step trailing stop loss calculation:
        steps = floor(profit / (step_pips * pip_unit))
        steps = 1 -> SL to entry (breakeven)
        steps = 2 -> SL to entry + 1 * step
        steps = 3 -> SL to entry + 2 * steps
        """
        profit = (current_price - open_price) if direction > 0 else (open_price - current_price)
        step_dist = self.step_pips * pip_unit
        if step_dist <= 0:
            return None

        steps = int(profit // step_dist)
        if steps < 1:
            return None

        desired_sl = open_price + direction * (steps - 1) * step_dist

        # Only trail forward, never backwards
        if direction > 0:
            if current_sl is not None and current_sl > 0 and desired_sl <= current_sl:
                return None
        else:
            if current_sl is not None and current_sl > 0 and desired_sl >= current_sl:
                return None

        return desired_sl

    def generate_signal(self, df) -> Optional[dict]:
        """BaseStrategy compliance."""
        return None

    async def analyze(self, pair: str, candles: list, config: dict) -> Optional[Signal]:
        """Standard BaseStrategy async interface."""
        return None
