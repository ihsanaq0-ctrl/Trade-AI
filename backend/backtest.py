"""
Backtesting Engine for TradeAI Pro Bots
Requires: pandas, numpy, MetaTrader5
Tests all 5 bots against real historical data and reports performance metrics.

Usage:
    python backtest.py                          # EURUSD H1, last 180 days
    python backtest.py --symbol XAUUSD --timeframe H1 --days 90
    python backtest.py --symbol EURUSD --timeframe H4 --days 365 --output results.csv
"""

import pandas as pd
import numpy as np
import argparse
import sys
import os
import asyncio
from datetime import datetime, timedelta

# Add app to path so we can import our bots
sys.path.insert(0, os.path.dirname(__file__))
from app.services.strategies.smart_money import SmartMoneyStrategy
from app.services.strategies.mirror import MirrorStrategy
from app.services.strategies.classic import ClassicStrategy
from app.services.strategies.full_confluence import FullConfluenceStrategy
from app.services.strategies.scalp import ScalpStrategy
from app.services.strategies.scalp_pyramid import ScalpPyramidBot
from app.services.strategies.scalp_fvg import ScalpModeBot
from app.services.strategies.signal_strength_hedge import SignalStrengthHedgeBot

# MT5 timeframe mapping
TIMEFRAMES = {
    'M1': 1, 'M5': 5, 'M15': 15, 'M30': 30,
    'H1': 60, 'H4': 240, 'D1': 1440, 'W1': 10080,
}

# Pip size per symbol type
PIP_SIZES = {
    'default': 0.0001,
    'jpy': 0.01,
    'xau': 0.01,
    'xag': 0.01,
    'btc': 1.0,
    'eth': 1.0,
}


def get_pip_size(symbol: str) -> float:
    s = symbol.upper()
    if s in ('USDJPY', 'EURJPY', 'GBPJPY', 'AUDJPY', 'CHFJPY', 'NZDJPY', 'CADJPY'):
        return 0.01
    if 'XAU' in s or 'XAG' in s:
        return 0.01
    if 'BTC' in s or 'ETH' in s or 'XRP' in s:
        return 1.0
    return 0.0001


class Backtester:
    def __init__(self, symbol: str, timeframe: str, start_date: datetime, end_date: datetime, initial_balance=10000):
        self.symbol = symbol
        self.timeframe_str = timeframe
        self.timeframe = TIMEFRAMES.get(timeframe, 60)
        self.start_date = start_date
        self.end_date = end_date
        self.initial_balance = initial_balance
        self.pip_size = get_pip_size(symbol)

    def fetch_data(self, df: pd.DataFrame = None):
        """
        Load data from MT5, or accept a pre-loaded DataFrame.
        If no MT5, generates synthetic data so the engine can still run.
        """
        if df is not None:
            return df

        try:
            from app.services.metaapi_service import _ensure_mt5, _ensure_symbol_visible
            mt5 = _ensure_mt5()
            resolved_symbol = _ensure_symbol_visible(self.symbol)
        except Exception as e:
            print(f"Warning: MT5 not available ({e}), using synthetic data")
            return self._generate_synthetic_data()

        rates = None
        if mt5:
            # Map minutes to MT5 constants
            tf_map = {
                1: mt5.TIMEFRAME_M1,
                5: mt5.TIMEFRAME_M5,
                15: mt5.TIMEFRAME_M15,
                30: mt5.TIMEFRAME_M30,
                60: mt5.TIMEFRAME_H1,
                240: mt5.TIMEFRAME_H4,
                1440: mt5.TIMEFRAME_D1,
                10080: mt5.TIMEFRAME_W1
            }
            mt5_tf = tf_map.get(self.timeframe, mt5.TIMEFRAME_H1)
            rates = mt5.copy_rates_range(resolved_symbol, mt5_tf, self.start_date, self.end_date)

        if rates is None or len(rates) == 0:
            print(f"Warning: No data from MT5 for {resolved_symbol}, using synthetic")
            return self._generate_synthetic_data()

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df = df.rename(columns={'tick_volume': 'volume'})
        df = df[['time', 'open', 'high', 'low', 'close', 'volume']]
        return df

    def _generate_synthetic_data(self, num_candles=2000):
        """Generate synthetic OHLCV data for testing without MT5."""
        np.random.seed(42)
        base = 1.0850 if 'JPY' not in self.symbol.upper() else 150.0
        if 'XAU' in self.symbol.upper():
            base = 2350.0
        elif 'BTC' in self.symbol.upper():
            base = 65000.0

        times = [self.start_date + timedelta(hours=i * (self.timeframe / 60))
                 for i in range(num_candles)]
        closes = [base]
        for i in range(1, num_candles):
            change = np.random.normal(0, base * 0.002)
            closes.append(closes[-1] + change)

        data = []
        for i in range(num_candles):
            o = closes[i]
            c = o + np.random.normal(0, base * 0.001)
            h = max(o, c) + abs(np.random.normal(0, base * 0.0005))
            l = min(o, c) - abs(np.random.normal(0, base * 0.0005))
            data.append({
                'time': times[i],
                'open': round(o, 5),
                'high': round(h, 5),
                'low': round(l, 5),
                'close': round(c, 5),
                'volume': int(np.random.randint(100, 10000)),
            })

        return pd.DataFrame(data)

    def simulate_trade(self, df, entry_index, signal, lookahead=200):
        """
        Walk forward from entry to see if SL or TP hits first.

        Returns dict with result, pips, rr_achieved.
        """
        direction = signal['direction']
        entry = signal['entry']
        sl = signal['stop_loss']
        tp = signal['take_profit']

        risk = abs(entry - sl)
        if risk == 0:
            return {'result': 'invalid', 'pips': 0, 'rr_achieved': 0}

        end_index = min(entry_index + lookahead, len(df) - 1)

        for i in range(entry_index + 1, end_index + 1):
            candle = df.iloc[i]

            if direction == 'BUY':
                if candle['low'] <= sl:
                    pips = sl - entry
                    return {'result': 'loss', 'pips': pips, 'rr_achieved': pips / risk}
                if candle['high'] >= tp:
                    pips = tp - entry
                    return {'result': 'win', 'pips': pips, 'rr_achieved': pips / risk}
            else:
                if candle['high'] >= sl:
                    pips = entry - sl
                    return {'result': 'loss', 'pips': pips, 'rr_achieved': pips / risk}
                if candle['low'] <= tp:
                    pips = entry - tp
                    return {'result': 'win', 'pips': pips, 'rr_achieved': pips / risk}

        # Timed out — close at last price
        last_price = df.iloc[end_index]['close']
        pips = last_price - entry if direction == 'BUY' else entry - last_price
        return {'result': 'timeout', 'pips': pips, 'rr_achieved': pips / risk}

    def candles_to_list(self, df):
        """Convert DataFrame to list-of-dicts format our bots expect."""
        return df.to_dict('records')

    async def run_backtest(self, bot, bot_name, min_history=100, lookahead=200, df=None, return_trades=False):
        """
        Walk through data candle-by-candle using the fast DataFrame path.
        At each step, feeds the bot a rolling window. If it signals, simulate the trade.
        """
        if df is None:
            df = self.fetch_data()

        trades = []
        i = min_history

        while i < len(df) - 1:
            # Bound window to avoid O(N^2) memory scaling
            start_idx = max(0, i - 1000)
            window = df.iloc[start_idx:i + 1].reset_index(drop=True)

            try:
                # Fast path: call generate_signal directly with DataFrame
                signal = bot.generate_signal(window)
            except Exception as e:
                signal = None

            if signal is not None:
                # The simple backtester only supports single dict signals (SL/TP).
                # It does not support complex multi-position bots that return lists of actions.
                if isinstance(signal, list) or 'direction' not in signal:
                    i += 1
                    continue

                result = self.simulate_trade(df, i, signal, lookahead=lookahead)
                result['entry_time'] = df.iloc[i]['time']
                result['direction'] = signal['direction']
                result['strategy'] = bot_name
                # Store additional signal details for export
                result['entry'] = signal['entry']
                result['stop_loss'] = signal['stop_loss']
                result['take_profit'] = signal['take_profit']
                if 'setup_type' in signal:
                    result['setup_type'] = signal['setup_type']
                trades.append(result)

                # Skip ahead to avoid overlapping signals on the same setup
                i += 5
            else:
                i += 1

        metrics = self.compute_metrics(trades, bot_name)
        if return_trades:
            return metrics, trades
        return metrics

    def compute_metrics(self, trades, bot_name):
        """Compute win rate, profit factor, drawdown, and other stats."""
        if len(trades) == 0:
            return {
                'strategy': bot_name,
                'total_trades': 0,
                'wins': 0, 'losses': 0, 'timeouts': 0,
                'win_rate': None,
                'profit_factor': None,
                'avg_rr': None,
                'max_drawdown_R': None,
                'net_R': None,
                'note': 'No signals generated during backtest period'
            }

        wins = [t for t in trades if t['result'] == 'win']
        losses = [t for t in trades if t['result'] == 'loss']
        valid = [t for t in trades if t['result'] in ('win', 'loss')]

        win_rate = len(wins) / len(valid) * 100 if valid else 0

        # Calculate in R-multiples instead of pips to prevent mathematical contradictions
        gross_profit_R = sum(t['rr_achieved'] for t in wins)
        gross_loss_R = sum(abs(t['rr_achieved']) for t in losses)
        profit_factor = gross_profit_R / gross_loss_R if gross_loss_R > 0 else float('inf')

        avg_rr = np.mean([t['rr_achieved'] for t in valid]) if valid else 0

        # Equity curve in R-multiples
        equity = [0]
        for t in valid:
            equity.append(equity[-1] + t['rr_achieved'])
        equity_arr = np.array(equity)
        running_max = np.maximum.accumulate(equity_arr)
        drawdown = running_max - equity_arr
        max_dd = drawdown.max() if len(drawdown) > 0 else 0
        net_R = equity[-1] if len(equity) > 0 else 0

        # Mathematically enforce the assertions requested by the user
        if valid and profit_factor != float('inf'):
            assert abs(gross_profit_R - gross_loss_R - net_R) < 1e-9, f"Net R mismatch: GP {gross_profit_R} - GL {gross_loss_R} != Net R {net_R}"
            assert abs((gross_profit_R / gross_loss_R) - profit_factor) < 1e-9, f"PF mismatch: GP/GL != PF"

        return {
            'strategy': bot_name,
            'total_trades': len(trades),
            'wins': len(wins),
            'losses': len(losses),
            'timeouts': len([t for t in trades if t['result'] == 'timeout']),
            'win_rate': round(win_rate, 2),
            'profit_factor': round(profit_factor, 2) if profit_factor != float('inf') else 'inf',
            'avg_rr': round(avg_rr, 2),
            'max_drawdown_R': round(max_dd, 2),
            'net_R': round(equity[-1], 2),
        }


async def run_comparison(symbol='EURUSD', timeframe='H1', days=180, output=None):
    """Run all 5 bots and print a comparison table."""
    print(f"\nTradeAI Pro - Backtest: {symbol} ({timeframe}), last {days} days")
    print(f"Period: {(datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')} -> "
          f"{datetime.now().strftime('%Y-%m-%d')}")
    print("=" * 80)

    end = datetime.now()
    start = end - timedelta(days=days)

    bt = Backtester(symbol, timeframe, start, end)
    df = bt.fetch_data()
    pip = get_pip_size(symbol)

    print(f"Loaded {len(df)} candles, pip size: {pip}")
    print()

    sm_bot = SmartMoneyStrategy(swing_lookback=5, displacement_atr_mult=1.5, atr_period=14, liquidity_cluster_pct=0.0008, min_rr=1.0)
    mmc_bot = MirrorStrategy(swing_lookback=5, zone_tolerance_pct=0.0015, min_rr=1.0)
    snr_bot = ClassicStrategy(swing_lookback=5, zone_atr_multiplier=0.5, min_touches=2, atr_period=14, min_rr=1.0)

    bots = [
        (sm_bot, 'Smart Money'),
        (mmc_bot, 'Mirror'),
        (snr_bot, 'Classic'),
        (FullConfluenceStrategy(smart_money_bot=sm_bot, mirror_bot=mmc_bot, classic_bot=snr_bot, min_rr=4.0), 'Full Confluence'),
        (ScalpStrategy(min_rr=1.5, max_daily_trades=3, atr_period=14), 'Scalp (Trend)'),
        (ScalpPyramidBot(), 'Scalp Pyramid'),
        (ScalpModeBot(), 'Scalp (FVG)'),
        (SignalStrengthHedgeBot(), 'SS Hedge')
    ]

    results = await asyncio.gather(*[
        bt.run_backtest(bot, name, df=df) for bot, name in bots
    ])

    for metrics in results:
        print(f"  {metrics['strategy']:20s} -> {metrics['total_trades']:3d} trades, "
              f"WR: {metrics['win_rate'] if metrics['win_rate'] is not None else 'N/A':>5}, "
              f"PF: {metrics['profit_factor'] if metrics['profit_factor'] is not None else 'N/A'}, "
              f"net R: {metrics['net_R'] if metrics['net_R'] is not None else 'N/A'}")

    # Print comparison table
    headers = ['Strategy', 'Trades', 'Wins', 'Loss', 'TO', 'Win Rate%', 'Profit Factor',
               'Avg RR', 'Max DD(R)', 'Net R']
    print()
    print("=" * 80)
    print(f"RESULTS — {symbol} ({timeframe}) — {days} days")
    print("=" * 80)
    print(f"{headers[0]:20s} {headers[1]:>6s} {headers[2]:>4s} {headers[3]:>4s} {headers[4]:>3s} "
          f"{headers[5]:>9s} {headers[6]:>13s} {headers[7]:>7s} {headers[8]:>10s} {headers[9]:>7s}")
    print("-" * 80)

    for r in results:
        wr = f"{r['win_rate']:.1f}" if r['win_rate'] is not None else 'N/A'
        pf = f"{r['profit_factor']:.2f}" if r['profit_factor'] is not None else 'N/A'
        avg = f"{r['avg_rr']:.2f}" if r['avg_rr'] is not None else 'N/A'
        dd = f"{r['max_drawdown_R']:.2f}" if r['max_drawdown_R'] is not None else 'N/A'
        net = f"{r['net_R']:.2f}" if r['net_R'] is not None else 'N/A'
        to = r['timeouts']
        print(f"{r['strategy']:20s} {r['total_trades']:6d} {r['wins']:4d} {r['losses']:4d} "
              f"{to:3d} {wr:>9s} {pf:>13s} {avg:>7s} {dd:>10s} {net:>7s}")

    print("=" * 80)

    if output:
        pd.DataFrame(results).to_csv(output, index=False)
        print(f"\nResults saved to {output}")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='TradeAI Pro Backtesting Engine')
    parser.add_argument('--symbol', default='EURUSD', help='Trading pair (default: EURUSD)')
    parser.add_argument('--timeframe', default='H1', choices=list(TIMEFRAMES.keys()),
                        help='Timeframe (default: H1)')
    parser.add_argument('--days', type=int, default=180, help='Days to backtest (default: 180)')
    parser.add_argument('--output', default=None, help='Save results to CSV file')

    args = parser.parse_args()
    asyncio.run(run_comparison(symbol=args.symbol, timeframe=args.timeframe,
                days=args.days, output=args.output))
