import unittest
import pandas as pd
from datetime import datetime
import sys
import os

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest import Backtester

class TestBacktesterMath(unittest.TestCase):
    def setUp(self):
        self.bt = Backtester('TEST', 'H1', datetime(2023, 1, 1), datetime(2023, 1, 2))

    def test_math_and_intrabar_priority(self):
        data = {
            'time': pd.date_range(start='2023-01-01', periods=10, freq='h'),
            'open': [100]*10,
            'high': [100]*10,
            'low': [100]*10,
            'close': [100]*10
        }
        df = pd.DataFrame(data)

        # Bar 1: BUY TP (High goes to 110, Low stays 100)
        df.loc[1, 'high'] = 110
        df.loc[1, 'low'] = 100

        # Bar 2: BUY SL and TP (High goes to 110, Low goes to 90) -> SL should hit first
        df.loc[2, 'high'] = 110
        df.loc[2, 'low'] = 90

        # Bar 3: SELL TP (Low goes to 90, High stays 100)
        df.loc[3, 'high'] = 100
        df.loc[3, 'low'] = 90

        # Bar 4: SELL SL and TP (High goes to 110, Low goes to 90) -> SL should hit first
        df.loc[4, 'high'] = 110
        df.loc[4, 'low'] = 90

        trade1 = self.bt.simulate_trade(df, 0, {'direction': 'BUY', 'entry': 100, 'stop_loss': 90, 'take_profit': 110}, lookahead=1)
        self.assertEqual(trade1['result'], 'win')
        self.assertAlmostEqual(trade1['rr_achieved'], 1.0)

        trade2 = self.bt.simulate_trade(df, 1, {'direction': 'BUY', 'entry': 100, 'stop_loss': 90, 'take_profit': 110}, lookahead=1)
        self.assertEqual(trade2['result'], 'loss')
        self.assertAlmostEqual(trade2['rr_achieved'], -1.0)

        trade3 = self.bt.simulate_trade(df, 2, {'direction': 'SELL', 'entry': 100, 'stop_loss': 110, 'take_profit': 90}, lookahead=1)
        self.assertEqual(trade3['result'], 'win')
        self.assertAlmostEqual(trade3['rr_achieved'], 1.0)

        trade4 = self.bt.simulate_trade(df, 3, {'direction': 'SELL', 'entry': 100, 'stop_loss': 110, 'take_profit': 90}, lookahead=1)
        self.assertEqual(trade4['result'], 'loss')
        self.assertAlmostEqual(trade4['rr_achieved'], -1.0)

        trades = [trade1, trade2, trade3, trade4]
        metrics = self.bt.compute_metrics(trades, 'TestBot')

        self.assertEqual(metrics['wins'], 2)
        self.assertEqual(metrics['losses'], 2)
        self.assertAlmostEqual(metrics['net_R'], 0.0)
        self.assertAlmostEqual(metrics['profit_factor'], 1.0)
        self.assertAlmostEqual(metrics['avg_rr'], 0.0)

        print("\nAll assertions passed. Math is mathematically sound and intrabar exit is conservative.")

if __name__ == '__main__':
    unittest.main()
