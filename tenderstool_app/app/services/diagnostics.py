"""Modo diagnóstico: logs de pasos, screenshots en error, y resolución de
headless según entorno. No registra nunca credenciales (ver README:
'Seguridad y logs').
"""
from __future__ import annotations

import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

DIAGNOSTICS_DIR = Path(__file__).resolve().parents[1] / "diagnostics"

logger = logging.getLogger("tenderstool")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def resolve_headless(diagnostic_mode: bool) -> bool:
    """En local con modo diagnóstico activado, navegador visible. En
    servidor sin display gráfico, headless siempre (evita romper el proceso
    intentando abrir una UI que no existe)."""
    if not diagnostic_mode:
        return True
    has_display = sys.platform == "win32" or bool(os.environ.get("DISPLAY"))
    return not has_display


class DiagnosticsLogger:
    """Acumula el log de pasos de una ejecución y, en modo diagnóstico,
    guarda capturas de pantalla ante errores en una carpeta propia por run.

    `on_step`, si se pasa, se invoca con cada línea de log (además de
    registrarla en el logger de proceso) — lo usa run_registry.py para
    alimentar la pantalla de progreso en vivo sin acoplar este módulo a
    ella directamente."""

    def __init__(
        self,
        diagnostic_mode: bool,
        run_id: str | None = None,
        on_step: Callable[[str], None] | None = None,
    ) -> None:
        self.diagnostic_mode = diagnostic_mode
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.on_step = on_step
        self.steps: list[str] = []
        self.run_dir: Path | None = None
        if diagnostic_mode:
            self.run_dir = DIAGNOSTICS_DIR / self.run_id
            self.run_dir.mkdir(parents=True, exist_ok=True)

    def step(self, message: str) -> None:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        entry = f"[{timestamp}] {message}"
        self.steps.append(entry)
        logger.info(entry)
        if self.on_step is not None:
            self.on_step(entry)

    async def error_screenshot(self, page, label: str) -> None:
        if not self.diagnostic_mode or self.run_dir is None:
            return
        try:
            path = self.run_dir / f"{label}_{uuid.uuid4().hex[:6]}.png"
            await page.screenshot(path=str(path), full_page=True)
            self.step(f"screenshot de diagnóstico guardado: {path.name}")
        except Exception as exc:  # noqa: BLE001 - un fallo al capturar no debe tumbar la extracción
            self.step(f"no se pudo guardar screenshot de diagnóstico: {exc}")
