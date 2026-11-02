import os
from pathlib import Path


def data_home() -> Path:
    root = Path(os.environ.get("STRATLAB_HOME", Path.home() / ".stratlab"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def database_path() -> Path:
    return data_home() / "stratlab.db"


OLLAMA_URL = os.environ.get("STRATLAB_OLLAMA_URL", "http://127.0.0.1:11434")
TRADING_DAYS = 252
