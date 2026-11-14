from pydantic import BaseModel


class StrategyCreate(BaseModel):
    name: str
    code: str
