"""Registro en memoria de ejecuciones en curso: progreso en vivo para la
pantalla de espera, y el guard de "una extracción a la vez" del MVP.

Todo vive en un único proceso/event loop (ver README: requiere un único
worker de uvicorn). Al ser un solo hilo de asyncio, no hace falta lock
adicional para las mutaciones del diccionario — solo para serializar el
"una extracción a la vez", que sí es una sección crítica real.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import asyncio

from .tenderstool_client import ExtractionResult


@dataclass
class RunState:
    steps: list[str] = field(default_factory=list)
    done: bool = False
    error: str | None = None
    error_status: int = 200
    result: ExtractionResult | None = None


_runs: dict[str, RunState] = {}
_extraction_lock = asyncio.Lock()


def create(run_id: str) -> None:
    _runs[run_id] = RunState()


def append_step(run_id: str, message: str) -> None:
    state = _runs.get(run_id)
    if state is not None:
        state.steps.append(message)


def finish_success(run_id: str, result: ExtractionResult) -> None:
    state = _runs.get(run_id)
    if state is not None:
        state.done = True
        state.result = result


def finish_error(run_id: str, message: str, status: int) -> None:
    state = _runs.get(run_id)
    if state is not None:
        state.done = True
        state.error = message
        state.error_status = status


def get(run_id: str) -> RunState | None:
    return _runs.get(run_id)


async def try_acquire() -> bool:
    """No bloqueante: intenta reservar el guard de "una extracción a la
    vez". Seguro sin lock adicional porque, bajo asyncio cooperativo, no
    hay ningún `await` entre la comprobación y la reserva — no puede colarse
    otra tarea en medio."""
    if _extraction_lock.locked():
        return False
    await _extraction_lock.acquire()
    return True


def release() -> None:
    if _extraction_lock.locked():
        _extraction_lock.release()
