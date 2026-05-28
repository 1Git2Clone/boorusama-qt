"""Built-in booru engines. Importing this package registers them all.

To add a new booru, drop a module here that defines a ``BooruEngine`` subclass
decorated with ``@register_engine`` and import it below.
"""

from . import danbooru, gelbooru, generic  # noqa: F401

__all__ = ["danbooru", "gelbooru", "generic"]
