import pytest

from stratlab.data.csv_import import parse_ohlcv_csv
from stratlab.strategies.sandbox import STRATEGY_TEMPLATE, StrategyCodeError, run_custom_strategy, validate_code


@pytest.mark.parametrize(
    "code",
    [
        "import os\ndef generate_signals(df, params):\n    return df['close']",
        "def generate_signals(df, params):\n    return open('/etc/passwd')",
        "def generate_signals(df, params):\n    return df.__class__",
        "def other(df, params):\n    return df['close']",
    ],
)
def test_validation_rejects_unsafe_or_incomplete_code(code):
    with pytest.raises(StrategyCodeError):
        validate_code(code)


def test_template_runs_in_sandbox(bars):
    signals = run_custom_strategy(STRATEGY_TEMPLATE, bars)
    assert len(signals) == len(bars)
    assert set(signals.dropna().unique()) <= {0.0, 1.0}


def test_runtime_errors_are_reported(bars):
    with pytest.raises(StrategyCodeError, match="KeyError"):
        run_custom_strategy("def generate_signals(df, params):\n    return df['nope']", bars)


def test_csv_with_french_format():
    content = "Date;Ouverture;Plus haut;Plus bas;Clôture;Volume\n02/01/2024;10,5;11;10;10,8;1000\n03/01/2024;10,8;11,2;10,6;11;1200\n".encode()
    frame = parse_ohlcv_csv(content)
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert frame["close"].tolist() == [10.8, 11.0]


def test_csv_close_only():
    frame = parse_ohlcv_csv(b"date,close\n2024-01-02,100\n2024-01-03,101\n")
    assert frame["open"].tolist() == [100, 101]
