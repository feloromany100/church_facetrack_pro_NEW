from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from facetrack.infra.config_loader import LoadedConfig, load_config


@dataclass
class ConfigService:
    """
    Central access point for configuration.

    This service prevents deep modules from importing `config` directly by
    loading it once and passing `.values` via dependency injection.
    """

    _loaded: Optional[LoadedConfig] = None

    def load(self) -> Any:
        if self._loaded is None:
            self._loaded = load_config("config")
        return self._loaded.values

