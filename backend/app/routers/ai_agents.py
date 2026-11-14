"""
TradingAgents Multi-Agent Committee API Router
Endpoints to trigger on-demand market deliberation and inspect agent consensus.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from app.middleware import get_current_user
from app.services import metaapi_service as mt5
from app.services.trading_agents.committee import TradingAgentsCommittee

router = APIRouter(prefix="/api/ai-agents", tags=["ai-agents"])


class DeliberateRequest(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: str = "H1"
    candles_count: int = 100
    config: Optional[Dict[str, Any]] = None


@router.get("/status")
async def get_agents_status():
    """
    Returns the status, capabilities, and agent roster of the TradingAgents committee.
    """
    return {
        "status": "online",
        "framework": "TauricResearch/TradingAgents",
        "version": "1.0.0",
        "agents": [
            {
                "id": "technical_analyst",
                "name": "Senior Technical Analyst",
                "role": "Chart patterns, multi-timeframe structure, RSI, ATR, Moving Averages"
            },
            {
                "id": "fundamental_analyst",
                "name": "Macro & Fundamental Analyst",
                "role": "Interest rates, central bank policy, macroeconomic catalysts, yields"
            },
            {
                "id": "sentiment_analyst",
                "name": "Sentiment & Order Flow Analyst",
                "role": "Positioning skew, liquidity sweep zones, market psychology"
            },
            {
                "id": "bull_researcher",
                "name": "Lead Bull Researcher",
                "role": "Formulates upside catalysts and high-probability expansion thesis"
            },
            {
                "id": "bear_researcher",
                "name": "Lead Bear Researcher",
                "role": "Formulates downside risks, supply traps, and distribution thesis"
            },
            {
                "id": "risk_manager",
                "name": "Chief Risk Officer",
                "role": "Evaluates R:R (minimum 1.5:1), invalidation stops, and drawdown protection"
            },
            {
                "id": "portfolio_trader",
                "name": "Lead Portfolio Trader",
                "role": "Final binding consensus verdict (BUY, SELL, or HOLD) with confidence score"
            }
        ]
    }


@router.post("/deliberate")
async def deliberate_symbol(
    req: DeliberateRequest,
    user=Depends(get_current_user)
):
    """
    Triggers an institutional multi-agent debate for the requested trading pair.
    Fetches live candles via MT5 and executes deliberation across all 6 specialized agents.
    """
    symbol = req.symbol.upper().strip()
    timeframe = req.timeframe.upper().strip()

    # Attempt to fetch live candles from MT5 terminal
    candles = []
    try:
        candles = await mt5.get_candles(symbol, timeframe, count=req.candles_count)
    except Exception:
        candles = []

    # If terminal has no candle data (e.g. offline or market closed), return clean error
    if not candles or len(candles) < 20:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient real-time candle data available for '{symbol}' ({timeframe}). Ensure symbol is active in MT5 Market Watch."
        )

    result = await TradingAgentsCommittee.deliberate(symbol, candles, req.config)
    return result
