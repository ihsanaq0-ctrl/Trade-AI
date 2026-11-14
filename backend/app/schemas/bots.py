from pydantic import BaseModel
from typing import Optional, Any

class BotCreate(BaseModel):
    account_id: str
    strategy: str
    pair: str = "EURUSD"
    timeframe: str = "H1"
    lot_size: float = 0.01
    take_profit: float = 50
    stop_loss: float = 25
    max_trades: int = 1
    max_daily_loss: float = 100
    config: dict = {}

class BotUpdate(BaseModel):
    pair: Optional[str] = None
    timeframe: Optional[str] = None
    lot_size: Optional[float] = None
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    max_trades: Optional[int] = None
    max_daily_loss: Optional[float] = None
    config: Optional[dict] = None

class BotOut(BaseModel):
    id: str
    user_id: str
    account_id: str
    strategy: str
    status: str
    pair: str
    timeframe: str
    lot_size: float
    take_profit: float
    stop_loss: float
    max_trades: int
    max_daily_loss: float
    config: Any
    created_at: str
