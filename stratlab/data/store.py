import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

BAR_COLUMNS = ["open", "high", "low", "close", "volume"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bars (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (symbol, date)
);
CREATE TABLE IF NOT EXISTS symbols (
    symbol TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS strategies (
    name TEXT PRIMARY KEY,
    code TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: Path | str):
        self._path = str(path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def save_bars(self, symbol: str, bars: pd.DataFrame, source: str) -> int:
        symbol = normalize_symbol(symbol)
        frame = bars[BAR_COLUMNS].copy()
        frame.index = pd.to_datetime(frame.index).strftime("%Y-%m-%d")
        rows = [(symbol, date, *map(float, values)) for date, values in zip(frame.index, frame.to_numpy())]
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO bars (symbol, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            self._conn.execute(
                "INSERT OR REPLACE INTO symbols (symbol, source, updated_at) VALUES (?, ?, ?)",
                (symbol, source, _now()),
            )
            self._conn.commit()
        return len(rows)

    def load_bars(self, symbol: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
        query = "SELECT date, open, high, low, close, volume FROM bars WHERE symbol = ?"
        params: list[str] = [normalize_symbol(symbol)]
        if start:
            query += " AND date >= ?"
            params.append(start)
        if end:
            query += " AND date <= ?"
            params.append(end)
        query += " ORDER BY date"
        with self._lock:
            frame = pd.read_sql_query(query, self._conn, params=params)
        if frame.empty:
            raise KeyError(f"Aucune donnée pour {symbol}")
        frame["date"] = pd.to_datetime(frame["date"])
        return frame.set_index("date")

    def list_symbols(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT s.symbol, s.source, s.updated_at, COUNT(b.date), MIN(b.date), MAX(b.date)
                FROM symbols s LEFT JOIN bars b ON b.symbol = s.symbol
                GROUP BY s.symbol ORDER BY s.symbol
                """
            ).fetchall()
        keys = ["symbol", "source", "updated_at", "bars", "first_date", "last_date"]
        return [dict(zip(keys, row)) for row in rows]

    def delete_symbol(self, symbol: str) -> None:
        symbol = normalize_symbol(symbol)
        with self._lock:
            self._conn.execute("DELETE FROM bars WHERE symbol = ?", (symbol,))
            self._conn.execute("DELETE FROM symbols WHERE symbol = ?", (symbol,))
            self._conn.commit()

    def save_strategy(self, name: str, code: str, description: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO strategies (name, code, description, updated_at) VALUES (?, ?, ?, ?)",
                (name.strip(), code, description, _now()),
            )
            self._conn.commit()

    def list_strategies(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT name, code, description, updated_at FROM strategies ORDER BY name"
            ).fetchall()
        return [dict(zip(["name", "code", "description", "updated_at"], row)) for row in rows]

    def get_strategy(self, name: str) -> dict:
        for strategy in self.list_strategies():
            if strategy["name"] == name:
                return strategy
        raise KeyError(f"Stratégie inconnue : {name}")

    def delete_strategy(self, name: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM strategies WHERE name = ?", (name,))
            self._conn.commit()


def normalize_symbol(symbol: str) -> str:
    cleaned = symbol.strip().upper()
    if not cleaned:
        raise ValueError("Symbole vide")
    return cleaned


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
