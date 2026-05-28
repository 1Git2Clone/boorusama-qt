"""Engine registry: discovers engine classes and instantiates configured sources.

New backends register themselves by subclassing :class:`BooruEngine` and calling
:func:`register_engine` (the :mod:`boorusama.engines` package does this on import).
This is what makes the app "pluggable": adding a booru is adding one module.
"""

from __future__ import annotations

from .engine import BooruEngine, EngineConfig

_ENGINES: dict[str, type[BooruEngine]] = {}


def register_engine(cls: type[BooruEngine]) -> type[BooruEngine]:
    """Class decorator / function to register an engine implementation."""
    if not cls.id:
        raise ValueError(f"Engine {cls.__name__} must define a non-empty `id`.")
    _ENGINES[cls.id] = cls
    return cls


def available_engines() -> dict[str, type[BooruEngine]]:
    return dict(_ENGINES)


def get_engine_class(engine_id: str) -> type[BooruEngine] | None:
    return _ENGINES.get(engine_id)


def create_engine(engine_id: str, config: EngineConfig) -> BooruEngine:
    cls = _ENGINES.get(engine_id)
    if cls is None:
        raise KeyError(f"Unknown engine id: {engine_id!r}")
    if not config.name:
        config.name = cls.display_name
    return cls(config)


def load_builtin_engines() -> None:
    """Import the engines package so its modules self-register."""
    from .. import engines  # noqa: F401  (import triggers registration)
