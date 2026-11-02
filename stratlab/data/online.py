import pandas as pd


class OnlineSourceUnavailable(RuntimeError):
    pass


def download_yahoo(symbol: str, period: str = "10y") -> pd.DataFrame:
    try:
        import yfinance
    except ImportError as error:
        raise OnlineSourceUnavailable(
            "Le téléchargement nécessite le module optionnel yfinance : pip install 'stratlab[online]'"
        ) from error
    try:
        raw = yfinance.Ticker(symbol).history(period=period, auto_adjust=True)
    except Exception as error:
        raise OnlineSourceUnavailable(f"Téléchargement impossible (hors ligne ?) : {error}") from error
    if raw.empty:
        raise OnlineSourceUnavailable(f"Aucune donnée renvoyée pour {symbol}")
    frame = raw.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
    frame.index = pd.to_datetime(frame.index).tz_localize(None).normalize()
    frame.index.name = "date"
    return frame
