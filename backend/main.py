from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import health, accounts, bots, trades, analytics, payments, admin, ai_agents

app = FastAPI(title="Trade-AI API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.cors_origins] if settings.cors_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(accounts.router)
app.include_router(bots.router)
app.include_router(trades.router)
app.include_router(analytics.router)
app.include_router(payments.router)
app.include_router(admin.router)
app.include_router(ai_agents.router)

@app.on_event("startup")
async def startup():
    from app.services.bot_engine import resume_running_bots
    await resume_running_bots()
