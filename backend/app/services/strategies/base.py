"""
Abstract base class for all trading strategies.
Each strategy implements analyze() which returns a Signal or None.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class Signal:
    action: str       # 'buy' or 'sell'
    pair: str
    lot_size: float
    stop_loss: float
    take_profit: float
    confidence: float  # 0.0 to 1.0
    reason: str


class BaseStrategy(ABC):
    name: str = ""
    description: str = ""
    timeframe: str = "H1"

    @abstractmethod
    def generate_signal(self, df) -> Optional[dict]:
        """
        Analyze market data using a pandas DataFrame and return a signal dict or None.
        This is the core analysis method — takes a DataFrame with 'open','high','low','close' columns.
        """
        pass

    async def analyze(self, pair: str, candles: list, config: dict) -> Optional[Signal]:
        """
        Analyze market data and return a trading signal or None.
        candles: list of {time, open, high, low, close, volume}
        config: strategy-specific settings from bot_settings.config
        """
        raise NotImplementedError("Subclasses must implement analyze() for the async path")

    def calculate_sl_tp(self, entry: float, direction: str, sl_pips: float, tp_pips: float, pip_value: float = 0.0001):
        """Calculate stop loss and take profit prices."""
        if direction == "buy":
            sl = entry - (sl_pips * pip_value)
            tp = entry + (tp_pips * pip_value)
        else:
            sl = entry + (sl_pips * pip_value)
            tp = entry - (tp_pips * pip_value)
        return round(sl, 5), round(tp, 5)
