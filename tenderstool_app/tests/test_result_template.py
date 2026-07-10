from pathlib import Path

from starlette.requests import Request

from app.routes import templates
from app.services.tenderstool_client import ExtractionResult


def _fake_request() -> Request:
    scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    return Request(scope)


def _fake_result(**overrides) -> ExtractionResult:
    defaults = dict(
        search_type="licitaciones",
        favorite_name="SAP > 1M",
        max_results=None,
        processed_count=23,
        partial_error_count=0,
        duration_seconds=73.0,
        excel_path=Path("tenderstool_licitaciones_SAP_1M_20260710_111548.xlsx"),
        run_id="abc123",
    )
    defaults.update(overrides)
    return ExtractionResult(**defaults)


def test_result_page_renders_download_button_with_filename():
    response = templates.TemplateResponse(
        _fake_request(), "result.html", {"result": _fake_result()}
    )
    html = response.body.decode("utf-8")
    assert 'id="download-btn"' in html
    assert 'data-filename="tenderstool_licitaciones_SAP_1M_20260710_111548.xlsx"' in html
    assert "/static/download.js" in html


def test_result_page_shows_partial_error_count():
    response = templates.TemplateResponse(
        _fake_request(), "result.html", {"result": _fake_result(partial_error_count=2)}
    )
    html = response.body.decode("utf-8")
    assert "2" in html
