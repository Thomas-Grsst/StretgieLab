import numpy as np
import pandas as pd

DEMO_ASSETS = {
    "DEMO-TECH": {"seed": 11, "drift": 0.14, "vol": 0.32, "start": 120.0},
    "DEMO-BANK": {"seed": 23, "drift": 0.06, "vol": 0.22, "start": 45.0},
    "DEMO-ENERGY": {"seed": 37, "drift": 0.04, "vol": 0.28, "start": 70.0},
    "DEMO-BOND": {"seed": 41, "drift": 0.025, "vol": 0.06, "start": 100.0},
    "DEMO-GOLD": {"seed": 53, "drift": 0.05, "vol": 0.15, "start": 1800.0},
}


def generate_demo_bars(symbol: str, days: int = 1500, end: str = "2026-10-30") -> pd.DataFrame:
    spec = DEMO_ASSETS[symbol]
    rng = np.random.default_rng(spec["seed"])
    dates = pd.bdate_range(end=end, periods=days)
    dt = 1 / 252
    regime = np.repeat(rng.choice([-1.0, 0.5, 1.0], size=days // 120 + 1, p=[0.25, 0.35, 0.4]), 120)[:days]
    drift = spec["drift"] * regime
    shocks = rng.standard_t(df=5, size=days) * np.sqrt(3 / 5)
    log_returns = (drift - 0.5 * spec["vol"] ** 2) * dt + spec["vol"] * np.sqrt(dt) * shocks
    close = spec["start"] * np.exp(np.cumsum(log_returns))
    open_ = np.concatenate([[spec["start"]], close[:-1]]) * np.exp(rng.normal(0, spec["vol"] * 0.15 * np.sqrt(dt), days))
    spread = np.abs(rng.normal(0, spec["vol"] * 0.6 * np.sqrt(dt), days))
    high = np.maximum(open_, close) * (1 + spread)
    low = np.minimum(open_, close) * (1 - spread)
    volume = rng.lognormal(mean=13, sigma=0.4, size=days).round()
    frame = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=dates)
    frame.index.name = "date"
    return frame.round(4)
