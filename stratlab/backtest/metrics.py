import math

import numpy as np
import pandas as pd

from stratlab.config import TRADING_DAYS


def performance_metrics(returns: pd.Series, risk_free: float = 0.0) -> dict:
    returns = returns.dropna()
    if returns.empty:
        return {}
    equity = (1 + returns).cumprod()
    years = len(returns) / TRADING_DAYS
    total_return = float(equity.iloc[-1] - 1)
    cagr = float(equity.iloc[-1] ** (1 / years) - 1) if years > 0 and equity.iloc[-1] > 0 else -1.0
    excess = returns - risk_free / TRADING_DAYS
    volatility = float(returns.std(ddof=1) * math.sqrt(TRADING_DAYS))
    downside = returns[returns < 0].std(ddof=1) * math.sqrt(TRADING_DAYS)
    drawdown = equity / equity.cummax() - 1
    max_drawdown = float(drawdown.min())
    return {
        "total_return": total_return,
        "cagr": cagr,
        "volatility": volatility,
        "sharpe": _safe_ratio(excess.mean() * TRADING_DAYS, volatility),
        "sortino": _safe_ratio(excess.mean() * TRADING_DAYS, downside),
        "max_drawdown": max_drawdown,
        "calmar": _safe_ratio(cagr, abs(max_drawdown)),
        "max_drawdown_days": longest_drawdown_days(drawdown),
        "var_95": historical_var(returns, 0.95),
        "cvar_95": historical_cvar(returns, 0.95),
        "best_day": float(returns.max()),
        "worst_day": float(returns.min()),
    }


def historical_var(returns: pd.Series, confidence: float) -> float:
    return float(-np.quantile(returns.dropna(), 1 - confidence))


def historical_cvar(returns: pd.Series, confidence: float) -> float:
    clean = returns.dropna()
    threshold = np.quantile(clean, 1 - confidence)
    tail = clean[clean <= threshold]
    return float(-tail.mean()) if len(tail) else 0.0


def parametric_var(returns: pd.Series, confidence: float) -> float:
    z_scores = {0.90: 1.2816, 0.95: 1.6449, 0.99: 2.3263}
    z = z_scores.get(round(confidence, 2), 1.6449)
    return float(z * returns.std(ddof=1) - returns.mean())


def longest_drawdown_days(drawdown: pd.Series) -> int:
    longest = current = 0
    for underwater in (drawdown < 0).to_numpy():
        current = current + 1 if underwater else 0
        longest = max(longest, current)
    return int(longest)


def trade_metrics(trades: list[dict]) -> dict:
    if not trades:
        return {"trades": 0, "win_rate": None, "profit_factor": None, "avg_trade": None, "avg_bars_held": None}
    results = np.array([trade["return"] for trade in trades])
    gains = results[results > 0].sum()
    losses = -results[results < 0].sum()
    return {
        "trades": len(trades),
        "win_rate": float((results > 0).mean()),
        "profit_factor": float(gains / losses) if losses > 0 else None,
        "avg_trade": float(results.mean()),
        "avg_bars_held": float(np.mean([trade["bars"] for trade in trades])),
    }


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    if denominator is None or not np.isfinite(denominator) or denominator == 0:
        return None
    return float(numerator / denominator)
