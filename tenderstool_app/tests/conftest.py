from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def fixture_html():
    def _load(name: str) -> str:
        return (FIXTURES_DIR / name).read_text(encoding="utf-8")

    return _load


@pytest.fixture(autouse=True)
def _reset_run_registry():
    """Estado global en memoria (run_registry): se limpia antes y después de
    cada test para que un fallo en un test no deje el lock de concurrencia
    colgado para el siguiente."""
    from app.services import run_registry

    def _clear():
        run_registry._runs.clear()
        if run_registry._extraction_lock.locked():
            run_registry._extraction_lock.release()

    _clear()
    yield
    _clear()
