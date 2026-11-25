import asyncio
import logging
from fastapi import APIRouter, Depends, Query
from app.database import supabase
from app.middleware import get_current_user
from app.schemas.analytics import Overview, DrawdownInfo
from app.services import metaapi_service as mt5

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analytics", tags=["analytics"])

_ANALYTICS_COLS = "id, symbol, direction, volume, open_price, close_price, profit, strategy, status, opened_at, closed_at, ticket"


def _compute_overview(closed_trades: list) -> dict:
    total = len(closed_trades)
    winning = [t for t in closed_trades if float(t.get("profit") or 0) > 0]
    losing = [t for t in closed_trades if float(t.get("profit") or 0) <= 0]
    gross_profit = sum(float(t.get("profit") or 0) for t in winning)
    gross_loss = abs(sum(float(t.get("profit") or 0) for t in losing))
    total_profit = gross_profit - gross_loss
    return {
        "total_trades": total,
        "winning_trades": len(winning),
        "losing_trades": len(losing),
        "win_rate": round(len(winning) / total * 100, 1) if total else 0.0,
        "total_profit": round(total_profit, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss else (round(gross_profit, 2) if gross_profit else 0.0),
        "avg_profit": round(total_profit / total, 2) if total else 0.0,
        "avg_pips": round(sum(float(t.get("pips") or 0) for t in closed_trades) / total, 1) if total else 0.0,
    }


def _compute_equity_and_drawdown(closed_trades_sorted: list, base_balance: float) -> tuple[list, dict]:
    running = 0.0
    curve = []
    peak = base_balance
    current_equity = base_balance
    max_dd_amount = 0.0
    max_dd_pct = 0.0

    for t in closed_trades_sorted:
        profit = float(t.get("profit") or 0)
        running += profit
        current_equity += profit
        date_str = str(t.get("closed_at") or t.get("opened_at") or "")[:10]
        curve.append({"date": date_str, "equity": round(base_balance + running, 2)})

        if current_equity > peak:
            peak = current_equity
        dd_amount = peak - current_equity
        dd_pct = (dd_amount / peak * 100.0) if peak > 0 else 0.0
        if dd_amount > max_dd_amount:
            max_dd_amount = dd_amount
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct

    curr_dd_pct = ((peak - current_equity) / peak * 100.0) if (peak > 0 and current_equity < peak) else 0.0
    drawdown = {
        "max_drawdown_pct": round(max_dd_pct, 2),
        "max_drawdown_amount": round(max_dd_amount, 2),
        "current_drawdown": round(curr_dd_pct, 2),
    }
    return curve, drawdown


def _compute_by_strategy(closed_trades: list) -> list:
    by_strat = {}
    for t in closed_trades:
        s = t.get("strategy") or "manual"
        if s not in by_strat:
            by_strat[s] = {"trades": 0, "wins": 0, "profit": 0.0}
        by_strat[s]["trades"] += 1
        profit = float(t.get("profit") or 0)
        by_strat[s]["profit"] += profit
        if profit > 0:
            by_strat[s]["wins"] += 1
    return [
        {
            "strategy": k,
            "trades": v["trades"],
            "wins": v["wins"],
            "profit": round(v["profit"], 2),
            "win_rate": round(v["wins"] / v["trades"] * 100, 1) if v["trades"] else 0.0,
        }
        for k, v in by_strat.items()
    ]


def _compute_by_pair(closed_trades: list) -> list:
    by_pair = {}
    for t in closed_trades:
        p = t.get("symbol") or "unknown"
        if p not in by_pair:
            by_pair[p] = {"trades": 0, "wins": 0, "profit": 0.0}
        by_pair[p]["trades"] += 1
        profit = float(t.get("profit") or 0)
        by_pair[p]["profit"] += profit
        if profit > 0:
            by_pair[p]["wins"] += 1
    return [
        {
            "pair": k,
            "trades": v["trades"],
            "wins": v["wins"],
            "profit": round(v["profit"], 2),
            "win_rate": round(v["wins"] / v["trades"] * 100, 1) if v["trades"] else 0.0,
        }
        for k, v in by_pair.items()
    ]


def _compute_monthly(closed_trades: list) -> list:
    by_month = {}
    for t in closed_trades:
        m = str(t.get("closed_at") or t.get("opened_at") or "")[:7]
        if not m:
            continue
        if m not in by_month:
            by_month[m] = {"profit": 0.0, "trades": 0}
        by_month[m]["profit"] += float(t.get("profit") or 0)
        by_month[m]["trades"] += 1
    return [{"month": k, "profit": round(v["profit"], 2), "trades": v["trades"]} for k, v in sorted(by_month.items())]


@router.get("/summary")
async def get_analytics_summary(
    user=Depends(get_current_user),
    from_date: str = None,
    to_date: str = None,
    limit: int = Query(100, le=200),
):
    """
    Single high-speed endpoint returning overview, equity curve, strategy breakdown,
    pair breakdown, monthly returns, drawdown, and recent trades in one parallel DB pass.
    Eliminates 6x duplicate Supabase queries on Dashboard & Analytics load.
    """
    try:
        def _fetch_trades():
            return (
                supabase.table("trades")
                .select(_ANALYTICS_COLS)
                .eq("user_id", user["sub"])
                .order("opened_at", desc=True)
                .limit(500)
                .execute()
            )

        def _fetch_account():
            return (
                supabase.table("accounts")
                .select("login, balance, equity, status")
                .eq("user_id", user["sub"])
                .order("created_at", desc=False)
                .execute()
            )

        tr_res, acc_res, terminal_info = await asyncio.gather(
            asyncio.to_thread(_fetch_trades),
            asyncio.to_thread(_fetch_account),
            mt5.get_account_info(""),
        )

        all_trades = tr_res.data or []
        accounts = acc_res.data or []
        connected_acc = next((a for a in accounts if a.get("status") == "connected"), None)
        base_balance = float((connected_acc or (accounts[0] if accounts else {})).get("balance") or 0.0)

        # Check if MT5 Desktop is synced to THIS authenticated user's connected account
        user_login = str(connected_acc.get("login", "")).strip() if connected_acc else ""
        terminal_login = str(terminal_info.get("login", "")).strip() if terminal_info else ""
        terminal_synced = bool(user_login and terminal_login and user_login == terminal_login)

        live_positions = []
        floating_pnl = 0.0
        if terminal_synced:
            try:
                live_positions = await mt5.get_positions("")
                floating_pnl = sum(float(p.get("profit") or 0) + float(p.get("swap") or 0) for p in live_positions)
            except Exception as mt5_err:
                logger.debug(f"Live positions fetch warning: {mt5_err}")

        # Merge live MT5 open position P&L & prices into recent trades list cleanly
        live_by_ticket = {str(p.get("ticket")): p for p in live_positions}
        seen_tickets = set()
        merged_trades = []

        # Include live MT5 positions first so open MT5 trades always show up with live profit!
        db_by_ticket = {str(t.get("ticket")): t for t in all_trades if t.get("ticket")}
        for p in live_positions:
            t_str = str(p.get("ticket"))
            seen_tickets.add(t_str)
            db_row = db_by_ticket.get(t_str)
            merged_trades.append({
                "id": db_row.get("id") if db_row else f"mt5-{t_str}",
                "ticket": t_str,
                "symbol": p.get("symbol"),
                "direction": (p.get("type") or "BUY").lower(),
                "volume": p.get("volume"),
                "open_price": p.get("open_price"),
                "current_price": p.get("current_price"),
                "stop_loss": p.get("stop_loss"),
                "take_profit": p.get("take_profit"),
                "profit": round(float(p.get("profit") or 0), 2),
                "strategy": (db_row.get("strategy") if db_row else None) or (p.get("comment") or "mt5_live"),
                "status": "open",
                "opened_at": p.get("time") or (db_row.get("opened_at") if db_row else None),
                "is_live": True,
            })

        for t in all_trades:
            t_str = str(t.get("ticket") or "")
            if t_str and t_str in seen_tickets:
                continue
            merged_trades.append(t)

        closed_all = [t for t in all_trades if (t.get("status") or "").lower() == "closed"]
        closed_filtered = closed_all
        if from_date:
            closed_filtered = [t for t in closed_filtered if (t.get("closed_at") or "") >= from_date]
        if to_date:
            closed_filtered = [t for t in closed_filtered if (t.get("closed_at") or "") <= to_date]

        closed_sorted = sorted(closed_filtered, key=lambda t: t.get("closed_at") or t.get("opened_at") or "")
        closed_all_sorted = sorted(closed_all, key=lambda t: t.get("closed_at") or t.get("opened_at") or "")

        overview = _compute_overview(closed_filtered)
        equity_curve, _ = _compute_equity_and_drawdown(closed_sorted, base_balance)
        _, drawdown = _compute_equity_and_drawdown(closed_all_sorted, base_balance)

        limit_val = limit if isinstance(limit, int) else getattr(limit, "default", 100)
        return {
            "overview": overview,
            "equity_curve": equity_curve,
            "by_strategy": _compute_by_strategy(closed_filtered),
            "by_pair": _compute_by_pair(closed_filtered),
            "monthly": _compute_monthly(closed_all),
            "drawdown": drawdown,
            "trades": merged_trades[:limit_val],
            "live_positions": live_positions,
            "floating_pnl": round(floating_pnl, 2),
            "terminal_synced": terminal_synced,
        }
    except Exception as e:
        logger.error(f"Error in analytics summary: {e}")
        return {
            "overview": Overview().model_dump(),
            "equity_curve": [],
            "by_strategy": [],
            "by_pair": [],
            "monthly": [],
            "drawdown": {"max_drawdown_pct": 0.0, "max_drawdown_amount": 0.0, "current_drawdown": 0.0},
            "trades": [],
            "live_positions": [],
            "floating_pnl": 0.0,
            "terminal_synced": False,
        }


@router.get("/overview")
async def get_overview(user=Depends(get_current_user), from_date: str = None, to_date: str = None):
    try:
        def _q():
            query = supabase.table("trades").select("profit, open_price, close_price, symbol").eq("user_id", user["sub"]).eq("status", "closed")
            if from_date:
                query = query.gte("closed_at", from_date)
            if to_date:
                query = query.lte("closed_at", to_date)
            return query.execute()

        result = await asyncio.to_thread(_q)
        return Overview(**_compute_overview(result.data or []))
    except Exception as e:
        logger.error(f"Error in overview: {e}")
        return Overview()


@router.get("/equity-curve")
async def get_equity_curve(user=Depends(get_current_user), from_date: str = None, to_date: str = None):
    try:
        def _acc():
            return supabase.table("accounts").select("balance").eq("user_id", user["sub"]).order("created_at", desc=False).limit(1).execute()

        def _tr():
            query = supabase.table("trades").select("profit, closed_at, opened_at").eq("user_id", user["sub"]).eq("status", "closed").order("closed_at")
            if from_date:
                query = query.gte("closed_at", from_date)
            if to_date:
                query = query.lte("closed_at", to_date)
            return query.execute()

        acc_res, result = await asyncio.gather(asyncio.to_thread(_acc), asyncio.to_thread(_tr))
        base_balance = float(acc_res.data[0].get("balance") or 0.0) if acc_res.data else 0.0
        curve, _ = _compute_equity_and_drawdown(result.data or [], base_balance)
        return curve
    except Exception as e:
        logger.error(f"Error in equity-curve: {e}")
        return []


@router.get("/by-strategy")
async def get_by_strategy(user=Depends(get_current_user), from_date: str = None, to_date: str = None):
    try:
        def _q():
            query = supabase.table("trades").select("strategy, profit").eq("user_id", user["sub"]).eq("status", "closed")
            if from_date:
                query = query.gte("closed_at", from_date)
            if to_date:
                query = query.lte("closed_at", to_date)
            return query.execute()

        result = await asyncio.to_thread(_q)
        return _compute_by_strategy(result.data or [])
    except Exception as e:
        logger.error(f"Error in by-strategy: {e}")
        return []


@router.get("/by-pair")
async def get_by_pair(user=Depends(get_current_user), from_date: str = None, to_date: str = None):
    try:
        def _q():
            query = supabase.table("trades").select("symbol, profit").eq("user_id", user["sub"]).eq("status", "closed")
            if from_date:
                query = query.gte("closed_at", from_date)
            if to_date:
                query = query.lte("closed_at", to_date)
            return query.execute()

        result = await asyncio.to_thread(_q)
        return _compute_by_pair(result.data or [])
    except Exception as e:
        logger.error(f"Error in by-pair: {e}")
        return []


@router.get("/monthly")
async def get_monthly(user=Depends(get_current_user)):
    try:
        result = await asyncio.to_thread(
            lambda: supabase.table("trades").select("closed_at, opened_at, profit").eq("user_id", user["sub"]).eq("status", "closed").execute()
        )
        return _compute_monthly(result.data or [])
    except Exception as e:
        logger.error(f"Error in monthly: {e}")
        return []


@router.get("/drawdown")
async def get_drawdown(user=Depends(get_current_user)):
    try:
        def _acc():
            return supabase.table("accounts").select("balance").eq("user_id", user["sub"]).order("created_at", desc=False).limit(1).execute()

        def _tr():
            return supabase.table("trades").select("profit, closed_at, opened_at").eq("user_id", user["sub"]).eq("status", "closed").order("closed_at").execute()

        acc_res, result = await asyncio.gather(asyncio.to_thread(_acc), asyncio.to_thread(_tr))
        base_balance = float(acc_res.data[0].get("balance") or 0.0) if acc_res.data else 0.0
        _, dd = _compute_equity_and_drawdown(result.data or [], base_balance)
        return DrawdownInfo(**dd)
    except Exception as e:
        logger.error(f"Error calculating drawdown: {e}")
        return DrawdownInfo(max_drawdown_pct=0.0, max_drawdown_amount=0.0, current_drawdown=0.0)
