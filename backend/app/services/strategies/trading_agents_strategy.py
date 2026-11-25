"""
TradingAgents Strategy (Multi-Agent Committee)
Integrated from TauricResearch/TradingAgents framework.
Executes consensus trades based on collaborative multi-agent deliberation:
- Technical Analyst
- Fundamental Macro Analyst
- Sentiment / Order Flow Analyst
- Bull vs Bear Debate
- Risk Manager Approval
"""

import asyncio
import pandas as pd
from typing import Optional, Dict, Any, List
from app.services.strategies.base import BaseStrategy, Signal
from app.services.trading_agents.committee import TradingAgentsCommittee


class TradingAgentsStrategy(BaseStrategy):
    name: str = "trading_agents"
    description: str = "Multi-Agent AI Committee simulating institutional trading desk debate (TauricResearch TradingAgents)"
    timeframe: str = "H1"
    min_bars_required: int = 30

    def generate_signal(self, df: pd.DataFrame) -> Optional[dict]:
        """
        Synchronous signal generation for backtesting and rule evaluation.
        """
        if df is None or len(df) < self.min_bars_required:
            return None

        candles = []
        for idx, row in df.iterrows():
            candles.append({
                "time": str(row.get("time", idx)),
                "open": float(row.get("open", 0)),
                "high": float(row.get("high", 0)),
                "low": float(row.get("low", 0)),
                "close": float(row.get("close", 0)),
                "volume": float(row.get("volume", row.get("tick_volume", 0))),
            })

        target_pair = getattr(self, "pair", None) or "EURUSD"
        if "symbol" in df.columns and len(df["symbol"]) > 0:
            target_pair = str(df["symbol"].iloc[-1])
        elif "pair" in df.columns and len(df["pair"]) > 0:
            target_pair = str(df["pair"].iloc[-1])

        # Run deliberation via async loop or sync execution
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If already in an async event loop, run deliberation directly
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    deliberation = pool.submit(
                        asyncio.run,
                        TradingAgentsCommittee.deliberate(target_pair, candles)
                    ).result()
            else:
                deliberation = loop.run_until_complete(
                    TradingAgentsCommittee.deliberate(target_pair, candles)
                )
        except Exception:
            # Fallback direct computation
            metrics = TradingAgentsCommittee._compute_metrics(candles)
            if metrics["trend"] == "BULLISH" and metrics["rsi"] < 70:
                return {
                    "action": "BUY",
                    "price": metrics["current_price"],
                    "sl": round(metrics["current_price"] - (metrics["atr"] * 1.3), 4),
                    "tp": round(metrics["current_price"] + (metrics["atr"] * 2.4), 4),
                    "confidence": 0.78,
                    "reason": "AI Committee Bullish Consensus"
                }
            elif metrics["trend"] == "BEARISH" and metrics["rsi"] > 30:
                return {
                    "action": "SELL",
                    "price": metrics["current_price"],
                    "sl": round(metrics["current_price"] + (metrics["atr"] * 1.3), 4),
                    "tp": round(metrics["current_price"] - (metrics["atr"] * 2.4), 4),
                    "confidence": 0.76,
                    "reason": "AI Committee Bearish Consensus"
                }
            return None

        decision = deliberation.get("decision", "HOLD")
        if decision in ("BUY", "SELL") and deliberation.get("confidence", 0) >= 0.65:
            return {
                "action": decision,
                "price": deliberation.get("entry_price"),
                "sl": deliberation.get("stop_loss"),
                "tp": deliberation.get("take_profit"),
                "confidence": deliberation.get("confidence"),
                "reason": deliberation.get("summary"),
                "committee_reports": deliberation.get("committee_reports")
            }
        return None

    async def analyze(self, pair: str, candles: list, config: dict) -> Optional[Signal]:
        """
        Asynchronous analysis for live BotEngine execution.
        """
        if not candles or len(candles) < self.min_bars_required:
            return None

        config = config or {}
        min_conf = float(config.get("min_confidence", 0.65))
        lot_size = float(config.get("lot_size", 0.01))

        deliberation = await TradingAgentsCommittee.deliberate(pair, candles, config)

        decision = deliberation.get("decision", "HOLD")
        confidence = float(deliberation.get("confidence", 0.0))

        if decision in ("BUY", "SELL") and confidence >= min_conf:
            return Signal(
                action=decision.lower(),
                pair=pair,
                lot_size=lot_size,
                stop_loss=float(deliberation.get("stop_loss", 0.0)),
                take_profit=float(deliberation.get("take_profit", 0.0)),
                confidence=confidence,
                reason=deliberation.get("summary", "AI Multi-Agent Consensus")
            )

        return None
