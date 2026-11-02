import json
import re
import urllib.error
import urllib.request

from stratlab.config import OLLAMA_URL
from stratlab.strategies.sandbox import STRATEGY_TEMPLATE

SYSTEM_PROMPT = f"""Tu es un assistant quantitatif intégré à StratégieLab, une application de backtest hors ligne.
Ta tâche : traduire la demande de l'utilisateur en une stratégie Python.

Règles strictes pour le code :
- Définis uniquement une fonction generate_signals(df, params).
- df est un DataFrame pandas indexé par date avec les colonnes open, high, low, close, volume.
- Renvoie une pandas Series alignée sur df.index : 1 = long, 0 = neutre, -1 = short.
- AUCUN import. Disponibles : pd, np, math, et ind (ind.sma(s, n), ind.ema(s, n), ind.rsi(s, n),
  ind.macd(s, fast, slow, signal) -> DataFrame[macd, signal, histogram], ind.bollinger(s, n, width) ->
  DataFrame[middle, upper, lower], ind.atr(df, n), ind.momentum(s, n), ind.donchian(df, n) -> DataFrame[upper, lower]).
- Pas de biais d'anticipation : n'utilise jamais de données futures (pas de shift négatif).
- Pas d'attributs commençant par _, pas de open/eval/exec.

Exemple :
```python
{STRATEGY_TEMPLATE}```

Réponds en français : une courte explication (3 phrases max), puis le code dans un unique bloc ```python."""


_LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class AssistantUnavailable(RuntimeError):
    pass


def ollama_status(base_url: str = OLLAMA_URL) -> dict:
    try:
        payload = _request(f"{base_url}/api/tags", None, timeout=2)
    except AssistantUnavailable as error:
        return {"available": False, "models": [], "error": str(error), "url": base_url}
    models = [model["name"] for model in payload.get("models", [])]
    return {"available": True, "models": models, "url": base_url}


def generate_strategy(prompt: str, model: str, previous_code: str | None = None, base_url: str = OLLAMA_URL) -> dict:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if previous_code:
        messages.append({"role": "user", "content": f"Code actuel de la stratégie :\n```python\n{previous_code}\n```"})
    messages.append({"role": "user", "content": prompt})
    payload = _request(
        f"{base_url}/api/chat",
        {"model": model, "messages": messages, "stream": False, "options": {"temperature": 0.2}},
        timeout=300,
    )
    content = payload.get("message", {}).get("content", "")
    return {"answer": content, "code": extract_code(content)}


def extract_code(content: str) -> str | None:
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", content, flags=re.DOTALL)
    for block in blocks:
        if "def generate_signals" in block:
            return block.strip() + "\n"
    return None


def _request(url: str, body: dict | None, timeout: float) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with _LOCAL_OPENER.open(request, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        raise AssistantUnavailable(f"Ollama a répondu {error.code} : {error.read().decode(errors='replace')}") from error
    except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
        raise AssistantUnavailable(f"Ollama injoignable sur {url} ({error})") from error
