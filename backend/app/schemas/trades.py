from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class TradeOut(BaseModel):
    id: str
    user_id: str
    account_id: Optional[str] = None
    bot_id: Optional[str] = None
    strategy: Optional[str] = None
    pair: str
    type: str
    lot_size: float
    open_price: float
    close_price: Optional[float] = None
    profit: Optional[float] = None
    pips: Optional[float] = None
    status: str
    opened_at: str
    closed_at: Optional[str] = None

class TradeCloseRequest(BaseModel):
    ticket: str | int
    account_id: str | None = None

class TradeModifySlRequest(BaseModel):
    ticket: str | int
    account_id: str | None = None
    stop_loss: float | None = None
    take_profit: float | None = None

class TradePartialCloseRequest(BaseModel):
    ticket: str | int
    account_id: str | None = None
    close_pct: float

class TradeOpenRequest(BaseModel):
    symbol: str
    type: str  # BUY or SELL
    lot_size: float = 0.01
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    account_id: Optional[str] = None
    comment: Optional[str] = "Manual Trade"
    reason: Optional[str] = "Manual Analysis"

class TradeList(BaseModel):
    trades: list[TradeOut]
    total: int

