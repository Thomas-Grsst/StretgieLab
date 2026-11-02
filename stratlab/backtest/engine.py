from dataclasses import dataclass

import numpy as np
import pandas as pd

from stratlab.backtest.metrics import performance_metrics, trade_metrics


@dataclass(frozen=True)
class BacktestSettings:
    fee_bps: float = 5.0
    slippage_bps: float = 2.0
    allow_short: bool = False
    initial_capital: float = 10_000.0


def run_backtest(bars: pd.DataFrame, signals: pd.Series, settings: BacktestSettings) -> dict:
    target = _clean_signals(signals, bars.index, settings.allow_short)
    position = target.shift(1).fillna(0.0)
    asset_returns = bars["close"].pct_change().fillna(0.0)
    turnover = position.diff().abs().fillna(position.abs())
    costs = turnover * (settings.fee_bps + settings.slippage_bps) / 10_000
    strategy_returns = position * asset_returns - costs

    equity = settings.initial_capital * (1 + strategy_returns).cumprod()
    benchmark = settings.initial_capital * (1 + asset_returns).cumprod()
    drawdown = equity / equity.cummax() - 1
    trades = extract_trades(bars["close"], position, settings)

    metrics = performance_metrics(strategy_returns.iloc[1:])
    metrics.update(trade_metrics(trades))
    metrics["exposure"] = float((position != 0).mean())
    metrics["total_costs"] = float(costs.sum())
    benchmark_metrics = performance_metrics(asset_returns.iloc[1:])

    return {
        "metrics": metrics,
        "benchmark": benchmark_metrics,
        "equity": _series_points(equity),
        "benchmark_equity": _series_points(benchmark),
        "drawdown": _series_points(drawdown),
        "position": _series_points(position),
        "trades": trades,
        "monthly_returns": monthly_returns(strategy_returns),
    }


def _clean_signals(signals: pd.Series, index: pd.Index, allow_short: bool) -> pd.Series:
    if not isinstance(signals, pd.Series):
        signals = pd.Series(signals, index=index)
    cleaned = pd.to_numeric(signals.reindex(index), errors="coerce").ffill().fillna(0.0)
    lower = -1.0 if allow_short else 0.0
    return cleaned.clip(lower, 1.0).astype(float)


def extract_trades(close: pd.Series, position: pd.Series, settings: BacktestSettings) -> list[dict]:
    cost_rate = (settings.fee_bps + settings.slippage_bps) / 10_000
    trades = []
    current_side = 0.0
    entry_index = None
    values = position.to_numpy()
    prices = close.to_numpy()
    dates = close.index
    for i, side in enumerate(values):
        side = float(np.sign(side))
        if side == current_side:
            continue
        if current_side != 0 and entry_index is not None:
            trades.append(_trade(dates, prices, entry_index, i - 1, current_side, cost_rate))
        current_side = side
        entry_index = i if side != 0 else None
    if current_side != 0 and entry_index is not None:
        trade = _trade(dates, prices, entry_index, len(values) - 1, current_side, cost_rate)
        trade["open"] = True
        trades.append(trade)
    return trades


def _trade(dates, prices, entry: int, last_held: int, side: float, cost_rate: float) -> dict:
    entry_price = prices[entry - 1] if entry > 0 else prices[entry]
    exit_price = prices[last_held]
    gross = side * (exit_price / entry_price - 1)
    return {
        "side": "long" if side > 0 else "short",
        "entry_date": dates[max(entry - 1, 0)].strftime("%Y-%m-%d"),
        "exit_date": dates[last_held].strftime("%Y-%m-%d"),
        "entry_price": float(entry_price),
        "exit_price": float(exit_price),
        "return": float(gross - 2 * cost_rate),
        "bars": int(last_held - entry + 1),
        "open": False,
    }


def monthly_returns(returns: pd.Series) -> list[dict]:
    monthly = (1 + returns).resample("ME").prod() - 1
    return [{"year": int(d.year), "month": int(d.month), "return": float(v)} for d, v in monthly.items()]


def _series_points(series: pd.Series) -> list[dict]:
    clean = series.replace([np.inf, -np.inf], np.nan).dropna()
    return [{"time": d.strftime("%Y-%m-%d"), "value": round(float(v), 6)} for d, v in clean.items()]
