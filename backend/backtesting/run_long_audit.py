import asyncio
import pandas as pd
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest import Backtester
from app.services.strategies.smart_money import SmartMoneyStrategy
from app.services.strategies.mirror import MirrorStrategy

async def run_and_export():
    # We will test on 180 days (6 months)
    days = 180
    end = datetime.now()
    start = end - timedelta(days=days)
    
    symbols = ['XAUUSD']
    
    for symbol in symbols:
        print(f"\nRunning tests on {symbol} M5 for {days} days...", flush=True)
        bt = Backtester(symbol, 'M5', start, end)
        try:
            df = bt.fetch_data()
        except Exception as e:
            print(f"Failed to fetch data for {symbol}: {e}", flush=True)
            continue
            
        print(f"Fetched {len(df)} candles.", flush=True)

        # MMC
        mmc_bot = MirrorStrategy(
            swing_lookback=8,
            eq_tp_extension=0.2,
            min_rr=1.0,
            trend_ema_period=200,
            spread_pct=0.0001,
            drop_forming_bar=False
        )
        
        # SMC
        smc_bot = SmartMoneyStrategy(
            swing_lookback=5,
            displacement_atr_mult=1.5,
            atr_period=14,
            liquidity_cluster_pct=0.0008,
            min_rr=1.0,
            drop_forming_bar=False
        )
        
        print("Testing SMC...", flush=True)
        smc_metrics, smc_trades = await bt.run_backtest(smc_bot, 'SMC', df=df, return_trades=True)
        print("SMC Metrics:", smc_metrics, flush=True)
        if smc_trades:
            smc_df = pd.DataFrame(smc_trades)
            smc_df.to_csv(f"smc_{symbol}_M5_trades.csv", index=False)
            print(f"Exported SMC trades to smc_{symbol}_M5_trades.csv", flush=True)
        
        print("Testing MMC...", flush=True)
        mmc_metrics, mmc_trades = await bt.run_backtest(mmc_bot, 'MMC', df=df, return_trades=True)
        print("MMC Metrics:", mmc_metrics, flush=True)
        if mmc_trades:
            mmc_df = pd.DataFrame(mmc_trades)
            mmc_df.to_csv(f"mmc_{symbol}_M5_trades.csv", index=False)
            print(f"Exported MMC trades to mmc_{symbol}_M5_trades.csv", flush=True)

if __name__ == '__main__':
    asyncio.run(run_and_export())
