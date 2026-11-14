"""
run_mmc_round3.py — Track-A FINAL round. Pre-declared, one validation look.

Round-2 evidence applied:
  'mid' rejection (C3) : best train config (54.2% WR, E +0.137R) -> base
  ATR < 1.5x median    : binds, removed -1.98R of losers on train -> stack (C4)
  longer cooldown      : diagnostic only (C5)

Decision rule (fixed BEFORE running, do not renegotiate after seeing output):
  Tier 1 (live candidate): val WR >= 53% AND val E >= +0.10R
  Tier 2 (paper only)    : val WR >= 50% AND val E >= +0.05R
  Tier 3 (STOP)          : anything else -> stop tuning; fix data depth instead

Winner between C4/C5 is chosen by TRAIN expectancy, then validated ONCE.
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
    rejection_mode="mid",            # round-2 winner
    enable_mirror_setup=False,       # A6 kept
    zone_reentry_block_bars=240,
    zone_reentry_atr_mult=0.5,
    post_signal_cooldown_bars=6,
)

C3_REF  = dict(BASE), 60
C4      = dict(BASE, atr_max_median_mult=1.5), 60
C5      = dict(BASE, atr_max_median_mult=1.5), 180   # longer loss cooldown


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


def run_config(df, cfg, bar_sec, cost, window_bars=1000):
    params, cooldown_bars = cfg
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
    print(f"MMC Track-A ROUND 3 (FINAL) | {symbol} {timeframe} | last {days} days")
    print("=" * 96)

    end = datetime.now()
    start = end - timedelta(days=days)
    bt = Backtester(symbol, timeframe, start, end)
    df = bt.fetch_data()
    print(f"Loaded {len(df)} candles | cost/trade {cost_for(symbol, cost_override)}")
    if len(df) < 20000:
        print("ABORT-LEVEL WARNING: candle count low. If this is the synthetic "
              "fallback (~2000 candles, base 2350 or 2777), STOP and fix MT5.")
    if len(df) < 6000:
        return

    bar_sec = infer_bar_seconds(df)
    split_ts = pd.Timestamp(df["time"].iloc[int(len(df) * 2 / 3)])
    cost = cost_for(symbol, cost_override)
    print(f"Bar size {bar_sec:.0f}s | train < {split_ts} <= validation")

    def is_train(t):
        return t["entry_time"] < split_ts

    print("\n" + "=" * 96)
    print("TRAIN PHASE — C4/C5 compete on TRAIN expectancy only")
    print("=" * 96)

    c3_trades = run_config(df, C3_REF, bar_sec, cost)
    c4_trades = run_config(df, C4, bar_sec, cost)
    c5_trades = run_config(df, C5, bar_sec, cost)

    for name, trades in (("C3 (reference, round-2 winner)", c3_trades),
                         ("C4 (= C3 + ATR<1.5x median)", c4_trades),
                         ("C5 (= C4 + 180-bar loss cooldown)", c5_trades)):
        m = metrics([t for t in trades if is_train(t)])
        print(f"\n{name}\n    TRAIN {fmt(m)}")

    # kill-count: what C4 removed vs C3, on train
    c3_train_keys = {(t["entry_time"], t["direction"]) for t in c3_trades if is_train(t)}
    c4_train = [t for t in c4_trades if is_train(t)]
    removed = [t for t in c3_trades if is_train(t)
               and (t["entry_time"], t["direction"]) not in
               {(x["entry_time"], x["direction"]) for x in c4_train}]
    if removed:
        rem_r = sum(t["rr"] for t in removed)
        rem_w = len([t for t in removed if t["result"] == "win"])
        print(f"\n    C4 vs C3 kill-count: removed {len(removed)} trades "
              f"({rem_w}W/{len(removed)-rem_w}L), combined {rem_r:+.2f}R "
              f"{'<< REMOVES WINNERS' if rem_r > 0 else '(good cut)'}")

    m4 = metrics(c4_train)
    m5 = metrics([t for t in c5_trades if is_train(t)])
    winner_name, winner_trades = (("C4", c4_trades)
                                  if (m4["expectancy"] or -9) >= (m5["expectancy"] or -9)
                                  else ("C5", c5_trades))
    print(f"\n    WINNER BY TRAIN EXPECTANCY: {winner_name}")

    print("\n" + "=" * 96)
    print(f"VALIDATION — {winner_name}, one look, FINAL. Decision rule is pre-declared.")
    print("=" * 96)
    w_train = [t for t in winner_trades if is_train(t)]
    w_val = [t for t in winner_trades if not is_train(t)]
    print(f"\n  {winner_name} TRAIN      : {fmt(metrics(w_train))}")
    print(f"  {winner_name} VALIDATION : {fmt(metrics(w_val))}")

    breakdown(winner_trades, lambda t: t["entry_time"].to_period("M"), f"{winner_name} per month")
    breakdown(winner_trades, lambda t: t["direction"], f"{winner_name} per direction (regime artifact — NOT a filter)")

    m_val = metrics(w_val)
    print("\n" + "=" * 96)
    print("PRE-DECLARED DECISION (do not renegotiate after reading)")
    print("=" * 96)
    if m_val["wr"] is None:
        print("  TIER 3 — no valid validation trades. STOP; fix data depth.")
    elif m_val["wr"] >= 53.0 and (m_val["expectancy"] or -9) >= 0.10:
        print("  TIER 1 — LIVE CANDIDATE (paper-trade 2-4 weeks before any live use)")
    elif m_val["wr"] >= 50.0 and (m_val["expectancy"] or -9) >= 0.05:
        print("  TIER 2 — PAPER TRADING ONLY. Promising, unproven. More data needed.")
    else:
        print("  TIER 3 — STOP TUNING MMC. Bottleneck is data, not filters.")

    pooled = metrics(winner_trades)
    if pooled["trades"] > 1:
        se = np.std([t["rr"] for t in winner_trades], ddof=1) / np.sqrt(pooled["trades"])
        t_stat = pooled["expectancy"] / se if se > 0 else 0.0
        print(f"  Pooled: {fmt(pooled)}  |  t-stat vs zero edge: {t_stat:.2f} "
              f"(<2 = indistinguishable from noise)")

    pd.DataFrame(winner_trades).to_csv("mmc_round3_trades.csv", index=False)
    print(f"\n{winner_name} trade list saved to mmc_round3_trades.csv")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="MMC Track-A round 3 (final)")
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--timeframe", default="M5", choices=list(TIMEFRAMES.keys()))
    p.add_argument("--days", type=int, default=180)
    p.add_argument("--cost", type=float, default=None)
    args = p.parse_args()
    asyncio.run(main(args.symbol, args.timeframe, args.days, args.cost))