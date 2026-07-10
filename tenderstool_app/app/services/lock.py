"""Guard de concurrencia para el MVP: una sola extracción a la vez por
proceso. Requiere que uvicorn se ejecute con un único worker (documentado en
el README) — un lock en memoria de proceso no protege frente a varios
workers/procesos.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager


class ExtractionInProgressError(Exception):
    pass


_lock = threading.Lock()


@contextmanager
def acquire_or_reject():
    if not _lock.acquire(blocking=False):
        raise ExtractionInProgressError("Ya hay una extracción en curso. Inténtalo de nuevo más tarde.")
    try:
        yield
    finally:
        _lock.release()
