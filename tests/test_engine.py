import numpy as np
import pandas as pd
import pytest

from stratlab import indicators as ind
from stratlab.backtest.engine import BacktestSettings, run_backtest
from stratlab.strategies.builtin import BUILTIN_STRATEGIES, resolve_params


def _bars(prices):
    index = pd.bdate_range("2024-01-01", periods=len(prices))
    close = pd.Series(prices, index=index, dtype=float)
    return pd.DataFrame({"open": close, "high": close, "low": close, "close": close, "volume": 1.0})


def test_always_long_without_costs_matches_buy_and_hold(bars):
    result = run_backtest(bars, pd.Series(1.0, index=bars.index), BacktestSettings(fee_bps=0, slippage_bps=0))
    expected = bars["close"].iloc[-1] / bars["close"].iloc[0] - 1
    assert result["metrics"]["total_return"] == pytest.approx(expected, rel=1e-9)


def test_signal_is_applied_on_next_bar_to_avoid_lookahead():
    bars = _bars([100, 110, 121, 100])
    signals = pd.Series([0, 1, 0, 0], index=bars.index, dtype=float)
    result = run_backtest(bars, signals, BacktestSettings(fee_bps=0, slippage_bps=0))
    assert result["metrics"]["total_return"] == pytest.approx(0.10)
    trade = result["trades"][0]
    assert trade["entry_price"] == 110 and trade["exit_price"] == 121
    assert trade["return"] == pytest.approx(0.10)


def test_costs_reduce_returns(bars):
    signals = BUILTIN_STRATEGIES["sma_cross"].generate(bars, {"fast": 10, "slow": 30})
    free = run_backtest(bars, signals, BacktestSettings(fee_bps=0, slippage_bps=0))
    paid = run_backtest(bars, signals, BacktestSettings(fee_bps=20, slippage_bps=5))
    assert paid["metrics"]["total_return"] < free["metrics"]["total_return"]


def test_shorts_are_clipped_when_not_allowed(bars):
    result = run_backtest(bars, pd.Series(-1.0, index=bars.index), BacktestSettings())
    assert all(point["value"] == 0 for point in result["position"])


@pytest.mark.parametrize("key", list(BUILTIN_STRATEGIES))
def test_builtin_strategies_produce_bounded_signals(bars, key):
    strategy = BUILTIN_STRATEGIES[key]
    signals = strategy.generate(bars, resolve_params(strategy, None))
    assert len(signals) == len(bars)
    assert signals.dropna().between(-1, 1).all()


def test_rsi_bounds(bars):
    values = ind.rsi(bars["close"]).dropna()
    assert values.between(0, 100).all()
    assert np.isclose(ind.rsi(pd.Series(np.arange(1.0, 60.0))).iloc[-1], 100)
