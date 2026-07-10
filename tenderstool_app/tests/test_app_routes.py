from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_index_returns_form():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Ejecutar extracción" in resp.text


def test_ejecutar_missing_required_fields_returns_422():
    resp = client.post("/ejecutar", data={})
    assert resp.status_code == 422


def test_ejecutar_invalid_max_results_returns_400():
    resp = client.post(
        "/ejecutar",
        data={
            "username": "user@example.com",
            "password": "secret",  # pragma: allowlist secret
            "search_type": "licitaciones",
            "favorite_name": "SAP > 1M",
            "max_results": "no-es-un-numero",
        },
    )
    assert resp.status_code == 400
    assert "entero positivo" in resp.text


def test_descargar_rejects_path_traversal():
    resp = client.get("/descargar/..%2F..%2Fapp%2Fmain.py")
    assert resp.status_code == 404


def test_descargar_unknown_file_returns_404():
    resp = client.get("/descargar/no-existe.xlsx")
    assert resp.status_code == 404
