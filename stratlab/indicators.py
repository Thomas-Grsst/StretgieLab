import numpy as np
import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window, min_periods=window).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False, min_periods=window).mean()


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    gains = delta.clip(lower=0).ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    losses = (-delta.clip(upper=0)).ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    relative = gains / losses.replace(0, np.nan)
    result = 100 - 100 / (1 + relative)
    return result.where(losses != 0, 100.0).where(gains.notna())


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = ema(series, fast) - ema(series, slow)
    signal_line = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame({"macd": line, "signal": signal_line, "histogram": line - signal_line})


def bollinger(series: pd.Series, window: int = 20, width: float = 2.0) -> pd.DataFrame:
    middle = sma(series, window)
    deviation = series.rolling(window, min_periods=window).std()
    return pd.DataFrame({"middle": middle, "upper": middle + width * deviation, "lower": middle - width * deviation})


def atr(bars: pd.DataFrame, window: int = 14) -> pd.Series:
    previous_close = bars["close"].shift(1)
    true_range = pd.concat(
        [bars["high"] - bars["low"], (bars["high"] - previous_close).abs(), (bars["low"] - previous_close).abs()],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()


def momentum(series: pd.Series, window: int = 126) -> pd.Series:
    return series / series.shift(window) - 1


def donchian(bars: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    return pd.DataFrame({
        "upper": bars["high"].rolling(window, min_periods=window).max(),
        "lower": bars["low"].rolling(window, min_periods=window).min(),
    })
