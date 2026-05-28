"""Background work plumbing built on Qt's QThreadPool.

`QRunnable` cannot carry signals, so each task pairs a runnable with a small
`QObject` signal holder. `run_async` is the ergonomic entry point used across the
UI to push a blocking callable onto the global pool and get results back on the
main thread via signals.
"""

from __future__ import annotations

import traceback
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()


class Worker(QRunnable):
    """Runs ``fn(*args, **kwargs)`` on a pool thread and emits the outcome."""

    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self._cancelled = False
        # Critical: a Python QRunnable subclass must NOT be auto-deleted by the
        # thread pool. If Qt deletes the C++ object while the Python wrapper still
        # holds it, the interpreter double-frees it on GC ("free(): invalid size").
        # We manage lifetime ourselves via the registry in run_async().
        self.setAutoDelete(False)

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def _emit(self, signal, *args) -> None:
        # The signal holder can be torn down (rapid re-navigation, app shutdown)
        # while this runnable is still executing on a pool thread. Emitting into a
        # deleted C++ object raises RuntimeError; swallow it — there's no one left
        # to receive the result anyway.
        try:
            signal.emit(*args)
        except RuntimeError:
            pass

    @Slot()
    def run(self) -> None:
        if self._cancelled:
            self._emit(self.signals.finished)
            return
        try:
            value = self.fn(*self.args, **self.kwargs)
        except Exception as exc:  # noqa: BLE001 - surface any backend error to UI
            tb = traceback.format_exc()
            self._emit(self.signals.error, f"{exc}\n\n{tb}")
        else:
            if not self._cancelled:
                self._emit(self.signals.result, value)
        finally:
            self._emit(self.signals.finished)


# Keeps workers alive for the duration of their run. Because we disable
# auto-delete (see Worker.__init__), Python owns each Worker; without a strong
# reference here it could be garbage-collected mid-run. Entries are removed when
# the worker's `finished` signal fires on the main thread.
_active_workers: set["Worker"] = set()


def run_async(
    fn: Callable[..., Any],
    *args: Any,
    on_result: Callable[[Any], None] | None = None,
    on_error: Callable[[str], None] | None = None,
    on_finished: Callable[[], None] | None = None,
    **kwargs: Any,
) -> Worker:
    """Schedule *fn* on the global thread pool, wiring optional callbacks.

    Returns the :class:`Worker` so callers can :meth:`Worker.cancel` it.
    """
    worker = Worker(fn, *args, **kwargs)
    if on_result is not None:
        worker.signals.result.connect(on_result)
    if on_error is not None:
        worker.signals.error.connect(on_error)
    if on_finished is not None:
        worker.signals.finished.connect(on_finished)
    _active_workers.add(worker)
    worker.signals.finished.connect(lambda w=worker: _active_workers.discard(w))
    QThreadPool.globalInstance().start(worker)
    return worker
