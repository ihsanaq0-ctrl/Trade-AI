"""
TradeAI Pro — Multi-Symbol Multi-Timeframe Backtest Runner
Runs all 5 bots across symbol×timeframe combinations and ranks results.
Outputs a CSV + ranked table so you can see which bot/pair/TF works best.

Usage:
    python multi_backtest.py                              # default run
    python multi_backtest.py --days 365                   # longer period
    python multi_backtest.py --symbols EURUSD,GBPUSD     # specific pairs
    python multi_backtest.py --timeframes H1,H4,D1        # specific TFs
    python multi_backtest.py --output results.csv         # save to file
    python multi_backtest.py --min-trades 10              # filter low-signal bots
"""

import sys, os, asyncio, argparse, csv
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(__file__))

from backtest import Backtester
from app.services.strategies.smart_money import SmartMoneyStrategy
from app.services.strategies.mirror import MirrorStrategy
from app.services.strategies.classic import ClassicStrategy
from app.services.strategies.full_confluence import FullConfluenceStrategy
from app.services.strategies.scalp import ScalpStrategy

ALL_SYMBOLS = ['EURUSD', 'GBPUSD', 'XAUUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'GBPJPY', 'EURJPY', 'NZDUSD']
ALL_TIMEFRAMES = ['H1', 'H4', 'D1']

BOTS = [
    (lambda: SmartMoneyStrategy(swing_lookback=5, displacement_multiplier=1.5, atr_period=14, liquidity_cluster_pct=0.0008, min_rr=3.0), 'Smart Money'),
    (lambda: MirrorStrategy(swing_lookback=5, zone_tolerance_pct=0.0015, min_rr=2.0), 'Mirror'),
    (lambda: ClassicStrategy(swing_lookback=5, zone_atr_multiplier=0.5, min_touches=2, atr_period=14, min_rr=2.0), 'Classic'),
    (lambda: FullConfluenceStrategy(
    SmartMoneyStrategy(swing_lookback=5, displacement_multiplier=1.5, atr_period=14, liquidity_cluster_pct=0.0008, min_rr=1.0),
    MirrorStrategy(swing_lookback=5, zone_tolerance_pct=0.0015, min_rr=1.0),
    ClassicStrategy(swing_lookback=5, zone_atr_multiplier=0.5, min_touches=2, atr_period=14, min_rr=1.0),
    min_rr=4.0
), 'Full Confluence'),
    (lambda: ScalpStrategy(session_lookback=12, min_rr=1.5, max_daily_trades=3, atr_period=14), 'Scalp'),
]


async def run_one(bot_fn, bot_name, symbol, timeframe, days, min_history, lookahead):
    """Run one bot/symbol/timeframe combination."""
    end = datetime.now()
    start = end - timedelta(days=days)

    try:
        bt = Backtester(symbol, timeframe, start, end)
        df = bt.fetch_data()
        if len(df) < min_history + 10:
            return None

        bot = bot_fn()
        metrics = await bt.run_backtest(bot, bot_name, min_history=min_history,
                                        lookahead=lookahead, df=df)
        metrics['symbol'] = symbol
        metrics['timeframe'] = timeframe
        return metrics
    except Exception as e:
        return {'strategy': bot_name, 'symbol': symbol, 'timeframe': timeframe,
                'total_trades': 0, 'wins': 0, 'losses': 0, 'timeouts': 0,
                'win_rate': None, 'profit_factor': None, 'avg_rr': None,
                'max_drawdown_R': None, 'net_R': None, 'error': str(e)}


def score(metrics):
    """Score a result for ranking. Higher is better."""
    if metrics['total_trades'] == 0 or metrics.get('error'):
        return -999
    wr = metrics['win_rate'] or 0
    pf = metrics['profit_factor'] if isinstance(metrics['profit_factor'], (int, float)) else 0
    net = metrics['net_R'] or 0
    trades = metrics['total_trades']
    dd = metrics['max_drawdown_R'] or 1
    # Composite: profit factor × net R × log(trades) / (drawdown + 1)
    # If net is negative, score is negative
    if net <= 0:
        return net * pf * 0.1
    return pf * net * (trades ** 0.3) / (dd + 1)


async def main():
    parser = argparse.ArgumentParser(description='TradeAI Pro — Multi-Symbol Multi-Timeframe Backtest')
    parser.add_argument('--symbols', default=','.join(ALL_SYMBOLS), help='Comma-separated symbols')
    parser.add_argument('--timeframes', default=','.join(ALL_TIMEFRAMES), help='Comma-separated timeframes')
    parser.add_argument('--days', type=int, default=180, help='Days of history')
    parser.add_argument('--min-trades', type=int, default=5, help='Minimum trades for ranking')
    parser.add_argument('--output', default='multi_backtest_results.csv', help='Output CSV')
    parser.add_argument('--lookahead', type=int, default=200, help='Max candles to simulate a trade')
    parser.add_argument('--top', type=int, default=20, help='Show top N results')
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(',') if s.strip()]
    timeframes = [t.strip() for t in args.timeframes.split(',') if t.strip()]

    total = len(symbols) * len(timeframes) * len(BOTS)
    print(f"\nTradeAI Pro — Multi-Backtest")
    print(f"{len(symbols)} symbols × {len(timeframes)} TFs × {len(BOTS)} bots = {total} runs")
    print(f"Period: last {args.days} days")
    print("=" * 70)

    results = []
    done = 0

    for symbol in symbols:
        for tf in timeframes:
            for bot_fn, bot_name in BOTS:
                done += 1
                print(f"  [{done}/{total}] {bot_name:18s} {symbol:7s} {tf:2s} ...", end=' ')
                sys.stdout.flush()

                metrics = await run_one(bot_fn, bot_name, symbol, tf, args.days, 100, args.lookahead)

                if metrics and metrics.get('total_trades', 0) > 0:
                    wr = f"{metrics['win_rate']:.1f}%" if metrics['win_rate'] else 'N/A'
                    pf = f"{metrics['profit_factor']}" if metrics.get('profit_factor') else 'N/A'
                    net = f"{metrics['net_R']:.1f}" if metrics.get('net_R') else 'N/A'
                    print(f"{metrics['total_trades']} trades, WR {wr}, PF {pf}, netR {net}")
                elif metrics and metrics.get('error'):
                    print(f"ERROR: {metrics['error'][:40]}")
                else:
                    print("0 trades (skipped)")

                if metrics is not None:
                    metrics['score'] = round(score(metrics), 2)
                    results.append(metrics)

    # Sort by score descending
    results.sort(key=lambda r: score(r), reverse=True)

    # Print ranked table
    print()
    print("=" * 100)
    print(f"RANKINGS  (min {args.min_trades} trades)")
    print("=" * 100)
    header = f"{'Rank':>4s}  {'Bot':20s} {'Symbol':7s} {'TF':3s}  {'Trades':>6s} {'Wins':>5s} {'Loss':>5s} {'WR%':>6s} {'PF':>7s} {'AvgRR':>6s} {'MaxDD':>7s} {'NetR':>7s}  {'Score':>6s}"
    print(header)
    print("-" * 100)

    rank = 0
    filtered = []
    for r in results:
        if r['total_trades'] >= args.min_trades:
            rank += 1
            filtered.append(r)
            if rank <= args.top:
                wr = f"{r['win_rate']:.1f}" if r['win_rate'] is not None else 'N/A'
                pf = f"{r['profit_factor']}" if isinstance(r.get('profit_factor'), (int, float)) else 'N/A'
                arr = f"{r['avg_rr']:.2f}" if r['avg_rr'] is not None else 'N/A'
                dd = f"{r['max_drawdown_R']:.1f}" if r['max_drawdown_R'] is not None else 'N/A'
                net = f"{r['net_R']:.1f}" if r['net_R'] is not None else 'N/A'
                print(f"{rank:4d}  {r['strategy']:20s} {r['symbol']:7s} {r['timeframe']:3s}  "
                      f"{r['total_trades']:6d} {r['wins']:5d} {r['losses']:5d} "
                      f"{wr:>6s} {pf:>7s} {arr:>6s} {dd:>7s} {net:>7s}  {r['score']:6.1f}")

    print("=" * 100)

    # Summary
    print(f"\nSummary: {len(results)} total runs, {len(filtered)} with >= {args.min_trades} trades")
    if filtered:
        best = filtered[0]
        worst = filtered[-1]
        print(f"Best:  {best['strategy']} on {best['symbol']} ({best['timeframe']}) — "
              f"{best['total_trades']} trades, WR {best['win_rate']:.1f}%, PF {best.get('profit_factor','N/A')}")
        print(f"Worst: {worst['strategy']} on {worst['symbol']} ({worst['timeframe']}) — "
              f"{worst['total_trades']} trades, NetR {worst['net_R']}")
        print(f"Median win rate across ranked: "
              f"{sum(r['win_rate'] or 0 for r in filtered) / len(filtered):.1f}%")

    # Save CSV
    if args.output:
        # Pick relevant columns, filter invalid
        clean = []
        for r in results:
            clean.append({
                'strategy': r['strategy'],
                'symbol': r['symbol'],
                'timeframe': r['timeframe'],
                'trades': r['total_trades'],
                'wins': r['wins'],
                'losses': r['losses'],
                'timeouts': r['timeouts'],
                'win_rate': round(r['win_rate'], 2) if r['win_rate'] else '',
                'profit_factor': r['profit_factor'] if isinstance(r.get('profit_factor'), (int, float)) else '',
                'avg_rr': round(r['avg_rr'], 2) if r['avg_rr'] else '',
                'max_drawdown_R': round(r['max_drawdown_R'], 2) if r['max_drawdown_R'] else '',
                'net_R': round(r['net_R'], 2) if r['net_R'] else '',
                'score': r.get('score', ''),
            })
        with open(args.output, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=clean[0].keys())
            writer.writeheader()
            writer.writerows(clean)
        print(f"Full results saved to {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
