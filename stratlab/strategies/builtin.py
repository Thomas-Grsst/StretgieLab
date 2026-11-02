from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from stratlab import indicators as ind


@dataclass(frozen=True)
class Parameter:
    name: str
    label: str
    default: float
    minimum: float
    maximum: float
    step: float = 1


@dataclass(frozen=True)
class BuiltinStrategy:
    key: str
    name: str
    description: str
    parameters: list[Parameter]
    generate: Callable[[pd.DataFrame, dict], pd.Series] = field(repr=False)


def _sma_cross(bars: pd.DataFrame, params: dict) -> pd.Series:
    fast = ind.sma(bars["close"], int(params["fast"]))
    slow = ind.sma(bars["close"], int(params["slow"]))
    return pd.Series(np.where(fast > slow, 1.0, -1.0), index=bars.index).where(slow.notna(), 0.0)


def _rsi_reversion(bars: pd.DataFrame, params: dict) -> pd.Series:
    rsi = ind.rsi(bars["close"], int(params["window"]))
    signal = pd.Series(np.nan, index=bars.index)
    signal[rsi < params["oversold"]] = 1.0
    signal[rsi > params["exit"]] = 0.0
    return signal.ffill().fillna(0.0)


def _bollinger_breakout(bars: pd.DataFrame, params: dict) -> pd.Series:
    bands = ind.bollinger(bars["close"], int(params["window"]), params["width"])
    signal = pd.Series(np.nan, index=bars.index)
    signal[bars["close"] > bands["upper"]] = 1.0
    signal[bars["close"] < bands["middle"]] = 0.0
    return signal.ffill().fillna(0.0)


def _macd_trend(bars: pd.DataFrame, params: dict) -> pd.Series:
    lines = ind.macd(bars["close"], int(params["fast"]), int(params["slow"]), int(params["signal"]))
    return pd.Series(np.where(lines["macd"] > lines["signal"], 1.0, -1.0), index=bars.index).where(
        lines["signal"].notna(), 0.0
    )


def _momentum(bars: pd.DataFrame, params: dict) -> pd.Series:
    score = ind.momentum(bars["close"], int(params["lookback"]))
    trend = ind.sma(bars["close"], int(params["trend"]))
    return ((score > params["threshold"] / 100) & (bars["close"] > trend)).astype(float)


def _donchian_breakout(bars: pd.DataFrame, params: dict) -> pd.Series:
    entry = ind.donchian(bars, int(params["entry"])).shift(1)
    exit_ = ind.donchian(bars, int(params["exit"])).shift(1)
    signal = pd.Series(np.nan, index=bars.index)
    signal[bars["close"] > entry["upper"]] = 1.0
    signal[bars["close"] < exit_["lower"]] = 0.0
    return signal.ffill().fillna(0.0)


BUILTIN_STRATEGIES: dict[str, BuiltinStrategy] = {
    strategy.key: strategy
    for strategy in [
        BuiltinStrategy(
            "sma_cross", "Croisement de moyennes mobiles",
            "Long quand la moyenne rapide passe au-dessus de la lente, short (si autorisé) sinon.",
            [Parameter("fast", "Moyenne rapide", 20, 2, 200), Parameter("slow", "Moyenne lente", 100, 5, 400)],
            _sma_cross,
        ),
        BuiltinStrategy(
            "rsi_reversion", "Retour à la moyenne RSI",
            "Achète en survente (RSI bas) et sort quand le RSI repasse au-dessus du seuil de sortie.",
            [
                Parameter("window", "Période RSI", 14, 2, 50),
                Parameter("oversold", "Seuil d'achat", 30, 5, 50),
                Parameter("exit", "Seuil de sortie", 55, 40, 95),
            ],
            _rsi_reversion,
        ),
        BuiltinStrategy(
            "bollinger_breakout", "Cassure de Bollinger",
            "Entre quand le cours casse la bande haute, sort sous la moyenne centrale.",
            [Parameter("window", "Période", 20, 5, 100), Parameter("width", "Largeur (écarts-types)", 2, 0.5, 4, 0.1)],
            _bollinger_breakout,
        ),
        BuiltinStrategy(
            "macd_trend", "Tendance MACD",
            "Long quand la ligne MACD est au-dessus de sa ligne de signal.",
            [
                Parameter("fast", "EMA rapide", 12, 2, 50),
                Parameter("slow", "EMA lente", 26, 5, 100),
                Parameter("signal", "Signal", 9, 2, 30),
            ],
            _macd_trend,
        ),
        BuiltinStrategy(
            "momentum", "Momentum filtré",
            "Long si la performance sur la période dépasse le seuil et que le cours est au-dessus de sa tendance.",
            [
                Parameter("lookback", "Période momentum", 126, 10, 300),
                Parameter("threshold", "Seuil (%)", 0, -20, 50, 0.5),
                Parameter("trend", "Moyenne de tendance", 200, 20, 400),
            ],
            _momentum,
        ),
        BuiltinStrategy(
            "donchian", "Canal de Donchian (Turtle)",
            "Achète la cassure du plus haut sur N jours, sort sous le plus bas sur M jours.",
            [Parameter("entry", "Canal d'entrée", 55, 5, 200), Parameter("exit", "Canal de sortie", 20, 3, 100)],
            _donchian_breakout,
        ),
    ]
}


def resolve_params(strategy: BuiltinStrategy, params: dict | None) -> dict:
    params = params or {}
    resolved = {}
    for parameter in strategy.parameters:
        value = float(params.get(parameter.name, parameter.default))
        resolved[parameter.name] = min(max(value, parameter.minimum), parameter.maximum)
    return resolved


def describe_builtins() -> list[dict]:
    return [
        {
            "key": s.key,
            "name": s.name,
            "description": s.description,
            "parameters": [p.__dict__ for p in s.parameters],
        }
        for s in BUILTIN_STRATEGIES.values()
    ]
