from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class AccountCreate(BaseModel):
    nickname: str = ""
    broker: str = "metaapi"
    login: str
    password: str
    server: str
    account_type: str = "demo"

class AccountUpdate(BaseModel):
    nickname: Optional[str] = None
    account_type: Optional[str] = None

class AccountOut(BaseModel):
    id: str
    user_id: str
    nickname: str
    broker: str
    login: str
    server: str
    account_type: str
    balance: float
    equity: float
    profit: float
    status: str
    created_at: str

class ConnectResponse(BaseModel):
    success: bool
    message: str
    balance: Optional[float] = None
    equity: Optional[float] = None
