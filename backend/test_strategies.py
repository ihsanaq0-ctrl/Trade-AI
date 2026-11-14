"""
Quick smoke test: verify all 5 bots produce signals on structured data.

Bypasses pandas DataFrame overhead — feeds candle dicts directly,
running each bot against crafted trend data to confirm logic fires.
"""

import asyncio
import sys
import os
import random

sys.path.insert(0, os.path.dirname(__file__))

from app.services.strategies.smart_money import SmartMoneyStrategy
from app.services.strategies.mirror import MirrorStrategy
from app.services.strategies.classic import ClassicStrategy
from app.services.strategies.full_confluence import FullConfluenceStrategy
from app.services.strategies.scalp import ScalpStrategy

random.seed(42)


def build_trend_data(up: bool = True, length: int = 150) -> list:
    """
    Build clean trend data: clear swing points, a BOS, then a pullback.
    up=True  → uptrend: higher highs, pullback to OB
    up=False → downtrend: lower lows, pullback to OB
    """
    candles = []
    price = 1.0800 if up else 1.1200
    step = 0.002

    for i in range(length):
        if up:
            if i < 50:
                price += step * 0.3 + random.uniform(-0.0002, 0.0002)
            elif i < 70:
                price -= step * 0.15 + random.uniform(-0.0002, 0.0002)
            elif i < 110:
                price += step * 0.5 + random.uniform(-0.0002, 0.0002)
            else:
                price -= step * 0.25 + random.uniform(-0.0002, 0.0002)
        else:
            if i < 50:
                price -= step * 0.3 + random.uniform(-0.0002, 0.0002)
            elif i < 70:
                price += step * 0.15 + random.uniform(-0.0002, 0.0002)
            elif i < 110:
                price -= step * 0.5 + random.uniform(-0.0002, 0.0002)
            else:
                price += step * 0.25 + random.uniform(-0.0002, 0.0002)

        o = price + random.uniform(-0.0005, 0.0005)
        c = price
        h = max(o, c) + abs(random.gauss(0, 0.0004))
        l = min(o, c) - abs(random.gauss(0, 0.0004))

        candles.append({
            'time': f'2026-01-{i//24+1:02d}T{i%24:02d}:00',
            'open': round(o, 5),
            'high': round(h, 5),
            'low': round(l, 5),
            'close': round(c, 5),
            'volume': random.randint(100, 10000),
        })

    return candles


def build_scalp_data() -> list:
    """Build M5 data with a London session open, Judas Swing, then OTE pullback."""
    candles = []
    price = 1.0850
    # Pre-session noise
    for i in range(20):
        price += random.uniform(-0.0005, 0.0005)
        candles.append({'time': f'2026-01-15T0{i%12+1}:{i%6*10:02d}:00',
                        'open': round(price, 5), 'high': round(price + 0.001, 5),
                        'low': round(price - 0.001, 5), 'close': round(price, 5),
                        'volume': 1000})

    # Session open (2:00 EST = London)
    price += 0.003  # Judas up
    for i in range(5):
        candles.append({'time': f'2026-01-15T0{2+i//2}:{i%2*30:02d}:00',
                        'open': round(price, 5), 'high': round(price + 0.002, 5),
                        'low': round(price - 0.0005, 5), 'close': round(price + 0.001, 5),
                        'volume': 2000})
    # Reversal down
    for i in range(10):
        price -= 0.0008
        o = price + 0.0005
        h = max(o, price) + 0.0005
        l = min(o, price) - 0.0005 if i < 8 else min(o, price) + 0.0002  # pin bar at end
        candles.append({'time': f'2026-01-15T0{2+i//2}:{i%2*30+15:02d}:00',
                        'open': round(o, 5), 'high': round(h, 5),
                        'low': round(l, 5), 'close': round(price, 5),
                        'volume': 1500})

    return candles, time(2, 30)


from datetime import time


async def test_bot(name: str, bot, candles: list, config: dict, pairs: list = None):
    """Run one bot across all candles with a warmup period, count signals."""
    pairs = pairs or ['EURUSD']
    total = 0
    reasons = []
    for pair in pairs:
        for i in range(60, len(candles)):
            sig = await bot.analyze(pair, candles[:i + 1], config)
            if sig:
                total += 1
                if len(reasons) < 3:
                    reasons.append(sig.reason)
    return total, reasons


async def main():
    print("=" * 60)
    print("TradeAI Pro — Strategy Smoke Test")
    print("=" * 60)

    config = {'pip_size': 0.0001, 'lot_size': 0.01, 'stop_loss': 25, 'take_profit': 50}

    uptrend = build_trend_data(up=True)
    downtrend = build_trend_data(up=False)
    scalp_data, kz_time = build_scalp_data()

    tests = [
        ("Smart Money (uptrend)", SmartMoneyStrategy(swing_lookback=5, min_rr=3.0), uptrend),
        ("Smart Money (downtrend)", SmartMoneyStrategy(swing_lookback=5, min_rr=3.0), downtrend),
        ("Mirror (uptrend)", MirrorStrategy(swing_lookback=5, zone_tolerance=0.001, min_rr=2.0), uptrend),
        ("Classic (uptrend)", ClassicStrategy(swing_lookback=5, zone_width_pct=0.0015, min_touches=2, min_rr=2.0), uptrend),
        ("Scalp (KZ data)", ScalpStrategy(min_rr=1.5, max_trades_per_session=3), scalp_data),
    ]

    for name, bot, data in tests:
        total, reasons = await test_bot(name, bot, data, config)
        status = "OK" if total > 0 else "NO SIGNALS"
        print(f"\n  {name:35s} → {total:2d} signals  [{status}]")
        for r in reasons[:2]:
            print(f"    {r}")

    # Confluence is stricter — test with more data and all agreed directions
    conf = FullConfluenceStrategy(swing_lookback=5, min_rr=4.0, zone_tolerance=0.0015)
    conf_data = build_trend_data(up=True, length=200)

    # Manually adjust timestamps to be during London KZ
    for i, c in enumerate(conf_data):
        h = (2 + i % 3)  # 2, 3, 4 AM EST = London KZ
        c['time'] = f'2026-01-{i//24+1:02d}T{h:02d}:{i%60:02d}:00'

    total, reasons = await test_bot("Full Confluence (KZ + uptrend)", conf, conf_data, config)
    status = "OK" if total > 0 else "NO SIGNALS"
    print(f"\n  {'Full Confluence':35s} → {total:2d} signals  [{status}]")
    for r in reasons[:2]:
        print(f"    {r}")


asyncio.run(main())
