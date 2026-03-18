from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Callable, List
import threading

from facetrack.infra.config_loader import LoadedConfig, load_config
import logging

logger = logging.getLogger("ConfigService")


@dataclass
class ConfigService:
    """
    Central access point for configuration.

    This service prevents deep modules from importing `config` directly by
    loading it once and passing `.values` via dependency injection.
    """

    _loaded: Optional[LoadedConfig] = None
    _listeners: List[Callable[[Any], None]] = []
    _lock = threading.Lock()

    def load(self) -> Any:
        with self._lock:
            if self._loaded is None:
                self._loaded = load_config("config")
            return self._loaded.values

    def subscribe(self, callback: Callable[[Any], None]):
        """Register a callback to be invoked when config changes."""
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def update_config(self, partial_dict: dict):
        """Update runtime config values and notify all listeners."""
        with self._lock:
            if self._loaded is None:
                self.load()
            
            updated = False
            for key, value in partial_dict.items():
                if hasattr(self._loaded.values, key):
                    old_val = getattr(self._loaded.values, key)
                    if old_val != value:
                        setattr(self._loaded.values, key, value)
                        updated = True
                        logger.info(f"Config '{key}' updated: {old_val} -> {value}")
            
            if updated:
                # Notify listeners inside the lock or copy the list
                listeners_copy = list(self._listeners)
        
        # Fire callbacks outside the lock to prevent deadlocks
        if updated:
            for cb in listeners_copy:
                try:
                    cb(self._loaded.values)
                except Exception as e:
                    logger.error(f"Config listener callback failed: {e}")

