import asyncio
import re
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services import tenderstool_client


def _fake_result(**overrides) -> tenderstool_client.ExtractionResult:
    defaults = dict(
        search_type="licitaciones",
        favorite_name="SAP > 1M",
        max_results=None,
        processed_count=2,
        partial_error_count=0,
        duration_seconds=1.2,
        excel_path=Path("fake_result.xlsx"),
        run_id="fake-run",
    )
    defaults.update(overrides)
    return tenderstool_client.ExtractionResult(**defaults)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _wait_until_done(client: AsyncClient, run_id: str, timeout: float = 2.0) -> dict:
    elapsed = 0.0
    while elapsed < timeout:
        resp = await client.get(f"/progreso/{run_id}")
        data = resp.json()
        if data.get("done"):
            return data
        await asyncio.sleep(0.01)
        elapsed += 0.01
    raise AssertionError(f"la ejecución {run_id} no terminó dentro del timeout de test")


async def test_favoritos_success_returns_list(mocker):
    async def fake_fetch(username, password, search_type):
        return ["SAP > 1M", "Software Gestión > 1M"]

    mocker.patch("app.services.tenderstool_client.fetch_favorites", side_effect=fake_fetch)

    async with _client() as client:
        resp = await client.post(
            "/favoritos",
            json={"username": "user@example.com", "password": "secret", "search_type": "licitaciones"},  # pragma: allowlist secret
        )

    assert resp.status_code == 200
    assert resp.json() == {"favorites": ["SAP > 1M", "Software Gestión > 1M"]}


async def test_favoritos_login_error_returns_401(mocker):
    async def fake_fetch(*args, **kwargs):
        raise tenderstool_client.LoginError("usr/pwd incorrectos")

    mocker.patch("app.services.tenderstool_client.fetch_favorites", side_effect=fake_fetch)

    async with _client() as client:
        resp = await client.post(
            "/favoritos",
            json={"username": "user@example.com", "password": "bad", "search_type": "licitaciones"},  # pragma: allowlist secret
        )

    assert resp.status_code == 401
    assert resp.json()["error"] == "usr/pwd incorrectos"


async def test_favoritos_blank_password_is_rejected_before_hitting_playwright(mocker):
    fetch_mock = mocker.patch("app.services.tenderstool_client.fetch_favorites")

    async with _client() as client:
        resp = await client.post(
            "/favoritos",
            json={"username": "user@example.com", "password": "  ", "search_type": "licitaciones"},
        )

    assert resp.status_code == 422
    fetch_mock.assert_not_called()


async def test_ejecutar_happy_path_reaches_result_via_progress(mocker):
    async def fake_run(params, run_id, on_step=None):
        if on_step:
            on_step("login correcto")
        return _fake_result(run_id=run_id)

    mocker.patch("app.services.tenderstool_client.run_extraction", side_effect=fake_run)

    async with _client() as client:
        resp = await client.post(
            "/ejecutar",
            data={
                "username": "user@example.com",
                "password": "secret",  # pragma: allowlist secret
                "search_type": "licitaciones",
                "favorite_name": "SAP > 1M",
            },
        )
        assert resp.status_code == 200
        assert "Extracción en curso" in resp.text

        run_id = re.search(r'data-run-id="([^"]+)"', resp.text).group(1)
        data = await _wait_until_done(client, run_id)
        assert data["done"] is True
        assert any("login correcto" in s for s in data["steps"])

        result_resp = await client.get(f"/resultado/{run_id}")

    assert result_resp.status_code == 200
    assert "Extracción completada" in result_resp.text
    assert "SAP &gt; 1M" in result_resp.text or "SAP > 1M" in result_resp.text


async def test_ejecutar_login_error_surfaces_on_resultado(mocker):
    async def fake_run(params, run_id, on_step=None):
        raise tenderstool_client.LoginError("usr/pwd incorrectos")

    mocker.patch("app.services.tenderstool_client.run_extraction", side_effect=fake_run)

    async with _client() as client:
        resp = await client.post(
            "/ejecutar",
            data={
                "username": "user@example.com",
                "password": "bad",  # pragma: allowlist secret
                "search_type": "licitaciones",
                "favorite_name": "SAP > 1M",
            },
        )
        run_id = re.search(r'data-run-id="([^"]+)"', resp.text).group(1)
        await _wait_until_done(client, run_id)

        result_resp = await client.get(f"/resultado/{run_id}")

    assert result_resp.status_code == 401
    assert "usr/pwd incorrectos" in result_resp.text


async def test_ejecutar_rejects_concurrent_second_run(mocker):
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_run(params, run_id, on_step=None):
        started.set()
        await release.wait()
        return _fake_result(run_id=run_id)

    mocker.patch("app.services.tenderstool_client.run_extraction", side_effect=fake_run)

    form_data = {
        "username": "user@example.com",
        "password": "secret",  # pragma: allowlist secret
        "search_type": "licitaciones",
        "favorite_name": "SAP > 1M",
    }

    async with _client() as client:
        resp1 = await client.post("/ejecutar", data=form_data)
        assert resp1.status_code == 200
        await asyncio.wait_for(started.wait(), timeout=2.0)

        resp2 = await client.post("/ejecutar", data=form_data)
        assert resp2.status_code == 409
        assert "Ya hay una extracción en curso" in resp2.text

        release.set()
        run_id = re.search(r'data-run-id="([^"]+)"', resp1.text).group(1)
        await _wait_until_done(client, run_id)


async def test_resultado_unknown_run_id_returns_404():
    async with _client() as client:
        resp = await client.get("/resultado/no-existe")
    assert resp.status_code == 404


async def test_progreso_unknown_run_id_returns_404():
    async with _client() as client:
        resp = await client.get("/progreso/no-existe")
    assert resp.status_code == 404
