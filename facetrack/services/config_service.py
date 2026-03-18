from __future__ import annotations

import logging
import threading
from typing import Any, Callable, List, Optional

from facetrack.infra.config_loader import load_config

logger = logging.getLogger("ConfigService")

# ---------------------------------------------------------------------------
# Module-level singleton state (shared across ALL ConfigService() instances)
# ---------------------------------------------------------------------------
_lock: threading.Lock = threading.Lock()
_loaded: Optional[Any] = None          # SimpleNamespace of config values once loaded
_listeners: List[Callable[[Any], None]] = []


class ConfigService:
    """
    Central access point for application configuration.

    All instances share the same underlying module-level state, making this a
    true singleton regardless of how many times ``ConfigService()`` is called.

    Thread-safe: load(), subscribe(), and update_config() all acquire the
    module-level lock before touching shared state.

    Usage
    -----
        cfg = ConfigService().load()
        ConfigService().subscribe(my_callback)
        ConfigService().update_config({"BASE_SIMILARITY_THRESHOLD": 0.45})
    """

    # -- Read ------------------------------------------------------------------

    def load(self) -> Any:
        """Return the config SimpleNamespace, loading from config.py on first call."""
        global _loaded
        with _lock:
            if _loaded is None:
                _loaded = load_config("config").values
                logger.debug("Config loaded from config.py")
        return _loaded

    # -- Subscribe -------------------------------------------------------------

    def subscribe(self, callback: Callable[[Any], None]) -> None:
        """
        Register a callback invoked with the updated config namespace whenever
        update_config() makes a change.  Safe to call from any thread.
        Duplicate registrations are silently ignored.
        """
        with _lock:
            if callback not in _listeners:
                _listeners.append(callback)

    def unsubscribe(self, callback: Callable[[Any], None]) -> None:
        """Remove a previously registered callback.  No-op if not registered."""
        with _lock:
            try:
                _listeners.remove(callback)
            except ValueError:
                pass

    # -- Mutate ----------------------------------------------------------------

    def update_config(self, partial_dict: dict) -> None:
        """
        Update one or more config values at runtime and notify all subscribers.

        Only keys that already exist in the loaded config are accepted —
        unknown keys are logged as warnings and silently dropped to prevent
        typos from creating phantom config entries.

        Callbacks are fired **outside** the lock to prevent deadlocks.
        """
        global _loaded
        listeners_copy: List[Callable[[Any], None]] = []
        snapshot: Any = None

        with _lock:
            if _loaded is None:
                self.load()
            updated = False
            for key, value in partial_dict.items():
                if not hasattr(_loaded, key):
                    logger.warning("Config key %r not found in loaded config — ignored", key)
                    continue
                old = getattr(_loaded, key)
                if old != value:
                    setattr(_loaded, key, value)
                    updated = True
                    logger.info("Config updated: %s = %r  (was %r)", key, value, old)
            if updated:
                listeners_copy = list(_listeners)
                snapshot = _loaded

        # Fire callbacks outside the lock to prevent deadlocks
        for cb in listeners_copy:
            try:
                cb(snapshot)
            except Exception as exc:
                logger.error("Config subscriber raised an exception: %s", exc)
