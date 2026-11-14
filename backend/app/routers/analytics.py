from fastapi import APIRouter, Depends, Query
from app.database import supabase
from app.middleware import get_current_user
from app.schemas.analytics import Overview, EquityPoint, StrategyPerformance, PairPerformance, MonthlyReturn, DrawdownInfo
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

def get_date_range(from_date: str = None, to_date: str = None):
    now = datetime.utcnow()
    if not to_date:
        to_date = now.isoformat()
    if not from_date:
        from_date = (now - timedelta(days=30)).isoformat()
    return from_date, to_date

@router.get("/overview")
async def get_overview(user=Depends(get_current_user), from_date: str = None, to_date: str = None):
    try:
        query = supabase.table("trades").select("*").eq("user_id", user["sub"]).eq("status", "closed")
        if from_date:
            query = query.gte("closed_at", from_date)
        if to_date:
            query = query.lte("closed_at", to_date)
        result = query.execute()

        trades = result.data or []
        total = len(trades)
        winning = [t for t in trades if float(t.get("profit") or 0) > 0]
        losing = [t for t in trades if float(t.get("profit") or 0) <= 0]
        gross_profit = sum(float(t.get("profit") or 0) for t in winning)
        gross_loss = abs(sum(float(t.get("profit") or 0) for t in losing))
        total_profit = gross_profit - gross_loss

        return Overview(
            total_trades=total,
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate=round(len(winning) / total * 100, 1) if total else 0.0,
            total_profit=round(total_profit, 2),
            gross_profit=round(gross_profit, 2),
            gross_loss=round(gross_loss, 2),
            profit_factor=round(gross_profit / gross_loss, 2) if gross_loss else (round(gross_profit, 2) if gross_profit else 0.0),
            avg_profit=round(total_profit / total, 2) if total else 0.0,
            avg_pips=round(sum(float(t.get("pips") or 0) for t in trades) / total, 1) if total else 0.0
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error in overview: {e}")
        return Overview()

@router.get("/equity-curve")
async def get_equity_curve(user=Depends(get_current_user), from_date: str = None, to_date: str = None):
    try:
        # Fetch base account balance
        acc_res = supabase.table("accounts").select("balance, equity").eq("user_id", user["sub"]).order("created_at", desc=False).limit(1).execute()
        base_balance = 0.0
        if acc_res.data and len(acc_res.data) > 0:
            base_balance = float(acc_res.data[0].get("balance") or 0.0)

        query = supabase.table("trades").select("*").eq("user_id", user["sub"]).eq("status", "closed").order("closed_at")
        if from_date:
            query = query.gte("closed_at", from_date)
        if to_date:
            query = query.lte("closed_at", to_date)
        result = query.execute()

        trades = result.data or []
        running = 0.0
        curve = []
        for t in trades:
            running += float(t.get("profit") or 0)
            date_str = str(t.get("closed_at") or t.get("opened_at") or "")[:10]
            curve.append({"date": date_str, "equity": round(base_balance + running, 2)})
        return curve
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error in equity-curve: {e}")
        return []

@router.get("/by-strategy")
async def get_by_strategy(user=Depends(get_current_user), from_date: str = None, to_date: str = None):
    try:
        query = supabase.table("trades").select("*").eq("user_id", user["sub"]).eq("status", "closed")
        if from_date:
            query = query.gte("closed_at", from_date)
        if to_date:
            query = query.lte("closed_at", to_date)
        result = query.execute()

        trades = result.data or []
        by_strat = {}
        for t in trades:
            s = t.get("strategy") or "unknown"
            if s not in by_strat:
                by_strat[s] = {"trades": 0, "wins": 0, "profit": 0.0}
            by_strat[s]["trades"] += 1
            profit = float(t.get("profit") or 0)
            by_strat[s]["profit"] += profit
            if profit > 0:
                by_strat[s]["wins"] += 1
        return [{"strategy": k, "trades": v["trades"], "wins": v["wins"], "profit": round(v["profit"], 2), "win_rate": round(v["wins"] / v["trades"] * 100, 1) if v["trades"] else 0.0} for k, v in by_strat.items()]
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error in by-strategy: {e}")
        return []

@router.get("/by-pair")
async def get_by_pair(user=Depends(get_current_user), from_date: str = None, to_date: str = None):
    try:
        query = supabase.table("trades").select("*").eq("user_id", user["sub"]).eq("status", "closed")
        if from_date:
            query = query.gte("closed_at", from_date)
        if to_date:
            query = query.lte("closed_at", to_date)
        result = query.execute()

        trades = result.data or []
        by_pair = {}
        for t in trades:
            p = t.get("symbol") or t.get("pair") or "unknown"
            if p not in by_pair:
                by_pair[p] = {"trades": 0, "wins": 0, "profit": 0.0}
            by_pair[p]["trades"] += 1
            profit = float(t.get("profit") or 0)
            by_pair[p]["profit"] += profit
            if profit > 0:
                by_pair[p]["wins"] += 1
        return [{"pair": k, "trades": v["trades"], "wins": v["wins"], "profit": round(v["profit"], 2), "win_rate": round(v["wins"] / v["trades"] * 100, 1) if v["trades"] else 0.0} for k, v in by_pair.items()]
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error in by-pair: {e}")
        return []

@router.get("/monthly")
async def get_monthly(user=Depends(get_current_user)):
    try:
        result = supabase.table("trades").select("*").eq("user_id", user["sub"]).eq("status", "closed").execute()
        trades = result.data or []
        by_month = {}
        for t in trades:
            m = str(t.get("closed_at") or t.get("opened_at") or "")[:7]
            if not m:
                continue
            if m not in by_month:
                by_month[m] = {"profit": 0.0, "trades": 0}
            by_month[m]["profit"] += float(t.get("profit") or 0)
            by_month[m]["trades"] += 1
        return [{"month": k, "profit": round(v["profit"], 2), "trades": v["trades"]} for k, v in sorted(by_month.items())]
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error in monthly: {e}")
        return []

@router.get("/drawdown")
async def get_drawdown(user=Depends(get_current_user)):
    try:
        acc_res = supabase.table("accounts").select("balance, equity").eq("user_id", user["sub"]).order("created_at", desc=False).limit(1).execute()
        base_balance = 0.0
        if acc_res.data and len(acc_res.data) > 0:
            base_balance = float(acc_res.data[0].get("balance") or 0.0)

        result = supabase.table("trades").select("*").eq("user_id", user["sub"]).eq("status", "closed").order("closed_at").execute()
        trades = result.data or []

        peak = base_balance
        current_equity = base_balance
        max_dd_amount = 0.0
        max_dd_pct = 0.0

        for t in trades:
            profit = float(t.get("profit") or 0)
            current_equity += profit
            if current_equity > peak:
                peak = current_equity
            dd_amount = peak - current_equity
            dd_pct = (dd_amount / peak * 100.0) if peak > 0 else 0.0
            if dd_amount > max_dd_amount:
                max_dd_amount = dd_amount
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct

        curr_dd_pct = ((peak - current_equity) / peak * 100.0) if (peak > 0 and current_equity < peak) else 0.0

        return DrawdownInfo(
            max_drawdown_pct=round(max_dd_pct, 2),
            max_drawdown_amount=round(max_dd_amount, 2),
            current_drawdown=round(curr_dd_pct, 2)
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error calculating drawdown: {e}")
        return DrawdownInfo(max_drawdown_pct=0.0, max_drawdown_amount=0.0, current_drawdown=0.0)
