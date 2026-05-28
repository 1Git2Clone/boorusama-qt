"""Headless CI smoke test.

Verifies that the built-in engines register and that the GUI modules import
under an offscreen Qt platform (no display needed). Run with::

    QT_QPA_PLATFORM=offscreen python scripts/ci_smoke.py
"""

import boorusama.app  # noqa: F401  (import-for-side-effect smoke check)
import boorusama.ui.main_window  # noqa: F401
from boorusama.core.registry import available_engines, load_builtin_engines

load_builtin_engines()
engines = set(available_engines())
assert {"danbooru", "gelbooru", "generic"} <= engines, engines
print("smoke OK:", sorted(engines))
