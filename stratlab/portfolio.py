import math

import numpy as np
import pandas as pd

from stratlab.backtest.metrics import historical_cvar, historical_var, parametric_var, performance_metrics
from stratlab.config import TRADING_DAYS


def aligned_returns(closes: dict[str, pd.Series]) -> pd.DataFrame:
    prices = pd.DataFrame(closes).dropna()
    if len(prices) < 30:
        raise ValueError("Pas assez de dates communes entre les actifs (minimum 30)")
    return prices.pct_change().dropna()


def analyze_portfolio(returns: pd.DataFrame, weights: dict[str, float] | None, samples: int = 3000) -> dict:
    symbols = list(returns.columns)
    vector = _normalize_weights(symbols, weights)
    portfolio_returns = returns @ vector
    mean = returns.mean().to_numpy() * TRADING_DAYS
    covariance = returns.cov().to_numpy() * TRADING_DAYS

    return {
        "symbols": symbols,
        "weights": dict(zip(symbols, vector.round(4).tolist())),
        "start": returns.index[0].strftime("%Y-%m-%d"),
        "end": returns.index[-1].strftime("%Y-%m-%d"),
        "metrics": performance_metrics(portfolio_returns),
        "risk": {
            "var_95_historical": historical_var(portfolio_returns, 0.95),
            "var_99_historical": historical_var(portfolio_returns, 0.99),
            "var_95_parametric": parametric_var(portfolio_returns, 0.95),
            "cvar_95": historical_cvar(portfolio_returns, 0.95),
            "risk_contribution": dict(zip(symbols, risk_contributions(vector, covariance).round(4).tolist())),
        },
        "assets": {symbol: performance_metrics(returns[symbol]) for symbol in symbols},
        "correlation": returns.corr().round(3).to_numpy().tolist(),
        "equity": [
            {"time": d.strftime("%Y-%m-%d"), "value": round(float(v), 6)}
            for d, v in (1 + portfolio_returns).cumprod().items()
        ],
        "frontier": efficient_frontier(mean, covariance, symbols, samples),
    }


def risk_contributions(weights: np.ndarray, covariance: np.ndarray) -> np.ndarray:
    variance = weights @ covariance @ weights
    if variance <= 0:
        return np.zeros_like(weights)
    return weights * (covariance @ weights) / variance


def efficient_frontier(mean: np.ndarray, covariance: np.ndarray, symbols: list[str], samples: int) -> dict:
    rng = np.random.default_rng(7)
    count = len(symbols)
    weights = rng.dirichlet(np.full(count, 0.6), size=samples)
    weights = np.vstack([weights, np.eye(count), np.full((1, count), 1 / count)])
    expected = weights @ mean
    volatility = np.sqrt(np.einsum("ij,jk,ik->i", weights, covariance, weights))
    sharpe = np.divide(expected, volatility, out=np.zeros_like(expected), where=volatility > 0)

    def describe(index: int) -> dict:
        return {
            "weights": dict(zip(symbols, weights[index].round(4).tolist())),
            "return": float(expected[index]),
            "volatility": float(volatility[index]),
            "sharpe": float(sharpe[index]),
        }

    step = max(1, len(weights) // 1500)
    return {
        "points": [
            {"return": float(r), "volatility": float(v), "sharpe": float(s)}
            for r, v, s in zip(expected[::step], volatility[::step], sharpe[::step])
        ],
        "max_sharpe": describe(int(np.argmax(sharpe))),
        "min_volatility": describe(int(np.argmin(volatility))),
        "assets": [
            {"symbol": s, "return": float(mean[i]), "volatility": float(math.sqrt(covariance[i, i]))}
            for i, s in enumerate(symbols)
        ],
    }


def _normalize_weights(symbols: list[str], weights: dict[str, float] | None) -> np.ndarray:
    if not weights:
        return np.full(len(symbols), 1 / len(symbols))
    vector = np.array([max(float(weights.get(symbol, 0.0)), 0.0) for symbol in symbols])
    total = vector.sum()
    if total <= 0:
        raise ValueError("La somme des poids doit être positive")
    return vector / total
