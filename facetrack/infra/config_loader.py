from __future__ import annotations

import importlib
import json
import os
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Optional

from facetrack.infra.errors import ErrorCode


@dataclass(frozen=True)
class LoadedConfig:
    """
    Wrapper for config values loaded from config.py and environment overrides.

    Values are exposed via `.values` (attribute-style access) for compatibility
    with the legacy pattern of global constants.
    """

    values: Any


def _env_key(name: str) -> str:
    return f"FACETRACK_{name}"


def _coerce(value: str) -> Any:
    """
    Best-effort coercion for env overrides.
    Supports JSON (lists/dicts), numbers, booleans, and strings.
    """
    v = value.strip()
    if not v:
        return v
    if v.lower() in {"true", "false"}:
        return v.lower() == "true"
    try:
        return json.loads(v)
    except Exception:
        pass
    try:
        if "." in v:
            return float(v)
        return int(v)
    except Exception:
        return v


def load_config(module_name: str = "config") -> LoadedConfig:
    """
    Load config values from `config.py` (module) and apply environment overrides.

    Environment overrides:
      FACETRACK_<NAME>=<value>
    where <value> can be JSON (recommended for lists), number, bool, or string.
    """
    try:
        mod = importlib.import_module(module_name)
    except Exception as e:
        raise RuntimeError(f"{ErrorCode.CONFIG_LOAD_FAIL}: cannot import {module_name}: {e}") from e

    # Pull UPPERCASE symbols only (treat them as config constants)
    base: dict[str, Any] = {
        k: getattr(mod, k)
        for k in dir(mod)
        if k.isupper() and not k.startswith("_")
    }

    # Apply env overrides (only for existing keys to avoid silent typos)
    for key in list(base.keys()):
        env = os.environ.get(_env_key(key))
        if env is None:
            continue
        base[key] = _coerce(env)

    return LoadedConfig(values=SimpleNamespace(**base))

