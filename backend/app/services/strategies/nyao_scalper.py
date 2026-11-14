"""
Bot 6: Nyao Scalper Bot (Trade Management & Risk Framework)
Requires: MetaTrader5, asyncio, logging
Extracted Concept: Scaled Partial Closes, Position Health Evaluation, Virtual SL & Re-entry.
NO Martingale, NO Grid, NO Hedge Chain.
"""

import MetaTrader5 as mt5
import asyncio
import logging
from typing import Tuple, Optional, Dict
from .base import BaseStrategy, Signal

logger = logging.getLogger(__name__)

class NyaoScalperBot(BaseStrategy):
    name = "nyao_scalper"
    description = "Nyao Scalper (Trade Mgmt & Position Health)"
    timeframe = "M1"

    def __init__(self, magic_number: int = 6926268, **kwargs):
        super().__init__(**kwargs)
        self.magic_number = magic_number
        
        # State tracking to prevent double-closes and map initial entry scores
        # Format: { ticket_id: {"level": 0, "initial_score": 8.5} }
        self.position_state: Dict[int, Dict] = {}

    # ---------------------------------------------------------------
    # HELPER: VOLUME NORMALIZATION
    # ---------------------------------------------------------------
    def _normalize_volume(self, symbol: str, volume: float) -> float:
        """Ensures the lot size matches the broker's min, max, and step requirements."""
        info = mt5.symbol_info(symbol)
        if info is None:
            logger.error(f"Symbol info not found for {symbol}")
            return 0.01
            
        min_vol = info.volume_min
        max_vol = info.volume_max
        step = info.volume_step
        
        # Round to nearest step
        normalized = round(volume / step) * step
        normalized = max(min_vol, min(normalized, max_vol))
        
        return round(normalized, 2)

    # ---------------------------------------------------------------
    # HELPER: EXECUTE PARTIAL / FULL CLOSE
    # ---------------------------------------------------------------
    async def _execute_close(self, position, volume_to_close: float, reason: str) -> bool:
        """Executes a market order to close a specific volume of a position."""
        symbol = position.symbol
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"Cannot get tick for {symbol}")
            return False

        # Ensure volume is normalized
        close_vol = self._normalize_volume(symbol, volume_to_close)
        
        # Ensure we don't try to close more than we have
        if close_vol > position.volume:
            close_vol = self._normalize_volume(symbol, position.volume)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": close_vol,
            "type": mt5.ORDER_TYPE_SELL if position.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY,
            "position": position.ticket,
            "price": tick.bid if position.type == mt5.POSITION_TYPE_BUY else tick.ask,
            "deviation": 20,
            "magic": self.magic_number,
            "comment": f"Nyao {reason}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            ret_comment = getattr(result, 'comment', 'No response from MT5')
            ret_code = getattr(result, 'retcode', 'None')
            logger.error(f"Close failed for {position.ticket}: {ret_comment} (retcode {ret_code})")
            return False
            
        logger.info(f"[{position.ticket}] {reason} successful. Closed {close_vol} lots.")
        return True

    # ---------------------------------------------------------------
    # 1. SCALED PARTIAL CLOSE ON SIGNAL DECAY
    # ---------------------------------------------------------------
    async def manage_partial_closes(self, position, current_signal_score: float, initial_signal_score: float) -> None:
        """
        Closes parts of the position as the signal strength decays.
        - 75% of initial score -> Close 25%
        - 50% of initial score -> Close 50%
        - 25% of initial score -> Close 100%
        """
        if initial_signal_score <= 0:
            return

        # Initialize state if new position
        if position.ticket not in self.position_state:
            self.position_state[position.ticket] = {"level": 0, "initial_score": initial_signal_score}

        state = self.position_state[position.ticket]
        if state["level"] == 3:  # Already fully closed by this logic
            return

        signal_ratio = current_signal_score / initial_signal_score
        current_vol = position.volume

        # Level 1: Drop to 75% -> Close 25%
        if signal_ratio <= 0.75 and state["level"] == 0:
            close_vol = current_vol * 0.25
            if await self._execute_close(position, close_vol, "L1 Partial Close"):
                state["level"] = 1

        # Level 2: Drop to 50% -> Close 50% of REMAINING volume
        elif signal_ratio <= 0.50 and state["level"] == 1:
            close_vol = current_vol * 0.50
            if await self._execute_close(position, close_vol, "L2 Partial Close"):
                state["level"] = 2

        # Level 3: Drop to 25% -> Close 100% Remaining
        elif signal_ratio <= 0.25 and state["level"] == 2:
            if await self._execute_close(position, current_vol, "L3 Full Exit"):
                state["level"] = 3

    # ---------------------------------------------------------------
    # 2. POSITION HEALTH EVALUATION
    # ---------------------------------------------------------------
    async def evaluate_position_health(self, position, current_atr: float, current_rsi: float, ema_fast: float, ema_slow: float) -> float:
        """
        Evaluates position health on a scale of 0.0 to 1.0.
        Closes position entirely if health < 0.40.
        """
        is_buy = position.type == mt5.POSITION_TYPE_BUY
        entry_price = position.price_open
        
        tick = mt5.symbol_info_tick(position.symbol)
        if not tick or current_atr <= 0:
            return 1.0  # Assume healthy if data is missing to prevent false closes

        current_price = tick.bid if is_buy else tick.ask
        score = 0.0

        # A. Trend Alignment (0.4 weight)
        trend_valid = (ema_fast > ema_slow) if is_buy else (ema_fast < ema_slow)
        if trend_valid:
            score += 0.4

        # B. RSI Zone (0.3 weight)
        # Buy: RSI should be between 40 (not oversold dying) and 70 (not overbought exhausted)
        # Sell: RSI should be between 30 and 60
        rsi_valid = False
        if is_buy and 40.0 <= current_rsi <= 70.0:
            rsi_valid = True
        elif not is_buy and 30.0 <= current_rsi <= 60.0:
            rsi_valid = True
            
        if rsi_valid:
            score += 0.3

        # C. Adverse ATR Movement (0.3 weight)
        adverse_move = 0.0
        if is_buy:
            adverse_move = entry_price - current_price  # Positive if losing
        else:
            adverse_move = current_price - entry_price  # Positive if losing
            
        adverse_atr_ratio = adverse_move / current_atr
        
        if adverse_atr_ratio <= 0:
            score += 0.3  # Not adverse at all
        elif adverse_atr_ratio <= 1.5:
            # Gradual decay: 1.0 at 0 ATR, 0.0 at 1.5 ATR
            score += 0.3 * (1.0 - (adverse_atr_ratio / 1.5))
        
        score = max(0.0, min(1.0, score))

        # Hard Virtual SL: Health decayed below 40%
        if score < 0.40:
            logger.warning(f"[{position.ticket}] Health decayed to {score:.2f}. Executing Virtual SL (Full Close).")
            await self._execute_close(position, position.volume, "Virtual SL (Health Decay)")
            if position.ticket in self.position_state:
                self.position_state[position.ticket]["level"] = 3

        return score

    # ---------------------------------------------------------------
    # 3. VIRTUAL SL & RE-ENTRY LOGIC
    # ---------------------------------------------------------------
    async def check_virtual_sl_reentry(self, closed_position, current_signal_score: float, initial_signal_score: float) -> Tuple[bool, Optional[dict]]:
        """
        If a position was just closed due to health decay, checks if signal is still
        strong enough (>= 75% of initial) to immediately re-enter.
        """
        if initial_signal_score <= 0:
            return False, None
            
        reentry_threshold = initial_signal_score * 0.75
        
        if current_signal_score >= reentry_threshold:
            logger.info(f"Virtual SL Re-entry triggered. Current Score: {current_signal_score:.2f} >= Threshold: {reentry_threshold:.2f}")
            
            tick = mt5.symbol_info_tick(closed_position.symbol)
            if not tick:
                return False, None
                
            is_buy = closed_position.type == mt5.POSITION_TYPE_BUY
            
            # Re-enter with the exact same volume as the closed position
            new_trade_params = {
                "symbol": closed_position.symbol,
                "order_type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
                "price": tick.ask if is_buy else tick.bid,
                "volume": self._normalize_volume(closed_position.symbol, closed_position.volume),
                "signal_score": current_signal_score  # Pass the new initial score
            }
            return True, new_trade_params
            
        return False, None

    # ---------------------------------------------------------------
    # STATE CLEANUP
    # ---------------------------------------------------------------
    def cleanup_state(self, ticket: int):
        """Call this when a position is fully closed externally to prevent memory leaks."""
        if ticket in self.position_state:
            del self.position_state[ticket]

    def generate_signal(self, df) -> Optional[dict]:
        """
        Adheres to BaseStrategy abstract method.
        NyaoScalperBot manages existing positions in real-time via _bot_loop_nyao_scalper.
        """
        return None

    async def analyze(self, pair: str, candles: list, config: dict) -> Optional[Signal]:
        """
        Adheres to BaseStrategy interface.
        NyaoScalperBot manages existing positions in real-time via _bot_loop_nyao_scalper.
        """
        return None
