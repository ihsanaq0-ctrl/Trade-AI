"""
File-backed store for admin-added (custom) strategies + audit journal.

Custom strategies persist in backend/data/strategies.json so cards and
execution survive refreshes and restarts. Every add/remove is appended to
backend/data/admin_audit.json with a timestamp. Pasted code is trusted
(per project scope: no sandboxing).

Execution contract for pasted code (generic engine loop):
    from app.services.strategies.base import Signal

    class MyStrategy:
        async def analyze(self, pair, candles, config):
            # candles: list of {time, open, high, low, close, volume}
            # return Signal(action='buy'|'sell', pair, lot_size, stop_loss,
            #               take_profit, confidence, reason) or None
            return None

Optionally set STRATEGY_CLASS = MyStrategy in the pasted code to make class
discovery explicit.
"""

import json
import os
import re
import uuid
from datetime import datetime, timezone

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
)
STRATEGIES_FILE = os.path.join(DATA_DIR, "strategies.json")
AUDIT_FILE = os.path.join(DATA_DIR, "admin_audit.json")

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,49}$")
MAX_CODE_BYTES = 200 * 1024

BUILTIN_STRATEGIES = [
    {"name": "smart_money", "title": "Smart Money Mode", "risk": "Medium"},
    {"name": "mmc_mirror", "title": "MMC Mirror", "description": "50% equilibrium continuation strategy, XAUUSD M5", "risk": "Medium"},
    {"name": "classic", "title": "Classic Mode", "risk": "Low"},
    {"name": "full_confluence", "title": "Full Confluence", "risk": "Low"},
    {"name": "scalp_pyramid", "title": "Scalp Pyramid", "risk": "High"},
    {"name": "scalp_fvg", "title": "Scalp (FVG)", "risk": "High"},
    {"name": "signal_strength_hedge", "title": "Signal Strength Hedge", "risk": "High"},
    {"name": "nyao_scalper", "title": "Nyao Scalper (Trade Mgmt)", "risk": "Medium"},
    {"name": "trading_agents", "title": "TradingAgents AI", "description": "Multi-agent committee debate (Technical, Fundamental, Sentiment, Bull vs Bear, Risk Officer)", "risk": "Adaptive"},
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:

        import logging

        logging.getLogger(__name__).error(f"Error: {e}")

        return default

def _write_json(path, data):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _audit(action: str, strategy_id: str, strategy_name: str):
    entries = _read_json(AUDIT_FILE, [])
    entries.append({
        "id": str(uuid.uuid4()),
        "action": action,
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "created_at": _now(),
    })
    _write_json(AUDIT_FILE, entries)


# ---------------------------------------------------------------- queries

def list_custom() -> list:
    """Raw custom strategy entries (with code)."""
    return _read_json(STRATEGIES_FILE, [])


def list_all() -> list:
    """Built-ins + custom entries, shaped for the bots page cards."""
    out = []
    for b in BUILTIN_STRATEGIES:
        out.append({
            "name": b["name"], "title": b["title"], "risk": b["risk"],
            "description": b.get("description"),
            "source": "builtin",
        })
    for c in list_custom():
        out.append({
            "name": c["name"], "title": c["title"], "risk": "Custom",
            "source": "custom", "id": c["id"], "created_at": c["created_at"],
        })
    return out


def get_custom(name: str):
    return next((e for e in list_custom() if e["name"] == name), None)


def list_audit(limit: int = 200) -> list:
    entries = _read_json(AUDIT_FILE, [])
    return entries[-limit:][::-1]  # newest first


import ast
from app.services.strategies.base import Signal

FORBIDDEN_MODULES = {
    "os", "sys", "subprocess", "shutil", "socket", "urllib", "requests", "http",
    "ftplib", "builtins", "__builtin__", "importlib", "ctypes", "pty", "commands",
    "pickle", "shelve", "posix", "threading", "multiprocessing"
}

FORBIDDEN_CALLS = {
    "eval", "exec", "open", "compile", "__import__", "globals", "locals",
    "getattr", "setattr", "delattr", "system", "popen", "spawn"
}

ALLOWED_ROOT_MODULES = {
    "math", "numpy", "pandas", "typing", "datetime", "dataclasses",
    "json", "random", "scipy", "app"
}

SAFE_BUILTINS = {
    "abs": abs, "all": all, "any": any, "bin": bin, "bool": bool, "dict": dict,
    "enumerate": enumerate, "filter": filter, "float": float, "hex": hex,
    "int": int, "isinstance": isinstance, "issubclass": issubclass, "len": len,
    "list": list, "map": map, "max": max, "min": min, "oct": oct, "pow": pow,
    "range": range, "reversed": reversed, "round": round, "set": set,
    "sorted": sorted, "str": str, "sum": sum, "tuple": tuple, "zip": zip,
    "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError,
    "KeyError": KeyError, "IndexError": IndexError, "True": True, "False": False, "None": None,
}


def validate_strategy_ast(code: str) -> None:
    """Validate strategy code against malicious AST constructs and ensure class structure."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise ValueError(f"Strategy code has a syntax error: {e}")

    has_strategy_class = False

    for node in ast.walk(tree):
        # 1. Check imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_pkg = alias.name.split(".")[0]
                if root_pkg in FORBIDDEN_MODULES:
                    raise ValueError(f"Security error: Forbidden module import '{alias.name}'")
                if root_pkg not in ALLOWED_ROOT_MODULES:
                    raise ValueError(f"Security error: Module '{alias.name}' is not in allowed strategy libraries")
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root_pkg = node.module.split(".")[0]
                if root_pkg in FORBIDDEN_MODULES:
                    raise ValueError(f"Security error: Forbidden module import '{node.module}'")
                if root_pkg not in ALLOWED_ROOT_MODULES:
                    raise ValueError(f"Security error: Module '{node.module}' is not in allowed strategy libraries")

        # 2. Check forbidden calls
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
                raise ValueError(f"Security error: Call to forbidden function '{node.func.id}()' is prohibited")

        # 3. Check dunder attribute access
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                raise ValueError(f"Security error: Access to private attribute '{node.attr}' is prohibited")

        # 4. Check for strategy class with analyze or generate_signal
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name in ("analyze", "generate_signal"):
                    has_strategy_class = True

    if not has_strategy_class:
        raise ValueError("Strategy code must define a class with an 'analyze' or 'generate_signal' method")


# ---------------------------------------------------------------- mutations

def add_strategy(name: str, code: str, operator: str = "admin") -> dict:
    name = name.strip().lower()
    if not NAME_RE.match(name):
        raise ValueError(
            "Strategy name must start with a letter and contain only "
            "lowercase letters, numbers, underscores (2-50 chars)"
        )
    if not code or not code.strip():
        raise ValueError("Strategy code cannot be empty")
    if len(code.encode("utf-8")) > MAX_CODE_BYTES:
        raise ValueError("Strategy code is too large (max 200 KB)")
    if any(b["name"] == name for b in BUILTIN_STRATEGIES):
        raise ValueError(f"'{name}' is a built-in strategy and cannot be replaced")

    # Validate AST security constraints
    validate_strategy_ast(code)

    entries = list_custom()
    if any(e["name"] == name for e in entries):
        raise ValueError(f"Strategy '{name}' already exists")
    entry = {
        "id": str(uuid.uuid4()),
        "name": name,
        "title": name.replace("_", " ").title(),
        "code": code,
        "created_at": _now(),
        "updated_at": _now(),
    }
    entries.append(entry)
    _write_json(STRATEGIES_FILE, entries)
    _audit(f"add ({operator})", entry["id"], name)
    return entry


def remove_strategy(strategy_id: str) -> dict:
    entries = list_custom()
    entry = next((e for e in entries if e["id"] == strategy_id), None)
    if not entry:
        raise ValueError("Strategy not found")
    entries = [e for e in entries if e["id"] != strategy_id]
    _write_json(STRATEGIES_FILE, entries)
    _audit("remove", strategy_id, entry["name"])
    return entry


# ---------------------------------------------------------------- dynamic loading

def load_dynamic_class(name: str):
    """Load a custom strategy class from the store in a sandboxed namespace. None if absent/invalid."""
    entry = get_custom(name)
    if not entry:
        return None

    # Validate AST prior to execution
    try:
        validate_strategy_ast(entry["code"])
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Strategy validation failed for {name}: {e}")
        return None

    module_name = f"custom_strategy_{name}"
    namespace = {
        "__name__": module_name,
        "__file__": STRATEGIES_FILE,
        "__builtins__": SAFE_BUILTINS,
        "Signal": Signal,
    }

    try:
        compiled = compile(entry["code"], f"<strategy:{name}>", "exec")
        exec(compiled, namespace)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Execution error loading strategy {name}: {e}")
        return None

    cls = namespace.get("STRATEGY_CLASS")
    if cls is not None:
        return cls
    for value in namespace.values():
        if isinstance(value, type) and value.__module__ == module_name:
            if hasattr(value, "analyze") or hasattr(value, "generate_signal"):
                return value
    return None
