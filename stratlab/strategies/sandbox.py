import ast
import math
import multiprocessing
import queue

import numpy as np
import pandas as pd

from stratlab import indicators

ENTRYPOINT = "generate_signals"
TIMEOUT_SECONDS = 20

_FORBIDDEN_NAMES = {
    "open", "exec", "eval", "compile", "__import__", "globals", "locals", "vars", "getattr", "setattr",
    "delattr", "input", "breakpoint", "help", "exit", "quit", "memoryview", "type", "object", "super",
}
_SAFE_BUILTINS = {
    name: getattr(__builtins__, name) if not isinstance(__builtins__, dict) else __builtins__[name]
    for name in [
        "abs", "all", "any", "bool", "dict", "enumerate", "float", "int", "len", "list", "max", "min",
        "range", "round", "set", "sorted", "sum", "tuple", "zip", "isinstance", "map", "filter", "reversed",
        "ValueError", "KeyError", "Exception", "True", "False", "None", "print",
    ]
    if (name in __builtins__ if isinstance(__builtins__, dict) else hasattr(__builtins__, name))
}


class StrategyCodeError(ValueError):
    pass


def validate_code(code: str) -> None:
    try:
        tree = ast.parse(code)
    except SyntaxError as error:
        raise StrategyCodeError(f"Erreur de syntaxe ligne {error.lineno} : {error.msg}") from error
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise StrategyCodeError("Les imports sont interdits : pd, np et ind sont déjà disponibles")
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            raise StrategyCodeError("global/nonlocal sont interdits")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise StrategyCodeError(f"Accès interdit à l'attribut privé « {node.attr} »")
        if isinstance(node, ast.Name) and (node.id in _FORBIDDEN_NAMES or node.id.startswith("__")):
            raise StrategyCodeError(f"Nom interdit : « {node.id} »")
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith("__"):
            raise StrategyCodeError("Chaînes commençant par __ interdites")
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == ENTRYPOINT]
    if not functions:
        raise StrategyCodeError(f"Le code doit définir une fonction {ENTRYPOINT}(df, params)")


def _execute(code: str, bars: pd.DataFrame, params: dict) -> pd.Series:
    namespace = {"__builtins__": _SAFE_BUILTINS, "pd": pd, "np": np, "ind": indicators, "math": math}
    exec(compile(code, "<strategie>", "exec"), namespace)
    result = namespace[ENTRYPOINT](bars.copy(), dict(params))
    if isinstance(result, pd.DataFrame):
        raise StrategyCodeError("generate_signals doit renvoyer une Series, pas un DataFrame")
    if not isinstance(result, pd.Series):
        result = pd.Series(np.asarray(result, dtype=float), index=bars.index)
    return pd.to_numeric(result, errors="coerce")


def _worker(code: str, bars: pd.DataFrame, params: dict, results: multiprocessing.Queue) -> None:
    try:
        results.put(("ok", _execute(code, bars, params)))
    except Exception as error:
        results.put(("error", f"{type(error).__name__}: {error}"))


def run_custom_strategy(code: str, bars: pd.DataFrame, params: dict | None = None) -> pd.Series:
    validate_code(code)
    context = multiprocessing.get_context("spawn")
    results = context.Queue()
    process = context.Process(target=_worker, args=(code, bars, params or {}, results), daemon=True)
    process.start()
    try:
        status, payload = results.get(timeout=TIMEOUT_SECONDS)
    except queue.Empty as error:
        raise StrategyCodeError(f"La stratégie a dépassé {TIMEOUT_SECONDS} s d'exécution") from error
    finally:
        process.join(timeout=1)
        if process.is_alive():
            process.kill()
    if status == "error":
        raise StrategyCodeError(payload)
    return payload


STRATEGY_TEMPLATE = '''def generate_signals(df, params):
    """df : colonnes open, high, low, close, volume (index = dates).
    Renvoie une Series : 1 = long, 0 = neutre, -1 = short (si autorisé).
    Outils disponibles : pd, np, math, ind.sma / ema / rsi / macd / bollinger / atr / momentum / donchian."""
    fast = ind.ema(df["close"], 10)
    slow = ind.ema(df["close"], 50)
    trend_up = fast > slow
    calm = ind.atr(df, 14) / df["close"] < 0.03
    return (trend_up & calm).astype(float)
'''
