from pydantic import BaseModel
from typing import Optional

class Overview(BaseModel):
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0
    total_profit: float = 0
    gross_profit: float = 0
    gross_loss: float = 0
    profit_factor: float = 0
    avg_profit: float = 0
    avg_pips: float = 0

class EquityPoint(BaseModel):
    date: str
    equity: float

class StrategyPerformance(BaseModel):
    strategy: str
    trades: int
    wins: int
    win_rate: float
    profit: float

class PairPerformance(BaseModel):
    pair: str
    trades: int
    win_rate: float
    profit: float

class MonthlyReturn(BaseModel):
    month: str
    profit: float
    trades: int

class DrawdownInfo(BaseModel):
    max_drawdown_pct: float
    max_drawdown_amount: float
    current_drawdown: float
