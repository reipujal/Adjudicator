from app.services import parsing


def test_parse_licitaciones_listing_returns_expected_row_count(fixture_html):
    html = fixture_html("licitaciones_listing.html")
    rows = parsing.parse_licitaciones_listing(html)
    assert len(rows) == 10


def test_parse_licitaciones_listing_first_row_fields(fixture_html):
    html = fixture_html("licitaciones_listing.html")
    rows = parsing.parse_licitaciones_listing(html)
    first = rows[0]
    assert first["fecha"] == "24/06/2026"
    assert first["detail_url"] == "licitaciones-ficha.php?id=194453"
    assert "Mantenimiento" in first["titulo"]
    # el breadcrumb de categoría/organismo no debe colarse en el título
    assert "»" not in first["titulo"]


def test_parse_licitaciones_listing_no_table_returns_empty_list():
    assert parsing.parse_licitaciones_listing("<html><body>sin tabla</body></html>") == []


def test_parse_vencimientos_listing_returns_expected_row_count(fixture_html):
    html = fixture_html("vencimientos_listing.html")
    rows = parsing.parse_vencimientos_listing(html)
    assert len(rows) == 10


def test_parse_vencimientos_listing_first_row_fields(fixture_html):
    html = fixture_html("vencimientos_listing.html")
    rows = parsing.parse_vencimientos_listing(html)
    first = rows[0]
    assert first["fecha_adjudicacion"] == "16/07/2020"
    assert first["fecha_vencimiento"] == "16/07/2021"
    assert first["prorrogable_hasta"] == "16/07/2026"
    assert first["detail_url"] == "adjudicaciones-ficha.php?id=57938"
    assert "»" not in first["titulo"]


def test_parse_vencimientos_listing_no_table_returns_empty_list():
    assert parsing.parse_vencimientos_listing("<html><body>sin tabla</body></html>") == []
