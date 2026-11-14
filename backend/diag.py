"""Test: does the new rapid trend strategy generate signals on live M1 data?"""
import sys, os, asyncio
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()

from app.services import metaapi_service as mt5
from app.services.strategies.scalp_fvg import ScalpModeBot
from app.services.scalp_scheduler import _resolve_pip_specs
import pandas as pd

async def test():
    print("=" * 60)
    print("LIVE SIGNAL TEST — Rapid Trend Scalper")
    print("=" * 60)

    for pair in ['XAUUSD', 'EURUSD']:
        print(f"\n--- {pair} ---")
        resolved = mt5._resolve_symbol(pair)
        candles = await mt5.get_candles(resolved, "M1", 100)
        if not candles or len(candles) < 30:
            print(f"  Not enough candles: {len(candles or [])}")
            continue

        df = pd.DataFrame(candles)
        pv, ps = _resolve_pip_specs(pair)
        balance = 100.0

        bot = ScalpModeBot(initial_balance=balance)
        
        # Show trend info
        ema_f, ema_s = bot.calculate_emas(df)
        rsi = bot.calculate_rsi(df)
        atr = bot.calculate_atr(df)
        trend = bot.get_trend(ema_f, ema_s)
        
        print(f"  Price: {df['close'].iloc[-1]:.5f}")
        print(f"  EMA9:  {ema_f.iloc[-1]:.5f}  EMA21: {ema_s.iloc[-1]:.5f}")
        print(f"  Trend: {trend or 'FLAT/CHOPPY'}")
        print(f"  RSI:   {rsi.iloc[-1]:.1f}")
        print(f"  ATR:   {atr.iloc[-1]:.5f}")
        
        # FVG + OB scan
        fvgs = bot.detect_fvg(df, atr)
        obs = bot.detect_order_blocks(df, atr)
        print(f"  FVGs:  {len(fvgs)} detected")
        for f in fvgs[-3:]:
            print(f"    {f['type']:8s} top={f['top']:.3f} bot={f['bottom']:.3f}")
        print(f"  OBs:   {len(obs)} detected")
        for o in obs[-3:]:
            print(f"    {o['type']:8s} high={o['high']:.3f} low={o['low']:.3f}")
        
        # Pullback check
        pb = bot.is_pullback_entry(df, ema_f, trend)
        print(f"  Pullback to EMA9: {pb}")
        
        # Generate signal
        signal = bot.generate_signal(
            df, account_balance=balance,
            pip_value_per_lot=pv, lot_size=0.01, pip_size=ps
        )
        if signal:
            print(f"\n  >>> SIGNAL: {signal['action']} {signal['direction']}")
            print(f"      entry={signal.get('entry')}")
            print(f"      SL={signal.get('stop_loss')}, TP={signal.get('take_profit')}")
            print(f"      reason: {signal.get('reason')}")
        else:
            print(f"\n  No signal this cycle (trend={trend}, pullback={pb})")
            if trend and not pb:
                print(f"  Waiting for pullback to EMA9 or FVG/OB pattern...")

asyncio.run(test())
