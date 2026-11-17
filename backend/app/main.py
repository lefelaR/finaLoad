"""TrendLens API. Secrets stay here; the browser only talks to these routes."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

load_dotenv()

from app.auth import mint, verify  # noqa: E402
from app.engine import ORDER, engine  # noqa: E402
from app.logic import DISCLAIMER, MODEL_VERSION, position_size  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("trendlens.api")

HITS: dict[str, list[float]] = defaultdict(list)


@asynccontextmanager
async def lifespan(app: FastAPI):
    boot = asyncio.create_task(engine.bootstrap())
    workers = [
        asyncio.create_task(engine.tick_loop()),
        asyncio.create_task(engine.news_loop()),
        asyncio.create_task(engine.oanda_stream()),
        asyncio.create_task(engine.failover_loop()),
    ]
    yield
    for task in workers + [boot]:
        task.cancel()


app = FastAPI(title="TrendLens", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path.startswith("/api"):
        ip = request.client.host if request.client else "local"
        now = time.time()
        window = [stamp for stamp in HITS[ip] if now - stamp < 60]
        if len(window) >= 300:
            return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
        window.append(now)
        HITS[ip] = window
    return await call_next(request)


def _guard(request: Request) -> None:
    if os.environ.get("AUTH_REQUIRED", "false").lower() != "true":
        return
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if verify(token) is None:
        raise HTTPException(status_code=401, detail="Login required")


class LoginIn(BaseModel):
    email: str
    password: str


class BacktestIn(BaseModel):
    timeframe: str = "H4"
    start: str
    end: str
    capital: float = Field(default=10000, gt=0)
    risk_pct: float = Field(default=1, gt=0, le=100)


class PositionIn(BaseModel):
    balance: float = Field(gt=0)
    risk_pct: float = Field(gt=0, le=100)
    stop_pips: float = Field(gt=0)


class AlertSettingsIn(BaseModel):
    on_flip: bool | None = None
    on_confidence: bool | None = None
    on_news: bool | None = None
    quiet_hours: bool | None = None
    quiet_start: str | None = None
    quiet_end: str | None = None
    email: str | None = None


@app.post("/api/auth/login")
def login(body: LoginIn):
    user = os.environ.get("DEMO_USER", "sipho")
    password = os.environ.get("DEMO_PASSWORD", "demo")
    if body.email != user or body.password != password:
        raise HTTPException(status_code=401, detail="Unknown user")
    return {"token": mint(body.email)}


@app.get("/api/health")
def health():
    oos = None
    if engine.ready and engine.model:
        oos = engine.model["bundles"]["H1"]["oos_start"].isoformat()
    return {
        "ready": engine.ready,
        "message": engine.message,
        "source": engine.source,
        "connection": engine.connection_label,
        "candles": {name: int(len(frame)) for name, frame in engine.frames.items()},
        "model": MODEL_VERSION if engine.ready else None,
        "oos_start": oos,
        "failover_events": engine.failover_events,
        "ingestion_errors": len(engine.ingestion_errors),
        "disclaimer": DISCLAIMER,
    }


@app.get("/api/market")
def market(request: Request):
    _guard(request)
    return engine.market()


@app.get("/api/dashboard")
def dashboard(request: Request):
    _guard(request)
    return engine.dashboard()


@app.get("/api/candles")
def candles(request: Request, timeframe: str = "H1", count: int = 280):
    _guard(request)
    if not engine.ready:
        raise HTTPException(status_code=503, detail=engine.message)
    if timeframe not in ORDER:
        raise HTTPException(status_code=400, detail="Timeframe must be H1, H4 or D1")
    count = max(50, min(count, 800))
    return engine.candle_payload(timeframe, count)


@app.get("/api/calendar")
def calendar(request: Request, currency: str = "ALL"):
    _guard(request)
    from app.engine import filtered_calendar

    if currency not in {"ALL", "EUR", "USD"}:
        raise HTTPException(status_code=400, detail="Currency must be ALL, EUR or USD")
    return filtered_calendar(currency)


@app.get("/api/signals/history")
def signal_history(
    request: Request,
    timeframe: str = "ALL",
    outcome: str = "ALL",
    start: str | None = None,
    end: str | None = None,
):
    _guard(request)
    if not engine.ready:
        raise HTTPException(status_code=503, detail=engine.message)
    if timeframe not in {"ALL", *ORDER}:
        raise HTTPException(status_code=400, detail="Unknown timeframe")
    return {"rows": engine.signal_history(timeframe, outcome, start, end)}


@app.post("/api/backtest")
def backtest(body: BacktestIn, request: Request):
    _guard(request)
    if not engine.ready:
        raise HTTPException(status_code=503, detail=engine.message)
    if body.timeframe not in ORDER:
        raise HTTPException(status_code=400, detail="Timeframe must be H1, H4 or D1")
    try:
        return engine.backtest(body.timeframe, body.start, body.end, body.capital, body.risk_pct)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/risk/position")
def position(body: PositionIn, request: Request):
    _guard(request)
    if not engine.ready:
        raise HTTPException(status_code=503, detail=engine.message)
    try:
        sized = position_size(body.balance, body.risk_pct, body.stop_pips, engine.usdzar)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    sized["usdzar"] = round(engine.usdzar, 4)
    sized["usdzar_source"] = engine.usdzar_source
    sized["eurusd"] = engine.mid
    sized["disclaimer"] = DISCLAIMER
    return sized


@app.get("/api/alerts")
def alerts(request: Request):
    _guard(request)
    return {"settings": engine.alert_settings, "alerts": engine.alerts}


@app.post("/api/alerts/settings")
def alert_settings(body: AlertSettingsIn, request: Request):
    _guard(request)
    updates = {key: value for key, value in body.model_dump().items() if value is not None}
    return engine.save_settings(updates)
