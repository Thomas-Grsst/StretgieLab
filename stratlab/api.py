from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from stratlab import __version__, indicators as ind
from stratlab.ai.assistant import AssistantUnavailable, generate_strategy, ollama_status
from stratlab.backtest.engine import BacktestSettings, run_backtest
from stratlab.config import database_path
from stratlab.data.csv_import import parse_ohlcv_csv
from stratlab.data.demo import DEMO_ASSETS, generate_demo_bars
from stratlab.data.online import OnlineSourceUnavailable, download_yahoo
from stratlab.data.store import Store
from stratlab.portfolio import aligned_returns, analyze_portfolio
from stratlab.strategies.builtin import BUILTIN_STRATEGIES, describe_builtins, resolve_params
from stratlab.strategies.sandbox import STRATEGY_TEMPLATE, StrategyCodeError, run_custom_strategy, validate_code

WEB_DIR = Path(__file__).parent / "web"


class BacktestRequest(BaseModel):
    symbol: str
    strategy: str = Field(description="Clé d'une stratégie intégrée, 'custom' ou 'saved:<nom>'")
    params: dict = {}
    code: str | None = None
    start: str | None = None
    end: str | None = None
    fee_bps: float = Field(5.0, ge=0, le=500)
    slippage_bps: float = Field(2.0, ge=0, le=500)
    allow_short: bool = False
    initial_capital: float = Field(10_000.0, gt=0)


class PortfolioRequest(BaseModel):
    symbols: list[str] = Field(min_length=2, max_length=20)
    weights: dict[str, float] | None = None
    start: str | None = None
    end: str | None = None


class StrategyPayload(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    code: str
    description: str = ""


class AssistantRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=4000)
    model: str
    previous_code: str | None = None


class DownloadRequest(BaseModel):
    symbol: str
    period: str = "10y"


def create_app(store: Store | None = None) -> FastAPI:
    store = store or Store(database_path())
    app = FastAPI(title="StratégieLab", version=__version__)
    _seed_demo_data(store)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__, "database": str(database_path())}

    @app.get("/api/symbols")
    def symbols() -> list[dict]:
        return store.list_symbols()

    @app.delete("/api/symbols/{symbol}")
    def delete_symbol(symbol: str) -> dict:
        store.delete_symbol(symbol)
        return {"deleted": symbol}

    @app.post("/api/import/csv")
    async def import_csv(symbol: str = Form(...), file: UploadFile = File(...)) -> dict:
        try:
            bars = parse_ohlcv_csv(await file.read())
            count = store.save_bars(symbol, bars, source=f"csv:{file.filename}")
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        return {"symbol": symbol.upper(), "bars": count}

    @app.post("/api/import/demo")
    def import_demo() -> dict:
        return {"symbols": _seed_demo_data(store, force=True)}

    @app.post("/api/import/download")
    def import_download(request: DownloadRequest) -> dict:
        try:
            bars = download_yahoo(request.symbol, request.period)
        except OnlineSourceUnavailable as error:
            raise HTTPException(503, str(error)) from error
        return {"symbol": request.symbol.upper(), "bars": store.save_bars(request.symbol, bars, source="yahoo")}

    @app.get("/api/bars/{symbol}")
    def bars(symbol: str, start: str | None = None, end: str | None = None) -> dict:
        frame = _load(store, symbol, start, end)
        close = frame["close"]
        bands = ind.bollinger(close)
        macd = ind.macd(close)
        return {
            "symbol": symbol.upper(),
            "candles": [
                {"time": d.strftime("%Y-%m-%d"), "open": o, "high": h, "low": l, "close": c, "volume": v}
                for d, (o, h, l, c, v) in zip(frame.index, frame.to_numpy().round(4).tolist())
            ],
            "indicators": {
                "sma20": _points(ind.sma(close, 20)),
                "sma50": _points(ind.sma(close, 50)),
                "sma200": _points(ind.sma(close, 200)),
                "ema20": _points(ind.ema(close, 20)),
                "bb_upper": _points(bands["upper"]),
                "bb_lower": _points(bands["lower"]),
                "rsi14": _points(ind.rsi(close, 14)),
                "macd": _points(macd["macd"]),
                "macd_signal": _points(macd["signal"]),
                "macd_hist": _points(macd["histogram"]),
            },
        }

    @app.get("/api/strategies")
    def strategies() -> dict:
        return {"builtin": describe_builtins(), "saved": store.list_strategies(), "template": STRATEGY_TEMPLATE}

    @app.post("/api/strategies")
    def save_strategy(payload: StrategyPayload) -> dict:
        try:
            validate_code(payload.code)
        except StrategyCodeError as error:
            raise HTTPException(400, str(error)) from error
        store.save_strategy(payload.name, payload.code, payload.description)
        return {"saved": payload.name}

    @app.delete("/api/strategies/{name}")
    def delete_strategy(name: str) -> dict:
        store.delete_strategy(name)
        return {"deleted": name}

    @app.post("/api/backtest")
    def backtest(request: BacktestRequest) -> dict:
        frame = _load(store, request.symbol, request.start, request.end)
        if len(frame) < 30:
            raise HTTPException(400, "Il faut au moins 30 barres pour un backtest")
        signals, params = _signals(store, request, frame)
        settings = BacktestSettings(
            fee_bps=request.fee_bps,
            slippage_bps=request.slippage_bps,
            allow_short=request.allow_short,
            initial_capital=request.initial_capital,
        )
        result = run_backtest(frame, signals, settings)
        result.update({"symbol": request.symbol.upper(), "strategy": request.strategy, "params": params})
        return result

    @app.post("/api/portfolio")
    def portfolio(request: PortfolioRequest) -> dict:
        closes = {s.upper(): _load(store, s, request.start, request.end)["close"] for s in request.symbols}
        try:
            returns = aligned_returns(closes)
            weights = {k.upper(): v for k, v in request.weights.items()} if request.weights else None
            return analyze_portfolio(returns, weights)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @app.get("/api/assistant/status")
    def assistant_status() -> dict:
        return ollama_status()

    @app.post("/api/assistant/strategy")
    def assistant_strategy(request: AssistantRequest) -> dict:
        try:
            result = generate_strategy(request.prompt, request.model, request.previous_code)
        except AssistantUnavailable as error:
            raise HTTPException(503, str(error)) from error
        result["validation_error"] = None
        if result["code"]:
            try:
                validate_code(result["code"])
            except StrategyCodeError as error:
                result["validation_error"] = str(error)
        return result

    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    return app


def _seed_demo_data(store: Store, force: bool = False) -> list[str]:
    if store.list_symbols() and not force:
        return []
    for symbol in DEMO_ASSETS:
        store.save_bars(symbol, generate_demo_bars(symbol), source="démo (synthétique)")
    return list(DEMO_ASSETS)


def _load(store: Store, symbol: str, start: str | None, end: str | None) -> pd.DataFrame:
    try:
        return store.load_bars(symbol, start, end)
    except KeyError as error:
        raise HTTPException(404, str(error.args[0])) from error
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


def _signals(store: Store, request: BacktestRequest, frame: pd.DataFrame) -> tuple[pd.Series, dict]:
    if request.strategy in BUILTIN_STRATEGIES:
        strategy = BUILTIN_STRATEGIES[request.strategy]
        params = resolve_params(strategy, request.params)
        return strategy.generate(frame, params), params
    if request.strategy == "custom":
        code = request.code
    elif request.strategy.startswith("saved:"):
        try:
            code = store.get_strategy(request.strategy.removeprefix("saved:"))["code"]
        except KeyError as error:
            raise HTTPException(404, str(error.args[0])) from error
    else:
        raise HTTPException(400, f"Stratégie inconnue : {request.strategy}")
    if not code:
        raise HTTPException(400, "Aucun code de stratégie fourni")
    try:
        return run_custom_strategy(code, frame, request.params), request.params
    except StrategyCodeError as error:
        raise HTTPException(400, str(error)) from error


def _points(series: pd.Series) -> list[dict]:
    clean = series.dropna()
    return [{"time": d.strftime("%Y-%m-%d"), "value": round(float(v), 4)} for d, v in clean.items()]
