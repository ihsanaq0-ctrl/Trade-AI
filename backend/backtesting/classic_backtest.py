import argparse
import sys
import os
import asyncio
from datetime import datetime, timedelta

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest import Backtester, get_pip_size, TIMEFRAMES
from app.services.strategies.classic import ClassicStrategy

async def run(symbol, timeframe, days):
    print(f"\nTradeAI Pro - Isolated Backtest: Classic | {symbol} ({timeframe}), last {days} days")
    print("=" * 80)

    end = datetime.now()
    start = end - timedelta(days=days)

    bt = Backtester(symbol, timeframe, start, end)
    df = bt.fetch_data()
    pip = get_pip_size(symbol)

    print(f"Loaded {len(df)} candles, pip size: {pip}\n")

    bot = ClassicStrategy(swing_lookback=5, zone_atr_multiplier=0.5, min_touches=2, atr_period=14, min_rr=1.0)

    results = await asyncio.gather(*[bt.run_backtest(bot, 'Classic', df=df)])
    metrics = results[0]

    wr = f"{metrics['win_rate']:.1f}" if metrics['win_rate'] is not None else 'N/A'
    pf = f"{metrics['profit_factor']:.2f}" if metrics['profit_factor'] is not None else 'N/A'
    net = f"{metrics['net_R']:.2f}" if metrics['net_R'] is not None else 'N/A'
    
    print(f"  {metrics['strategy']:20s} -> {metrics['total_trades']:3d} trades, "
          f"WR: {wr:>5}, PF: {pf}, net R: {net}\n")

    print("=" * 80)
    print(f"RESULTS - {symbol} ({timeframe}) - {days} days")
    print("=" * 80)
    headers = ['Strategy', 'Trades', 'Wins', 'Loss', 'TO', 'Win Rate%', 'Profit Factor', 'Avg RR', 'Max DD(R)', 'Net R']
    print(f"{headers[0]:20s} {headers[1]:>6s} {headers[2]:>4s} {headers[3]:>4s} {headers[4]:>3s} "
          f"{headers[5]:>9s} {headers[6]:>13s} {headers[7]:>7s} {headers[8]:>10s} {headers[9]:>7s}")
    print("-" * 80)
    
    r = metrics
    wr = f"{r['win_rate']:.1f}" if r['win_rate'] is not None else 'N/A'
    pf = f"{r['profit_factor']:.2f}" if r['profit_factor'] is not None else 'N/A'
    avg = f"{r['avg_rr']:.2f}" if r['avg_rr'] is not None else 'N/A'
    dd = f"{r['max_drawdown_R']:.2f}" if r['max_drawdown_R'] is not None else 'N/A'
    net = f"{r['net_R']:.2f}" if r['net_R'] is not None else 'N/A'
    to = r['timeouts']
    print(f"{r['strategy']:20s} {r['total_trades']:6d} {r['wins']:4d} {r['losses']:4d} "
          f"{to:3d} {wr:>9s} {pf:>13s} {avg:>7s} {dd:>10s} {net:>7s}")
    print("=" * 80)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Isolated Backtester')
    parser.add_argument('--symbol', default='EURUSD')
    parser.add_argument('--timeframe', default='H1', choices=list(TIMEFRAMES.keys()))
    parser.add_argument('--days', type=int, default=180)
    args = parser.parse_args()
    asyncio.run(run(args.symbol, args.timeframe, args.days))
