import io

import pandas as pd

_ALIASES = {
    "date": ["date", "datetime", "time", "timestamp", "jour"],
    "open": ["open", "ouverture", "o"],
    "high": ["high", "haut", "plus haut", "h"],
    "low": ["low", "bas", "plus bas", "l"],
    "close": ["close", "adj close", "adj_close", "cloture", "clôture", "dernier", "c", "price"],
    "volume": ["volume", "vol", "v"],
}


def parse_ohlcv_csv(content: bytes) -> pd.DataFrame:
    text = content.decode("utf-8-sig", errors="replace")
    separator = ";" if text.count(";") > text.count(",") else ","
    raw = pd.read_csv(io.StringIO(text), sep=separator)
    columns = _map_columns(raw.columns)
    if "date" not in columns or "close" not in columns:
        raise ValueError("Le CSV doit contenir au moins une colonne Date et une colonne Close")

    frame = pd.DataFrame(index=_parse_dates(raw[columns["date"]], european=separator == ";"))
    frame.index.name = "date"
    close = _to_number(raw[columns["close"]])
    frame["close"] = close.to_numpy()
    for field in ("open", "high", "low"):
        frame[field] = _to_number(raw[columns[field]]).to_numpy() if field in columns else close.to_numpy()
    frame["volume"] = _to_number(raw[columns["volume"]]).fillna(0).to_numpy() if "volume" in columns else 0.0

    frame = frame[frame.index.notna()].dropna(subset=["close"])
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    if frame.empty:
        raise ValueError("Aucune ligne exploitable dans le CSV")
    frame["high"] = frame[["open", "high", "low", "close"]].max(axis=1)
    frame["low"] = frame[["open", "high", "low", "close"]].min(axis=1)
    return frame[["open", "high", "low", "close", "volume"]]


def _map_columns(columns: pd.Index) -> dict[str, str]:
    lookup = {str(column).strip().lower(): column for column in columns}
    mapping = {}
    for field, aliases in _ALIASES.items():
        for alias in aliases:
            if alias in lookup:
                mapping[field] = lookup[alias]
                break
    return mapping


def _parse_dates(values: pd.Series, european: bool) -> pd.DatetimeIndex:
    text = values.astype(str).str.strip()
    parts = text.str.extract(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})")
    if parts[0].notna().all():
        first, second = parts[0].astype(int), parts[1].astype(int)
        day_first = (first > 12).any() or (european and not (second > 12).any())
        order = ["day", "month", "year"] if day_first else ["month", "day", "year"]
        components = pd.DataFrame({order[0]: first, order[1]: second, "year": parts[2].astype(int)})
        components.loc[components["year"] < 100, "year"] += 2000
        return pd.DatetimeIndex(pd.to_datetime(components[["year", "month", "day"]], errors="coerce"))
    return pd.DatetimeIndex(pd.to_datetime(text, errors="coerce", format="mixed"))


def _to_number(series: pd.Series) -> pd.Series:
    if not pd.api.types.is_numeric_dtype(series):
        series = series.astype(str).str.replace(" ", "", regex=False).str.replace(" ", "", regex=False)
        if series.str.contains(",").any() and not series.str.contains(r"\.").any():
            series = series.str.replace(",", ".", regex=False)
        else:
            series = series.str.replace(",", "", regex=False)
    return pd.to_numeric(series, errors="coerce")
