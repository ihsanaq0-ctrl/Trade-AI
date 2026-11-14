"""Admin routes: strategy management (add/remove) + audit journal + public card list."""
from fastapi import APIRouter, Depends, HTTPException

from app.middleware import get_current_user, require_admin
from app.schemas.admin import StrategyCreate
from app.services import strategy_store

router = APIRouter(tags=["admin"])


@router.get("/api/strategies")
async def list_strategies():
    """Public strategy list (built-ins + custom) - powers the bots page cards."""
    return strategy_store.list_all()


@router.get("/api/admin/strategies")
async def admin_list_strategies(user=Depends(require_admin)):
    """Full list for the admin panel; custom entries include their pasted code."""
    items = strategy_store.list_all()
    custom = {c["id"]: c for c in strategy_store.list_custom()}
    for it in items:
        if it["source"] == "custom" and it.get("id") in custom:
            it["code"] = custom[it["id"]]["code"]
    return items


@router.post("/api/admin/strategies")
async def admin_add_strategy(data: StrategyCreate, user=Depends(require_admin)):
    try:
        operator = user.get("email") or user.get("sub") or "admin"
        return strategy_store.add_strategy(data.name, data.code, operator=operator)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/api/admin/strategies/{strategy_id}")
async def admin_remove_strategy(strategy_id: str, user=Depends(require_admin)):
    try:
        return {"success": True, "removed": strategy_store.remove_strategy(strategy_id)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/api/admin/audit")
async def admin_audit(user=Depends(require_admin)):
    return strategy_store.list_audit()
