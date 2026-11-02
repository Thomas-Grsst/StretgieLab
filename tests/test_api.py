def test_demo_data_is_seeded(client):
    symbols = {s["symbol"] for s in client.get("/api/symbols").json()}
    assert "DEMO-TECH" in symbols


def test_backtest_builtin(client):
    response = client.post("/api/backtest", json={"symbol": "DEMO-TECH", "strategy": "sma_cross", "params": {"fast": 10, "slow": 50}})
    assert response.status_code == 200
    body = response.json()
    assert body["params"] == {"fast": 10, "slow": 50}
    assert body["equity"] and "sharpe" in body["metrics"]


def test_backtest_rejects_unsafe_code(client):
    code = "import os\ndef generate_signals(df, params):\n    return df['close']"
    response = client.post("/api/backtest", json={"symbol": "DEMO-TECH", "strategy": "custom", "code": code})
    assert response.status_code == 400


def test_portfolio(client):
    response = client.post("/api/portfolio", json={"symbols": ["DEMO-TECH", "DEMO-BOND", "DEMO-GOLD"]})
    assert response.status_code == 200
    body = response.json()
    assert abs(sum(body["weights"].values()) - 1) < 1e-3
    assert body["frontier"]["max_sharpe"]["sharpe"] >= body["frontier"]["min_volatility"]["sharpe"] - 1e-9


def test_csv_import_and_bars(client):
    csv = b"Date,Open,High,Low,Close,Volume\n" + b"".join(
        f"2024-01-{d:02d},{100+d},{101+d},{99+d},{100.5+d},1000\n".encode() for d in range(1, 29)
    )
    response = client.post("/api/import/csv", data={"symbol": "test"}, files={"file": ("t.csv", csv, "text/csv")})
    assert response.json() == {"symbol": "TEST", "bars": 28}
    assert len(client.get("/api/bars/TEST").json()["candles"]) == 28


def test_save_strategy_and_unknown_symbol(client):
    code = "def generate_signals(df, params):\n    return (df['close'] > ind.sma(df['close'], 20)).astype(float)\n"
    assert client.post("/api/strategies", json={"name": "Trend", "code": code}).status_code == 200
    assert client.post("/api/backtest", json={"symbol": "DEMO-BANK", "strategy": "saved:Trend"}).status_code == 200
    assert client.get("/api/bars/UNKNOWN").status_code == 404


def test_assistant_status_offline(client, monkeypatch):
    body = client.get("/api/assistant/status").json()
    assert "available" in body
