"""Chequeo de salud contra el sitio real: no se ejecuta por defecto (marcado
`integration`, excluido por pytest.ini). Requiere TENDERSTOOL_USER y
TENDERSTOOL_PASSWORD reales (los mismos del .env de la raíz del repo).

Ejecutar bajo demanda con:
    pytest -m integration

Si esto falla, el sitio probablemente ha cambiado de estructura — repetir
el proceso de inspección descrito en el README ("Si cambia la web de
TendersTool") antes de tocar nada más.
"""
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from app.services import selectors, tenderstool_client

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

pytestmark = pytest.mark.integration

requires_credentials = pytest.mark.skipif(
    not (os.environ.get("TENDERSTOOL_USER") and os.environ.get("TENDERSTOOL_PASSWORD")),
    reason="Requiere TENDERSTOOL_USER/TENDERSTOOL_PASSWORD reales en el entorno",
)


@requires_credentials
async def test_login_and_favorites_still_work_against_real_site():
    user = os.environ["TENDERSTOOL_USER"]
    password = os.environ["TENDERSTOOL_PASSWORD"]

    favorites = await tenderstool_client.fetch_favorites(
        user, password, selectors.SearchType.LICITACIONES
    )

    assert isinstance(favorites, list)
    assert len(favorites) > 0


@requires_credentials
async def test_favorites_also_work_for_vencimientos_module():
    user = os.environ["TENDERSTOOL_USER"]
    password = os.environ["TENDERSTOOL_PASSWORD"]

    favorites = await tenderstool_client.fetch_favorites(
        user, password, selectors.SearchType.VENCIMIENTOS
    )

    assert isinstance(favorites, list)
