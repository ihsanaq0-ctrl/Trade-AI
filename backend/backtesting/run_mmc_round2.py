"""
run_mmc_round2.py — Track-A round 2: corrected composite after the round-1 audit.

Round-1 verdicts applied:
  A1 'edge' rejection  -> REJECTED (removed +5.41R of winners)
  A2 confirmation bar  -> REJECTED (removed +3.16R of winners, n collapsed to 9)
  A6 mirror OFF         -> KEPT
  A3 zone block/cooldown-> KEPT
  A5 @ 2.0x median      -> never binds; retested at 1.5x on TRAIN only (C2)

C1 is pre-declared PRIMARY. Validation runs on C1 exactly once.
C2/C3 are train-only diagnostics. No config is ever selected based on
validation output.
"""

import argparse
import asyncio
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

from backtest import Backtester, get_pip_size, TIMEFRAMES
from app.services.strategies.mirror import MirrorStrategy

DEFAULT_COSTS = {"XAUUSD": 0.35, "XAGUSD": 0.04}
BASE = dict(
    swing_lookback=8,
    eq_tp_extension=0.2,
    min_rr=1.0,
    trend_ema_period=200,
    spread_pct=0.0,
    drop_forming_bar=False,
)

C1_PRIMARY = dict(
    BASE,
    rejection_mode="inner",          # round-1 audit: 'edge' removed winners
    enable_mirror_setup=False,        # A6 kept
    zone_reentry_block_bars=240,
    zone_reentry_atr_mult=0.5,
    post_signal_cooldown_bars=6,
    confirm_next_close=False,        # A2 rejected by audit
), 60                                 # loss cooldown bars

C2_ATR = dict(
    BASE,
    rejection_mode="inner",
    enable_mirror_setup=False,
    zone_reentry_block_bars=240,
    zone_reentry_atr_mult=0.5,
    post_signal_cooldown_bars=6,
    atr_max_median_mult=1.5,         # binds where 2.0 never did
), 60

C3_MID = dict(
    BASE,
    rejection_mode="mid",             # middle ground between inner and edge
    enable_mirror_setup=False,
    zone_reentry_block_bars=240,
    zone_reentry_atr_mult=0.5,
    post_signal_cooldown_bars=6,
), 60


def cost_for(symbol, override):
    if override is not None:
        return override
    return DEFAULT_COSTS.get(symbol.upper(), 0.00015)


def infer_bar_seconds(df):
    s = pd.to_datetime(pd.Series(df["time"].values[-200:]))
    d = s.diff().dt.total_seconds().dropna()
    d = d[d > 0]
    return float(d.median()) if len(d) else 300.0


def simulate(df, entry_index, signal, cost, lookahead=200):
    direction, entry = signal["direction"], signal["entry"]
    sl, tp = signal["stop_loss"], signal["take_profit"]
    risk = abs(entry - sl)
    if risk <= 0:
        return "invalid", 0.0, entry_index
    end = min(entry_index + lookahead, len(df) - 1)
    for j in range(entry_index + 1, end + 1):
        row = df.iloc[j]
        if direction == "BUY":
            if row["low"] <= sl:
                return "loss", -(risk + cost) / risk, j
            if row["high"] >= tp:
                return "win", (tp - entry - cost) / risk, j
        else:
            if row["high"] >= sl:
                return "loss", -(risk + cost) / risk, j
            if row["low"] <= tp:
                return "win", (entry - tp - cost) / risk, j
    px = df.iloc[end]["close"]
    pnl = (px - entry) if direction == "BUY" else (entry - px)
    return "timeout", (pnl - cost) / risk, end


def run_config(df, params, loss_cooldown_bars, bar_sec, cost, window_bars=1000):
    params, cooldown_bars = params
    bot = MirrorStrategy(**params)
    trades = []
    i = max(100, bot.min_bars_required + 2)
    while i < len(df) - 1:
        window = df.iloc[max(0, i - window_bars):i + 1].reset_index(drop=True)
        try:
            sig = bot.generate_signal(window)
        except Exception:
            sig = None
        if sig is None:
            i += 1
            continue
        result, rr, exit_j = simulate(df, i, sig, cost)
        exit_time = df.iloc[exit_j]["time"]
        if result == "loss" and cooldown_bars > 0:
            bot.on_trade_result(result, exit_time,
                                cooldown_seconds=cooldown_bars * bar_sec)
        trades.append({
            "entry_time": pd.Timestamp(df.iloc[i]["time"]),
            "exit_time": pd.Timestamp(exit_time),
            "setup_type": sig.get("setup_type", "n/a"),
            "direction": sig["direction"],
            "result": result,
            "rr": rr,
            "risk": sig.get("risk", np.nan),
            "atr": sig.get("atr", np.nan),
        })
        i = exit_j + 1
    return trades


def metrics(trades):
    if not trades:
        return {"trades": 0, "wr": None, "pf": None, "net": 0.0, "dd": 0.0,
                "avg_win": None, "expectancy": None}
    wins = [t for t in trades if t["result"] == "win"]
    losses = [t for t in trades if t["result"] == "loss"]
    valid = wins + losses
    gp = sum(t["rr"] for t in wins)
    gl = sum(-t["rr"] for t in losses)
    eq = [0.0]
    for t in sorted(trades, key=lambda x: x["entry_time"]):
        eq.append(eq[-1] + t["rr"])
    eqa = np.array(eq)
    dd = float((np.maximum.accumulate(eqa) - eqa).max()) if len(eqa) else 0.0
    return {
        "trades": len(trades),
        "wr": (len(wins) / len(valid) * 100) if valid else None,
        "pf": (gp / gl) if gl > 0 else float("inf"),
        "net": eq[-1], "dd": dd,
        "avg_win": (gp / len(wins)) if wins else None,
        "expectancy": eq[-1] / len(trades),
    }


def fmt(m):
    wr = f"{m['wr']:.1f}" if m["wr"] is not None else "  —"
    pf = f"{m['pf']:.2f}" if m["pf"] not in (None, float("inf")) else "  —"
    aw = f"{m['avg_win']:.2f}" if m["avg_win"] is not None else " —"
    ex = f"{m['expectancy']:+.3f}" if m["expectancy"] is not None else " —"
    return (f"trades {m['trades']:3d} | WR {wr:>5}% | PF {pf:>5} | avgWin {aw:>4}R | "
            f"net {m['net']:+7.2f}R | maxDD {m['dd']:5.2f}R | E/trade {ex}R")


def breakdown(trades, keyfn, title):
    groups = defaultdict(list)
    for t in trades:
        groups[keyfn(t)].append(t)
    print(f"\n  --- {title} ---")
    print(f"  {'key':>10} | {'n':>3} | {'WR%':>6} | {'net R':>8}")
    for k in sorted(groups, key=lambda x: str(x)):
        m = metrics(groups[k])
        wr = f"{m['wr']:.1f}" if m["wr"] is not None else "—"
        print(f"  {str(k):>10} | {m['trades']:3d} | {wr:>6} | {m['net']:+8.2f}")


async def main(symbol, timeframe, days, cost_override):
    print(f"MMC Track-A ROUND 2 (corrected composite) | {symbol} {timeframe} | last {days} days")
    print("=" * 96)

    end = datetime.now()
    start = end - timedelta(days=days)
    bt = Backtester(symbol, timeframe, start, end)
    df = bt.fetch_data()
    print(f"Loaded {len(df)} candles | cost/trade {cost_for(symbol, cost_override)} price units")
    if len(df) < 20000:
        print("WARNING: low candle count — check this is real MT5 data, not synthetic.")
    if len(df) < 6000:
        print("ABORT: this looks like the synthetic fallback. Fix MT5 and re-run.")
        return

    bar_sec = infer_bar_seconds(df)
    split_ts = pd.Timestamp(df["time"].iloc[int(len(df) * 2 / 3)])
    cost = cost_for(symbol, cost_override)
    print(f"Bar size {bar_sec:.0f}s | train < {split_ts} <= validation")

    def is_train(t):
        return t["entry_time"] < split_ts

    configs = [
        ("C1 (PRIMARY - inner + A6 + A3)", C1_PRIMARY),
        ("C2 (train-only diag - C1 + ATR<1.5x median)", C2_ATR),
        ("C3 (train-only diag - C1 with 'mid' rejection)", C3_MID),
    ]

    print("\n" + "=" * 96)
    print("TRAIN RESULTS (all three configs)")
    print("=" * 96)
    c1_trades = None
    for name, cfg in configs:
        trades = run_config(df, cfg, 0, bar_sec, cost)
        train = [t for t in trades if is_train(t)]
        print(f"\n{name}\n    TRAIN {fmt(metrics(train))}")
        if c1_trades is None:
            c1_trades = trades

    print("\n" + "=" * 96)
    print("VALIDATION - C1 PRIMARY, run once, this is the final look")
    print("=" * 96)
    f_train = [t for t in c1_trades if is_train(t)]
    f_val = [t for t in c1_trades if not is_train(t)]
    print(f"\n  C1 TRAIN      : {fmt(metrics(f_train))}")
    print(f"  C1 VALIDATION : {fmt(metrics(f_val))}")

    breakdown(c1_trades, lambda t: t["setup_type"], "C1 per setup")
    breakdown(c1_trades, lambda t: t["entry_time"].to_period("M"), "C1 per month")
    breakdown(c1_trades, lambda t: t["direction"], "C1 per direction (regime check - do NOT turn into a filter)")

    print("\n" + "=" * 96)
    print("TARGET CHECK (WR >= 53% AND expectancy >= +0.08R after costs)")
    print("=" * 96)
    for label, subset in (("C1 TRAIN", f_train), ("C1 VALIDATION", f_val)):
        m = metrics(subset)
        if m["wr"] is None or not subset:
            print(f"  {label:15}: no valid trades")
            continue
        ok_wr = m["wr"] >= 53.0
        ok_ex = m["expectancy"] is not None and m["expectancy"] >= 0.08
        print(f"  {label:15}: WR {m['wr']:.1f}% [{'PASS' if ok_wr else 'fail'}] | "
              f"expectancy {m['expectancy']:+.3f}R [{'PASS' if ok_ex else 'fail'}]")

    if len(f_val) < 30:
        print(f"\n  NOTE: validation n={len(f_val)} < 30 — treat the WR point "
              f"estimate as indicative only. Extending data (more days or a "
              f"second symbol) is the fix, not re-running.")

    pd.DataFrame(c1_trades).to_csv("mmc_round2_trades.csv", index=False)
    print("\nC1 trade list saved to mmc_round2_trades.csv")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="MMC Track-A round 2")
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--timeframe", default="M5", choices=list(TIMEFRAMES.keys()))
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--cost", type=float, default=None)
    args = p.parse_args()
    asyncio.run(main(args.symbol, args.timeframe, args.days, args.cost))