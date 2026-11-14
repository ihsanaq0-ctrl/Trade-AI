"""
run_mmc_tuning.py — Track-A protocol runner for the MMC strategy.

Protocol (as agreed):
  1. Split by entry time: first ~2/3 train, last ~1/3 validation.
  2. Costs applied to EVERY trade from the first run (XAUUSD round trip
     in price units; default 0.35). spread_pct=0.0 in the strategy so
     costs live in exactly one place.
  3. Single position at a time: the loop advances to the trade's EXIT bar.
  4. Loss cooldown fed back to the strategy via on_trade_result().
  5. Attribution ladder on TRAIN: each filter reports how many trades it
     removed and what those removed trades were worth (kill-count audit —
     a filter that removes winners gets exposed immediately).
  6. Validation runs ONCE with the final preset. Do not iterate on it.

Usage:
    python run_mmc_tuning.py --symbol XAUUSD --timeframe M5 --days 180
    python run_mmc_tuning.py --symbol XAUUSD --timeframe M5 --days 180 --cost 0.35
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

# Round-trip cost in PRICE UNITS (spread + slippage). XAUUSD: ~0.20 spread
# + ~0.15 slippage on M5. For FX majors use ~0.00012 (1.2 pips).
DEFAULT_COSTS = {"XAUUSD": 0.35, "XAGUSD": 0.04}


def cost_for(symbol: str, override: float) -> float:
    if override is not None:
        return override
    s = symbol.upper()
    return DEFAULT_COSTS.get(s, 0.00015)


def infer_bar_seconds(df: pd.DataFrame) -> float:
    s = pd.to_datetime(pd.Series(df["time"].values[-200:]))
    d = s.diff().dt.total_seconds().dropna()
    d = d[d > 0]
    return float(d.median()) if len(d) else 300.0


# --------------------------------------------------------------------------
# Simulation (single position, costs, SL-before-TP intrabar = conservative)
# --------------------------------------------------------------------------
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
            if row["low"] <= sl:                                   # SL first
                return "loss", -(risk + cost) / risk, j
            if row["high"] >= tp:
                return "win", (tp - entry - cost) / risk, j
        else:
            if row["high"] >= sl:                                  # SL first
                return "loss", -(risk + cost) / risk, j
            if row["low"] <= tp:
                return "win", (entry - tp - cost) / risk, j

    px = df.iloc[end]["close"]
    pnl = (px - entry) if direction == "BUY" else (entry - px)
    return "timeout", (pnl - cost) / risk, end


# --------------------------------------------------------------------------
# One config = one fresh bot = one full pass over the data
# --------------------------------------------------------------------------
def run_config(df, params, loss_cooldown_bars, bar_sec, cost, window_bars=1000):
    bot = MirrorStrategy(**params)              # FRESH instance: clean dedup state
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
        if result == "loss" and loss_cooldown_bars > 0:
            bot.on_trade_result(result, exit_time,
                                cooldown_seconds=loss_cooldown_bars * bar_sec)
        trades.append({
            "entry_time": pd.Timestamp(df.iloc[i]["time"]),
            "exit_time": pd.Timestamp(exit_time),
            "setup_type": sig.get("setup_type", "n/a"),
            "direction": sig["direction"],
            "result": result,
            "rr": rr,                                  # NET of costs, in R
            "risk": sig.get("risk", np.nan),
            "atr": sig.get("atr", np.nan),
        })
        i = exit_j + 1                                  # single position at a time
    return trades


# --------------------------------------------------------------------------
# Metrics — timeouts INCLUDED in net R / equity / drawdown (they are real P&L)
# --------------------------------------------------------------------------
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
        "net": eq[-1],
        "dd": dd,
        "avg_win": (gp / len(wins)) if wins else None,
        "expectancy": eq[-1] / len(trades),
    }


def fmt(m):
    wr = f"{m['wr']:.1f}" if m["wr"] is not None else "  —"
    pf = f"{m['pf']:.2f}" if m["pf"] not in (None, float("inf")) else "  —"
    aw = f"{m['avg_win']:.2f}" if m["avg_win"] is not None else " —"
    ex = f"{m['expectancy']:+.3f}" if m["expectancy"] is not None else " —"
    return (f"trades {m['trades']:3d} | WR {wr:>5}% | PF {pf:>5} | "
            f"avgWin {aw:>4}R | net {m['net']:+7.2f}R | maxDD {m['dd']:5.2f}R | E/trade {ex}R")


def tkey(t):
    return (t["entry_time"], t["setup_type"], t["direction"])


# --------------------------------------------------------------------------
# Attribution ladder (TRAIN only)
# --------------------------------------------------------------------------
BASE = dict(
    swing_lookback=8,
    eq_tp_extension=0.2,
    min_rr=1.0,
    trend_ema_period=200,
    spread_pct=0.0,          # costs are applied in simulate() — one source of truth
    drop_forming_bar=False,
)

STEPS = [
    ("B0  baseline (v2 logic — but now: costs + single-position)",
     dict(BASE, rejection_mode="inner"), 0),
    ("A1  + full-rejection close (edge)",
     dict(BASE, rejection_mode="edge"), 0),
    ("A6  + mirror reversals OFF",
     dict(BASE, rejection_mode="edge", enable_mirror_setup=False), 0),
    ("A3  + same-zone block + loss cooldown + spacing",
     dict(BASE, rejection_mode="edge", enable_mirror_setup=False,
          zone_reentry_block_bars=240, zone_reentry_atr_mult=0.5,
          post_signal_cooldown_bars=6), 60),
    ("A2  + confirmation bar",
     dict(BASE, rejection_mode="edge", enable_mirror_setup=False,
          zone_reentry_block_bars=240, post_signal_cooldown_bars=6,
          confirm_next_close=True), 60),
    ("A5  + ATR news filter (< 2x median)",
     dict(BASE, rejection_mode="edge", enable_mirror_setup=False,
          zone_reentry_block_bars=240, post_signal_cooldown_bars=6,
          confirm_next_close=True, atr_max_median_mult=2.0), 60),
]
FINAL_NAME, FINAL_PARAMS, FINAL_COOLDOWN = STEPS[-1]


# --------------------------------------------------------------------------
# Breakdown tables (this is what exposes regime concentration / bad hours)
# --------------------------------------------------------------------------
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


def atr_quintile(trades):
    if not trades:
        return "—"
    atrs = sorted(t["atr"] for t in trades if np.isfinite(t["atr"]))
    if not atrs:
        return "—"
    q = [atras := atrs, 0][1]  # placeholder never used
    edges = np.quantile(atrs, [0.2, 0.4, 0.6, 0.8])
    def bucket(a):
        if not np.isfinite(a):
            return "na"
        return f"Q{int(np.searchsorted(edges, a)) + 1}"
    return bucket


def atr_bucket_factory(trades):
    atrs = [t["atr"] for t in trades if np.isfinite(t["atr"])]
    if len(atrs) < 10:
        return lambda t: "na"
    edges = np.quantile(atrs, [0.2, 0.4, 0.6, 0.8])
    def bucket(t):
        if not np.isfinite(t["atr"]):
            return "na"
        return f"Q{int(np.searchsorted(edges, t['atr'])) + 1}"
    return bucket


# --------------------------------------------------------------------------
async def main(symbol, timeframe, days, cost_override):
    print(f"MMC Track-A tuning | {symbol} {timeframe} | last {days} days")
    print("=" * 96)

    end = datetime.now()
    start = end - timedelta(days=days)
    bt = Backtester(symbol, timeframe, start, end)
    df = bt.fetch_data()
    print(f"Loaded {len(df)} candles | pip size {get_pip_size(symbol)} | "
          f"cost/trade {cost_for(symbol, cost_override)} price units")

    if len(df) < 3000 or float(df['close'].iloc[-1]) < 3000 and 'XAU' in symbol.upper() \
            and abs(float(df['close'].iloc[-1]) - 2350.0) < 5:
        print("WARNING: this looks like SYNTHETIC data (MT5 unavailable?). "
              "Numbers will be meaningless.")

    bar_sec = infer_bar_seconds(df)
    split_ts = pd.Timestamp(df["time"].iloc[int(len(df) * 2 / 3)])
    cost = cost_for(symbol, cost_override)
    print(f"Bar size {bar_sec:.0f}s | train < {split_ts} <= validation")

    def is_train(t):
        return t["entry_time"] < split_ts

    # ---- 1) attribution ladder on TRAIN -------------------------------
    print("\n" + "=" * 96)
    print("ATTRIBUTION LADDER (train split only — this is where tuning happens)")
    print("=" * 96)

    prev_train = {}
    train_metrics_by_step = {}
    for name, params, cooldown in STEPS:
        trades = run_config(df, params, cooldown, bar_sec, cost)
        train = [t for t in trades if is_train(t)]
        m = metrics(train)
        train_metrics_by_step[name] = m
        print(f"\n{name}\n    {fmt(m)}")

        if prev_train:
            cur_keys = {tkey(t) for t in train}
            removed = [t for k, t in prev_train.items() if k not in cur_keys]
            if removed:
                rem_r = sum(t["rr"] for t in removed)
                rem_w = len([t for t in removed if t["result"] == "win"])
                print(f"    removed by this step: {len(removed)} trades "
                      f"({rem_w}W/{len(removed)-rem_w}L), combined {rem_r:+.2f}R "
                      f"{'<< REMOVES WINNERS — scrutinize' if rem_r > 0 else '(good cut)'}")
            else:
                print("    removed by this step: 0 trades")
        prev_train = {tkey(t): t for t in train}

    # ---- 2) VALIDATION: final preset, run ONCE -------------------------
    print("\n" + "=" * 96)
    print("VALIDATION — final preset, run once, do not iterate on these numbers")
    print("=" * 96)
    final_trades = run_config(df, FINAL_PARAMS, FINAL_COOLDOWN, bar_sec, cost)
    f_train = [t for t in final_trades if is_train(t)]
    f_val = [t for t in final_trades if not is_train(t)]

    print(f"\n  TRAIN      : {fmt(metrics(f_train))}")
    print(f"  VALIDATION : {fmt(metrics(f_val))}")

    # ---- 3) breakdowns for the final preset (full period) -------------
    breakdown(final_trades, lambda t: t["setup_type"], "per setup")
    breakdown(final_trades, lambda t: t["entry_time"].to_period("M"), "per month")
    breakdown(final_trades, lambda t: t["entry_time"].hour, "per hour (data/server timezone!)")
    breakdown(final_trades, atr_bucket_factory(final_trades), "per ATR quintile (Q5 = most volatile)")
    breakdown(final_trades, lambda t: t["direction"], "per direction")

    # ---- 4) verdict vs the agreed targets ------------------------------
    print("\n" + "=" * 96)
    print("TARGET CHECK (agreed: WR >= 53% point estimate AND expectancy >= +0.08R after costs)")
    print("=" * 96)
    for label, subset in (("TRAIN", f_train), ("VALIDATION", f_val)):
        m = metrics(subset)
        if m["wr"] is None:
            print(f"  {label:11}: no valid trades")
            continue
        ok_wr = m["wr"] >= 53.0
        ok_ex = m["expectancy"] is not None and m["expectancy"] >= 0.08
        print(f"  {label:11}: WR {m['wr']:.1f}% [{'PASS' if ok_wr else 'fail'}] | "
              f"expectancy {m['expectancy']:+.3f}R [{'PASS' if ok_ex else 'fail'}]")

    # optional: dump the final trade list for external audit
    out = pd.DataFrame(final_trades)
    out.to_csv("mmc_trackA_trades.csv", index=False)
    print("\nFinal-preset trade list saved to mmc_trackA_trades.csv "
          "(send this back with the console output)")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="MMC Track-A tuning protocol")
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--timeframe", default="M5", choices=list(TIMEFRAMES.keys()))
    p.add_argument("--days", type=int, default=180)
    p.add_argument("--cost", type=float, default=None,
                   help="Override round-trip cost in price units (default: per-symbol table)")
    args = p.parse_args()
    asyncio.run(main(args.symbol, args.timeframe, args.days, args.cost))