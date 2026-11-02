import pytest
from fastapi.testclient import TestClient

from stratlab.api import create_app
from stratlab.data.demo import generate_demo_bars
from stratlab.data.store import Store


@pytest.fixture
def bars():
    return generate_demo_bars("DEMO-TECH", days=600)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATLAB_HOME", str(tmp_path))
    store = Store(tmp_path / "test.db")
    yield TestClient(create_app(store))
    store.close()
