from app.services import parsing


def test_parse_detail_adjudicacion_has_all_expected_fields(fixture_html):
    html = fixture_html("adjudicacion_ficha.html")
    data = parsing.parse_detail(html)
    assert data["numero_expediente"] == "MNTB008_20"
    assert data["estado"] == "Adjudicada"
    assert data["tipo_procedimiento"] == "Abierto"
    assert data["provincia"] == "Madrid"
    assert data["comunidad_autonoma"] == "Madrid, Comunidad de"
    assert "45 puntos" in data["criterios_adjudicacion"]


def test_parse_detail_licitacion_missing_fields_are_absent_not_invented(fixture_html):
    html = fixture_html("licitacion_ficha.html")
    data = parsing.parse_detail(html)
    # Una licitación no adjudicada no tiene "Estado" ni "Importe adjudicación
    # vs licitación" en esta ficha concreta: no deben aparecer inventados.
    assert "estado" not in data
    assert "importe_adjudicacion_vs_licitacion" not in data
    assert data["numero_expediente"] == "CSI2025005"
    assert data["tipo_procedimiento"] == "Simplificado"


def test_parse_detail_empty_html_returns_empty_dict():
    assert parsing.parse_detail("<html><body>vacío</body></html>") == {}


def test_parse_detail_unknown_label_is_ignored():
    html = """
    <div class="adjudicacion-dato">
      <div class="adjudicacion-dato-nombre">Campo inventado del futuro</div>
      <div class="adjudicacion-dato-valor">valor</div>
    </div>
    """
    assert parsing.parse_detail(html) == {}


def test_is_platinum_gated_detects_redirect_to_registro():
    assert parsing.is_platinum_gated("https://www.adjudicacionestic.com/front/registro.php?error=5")
    assert not parsing.is_platinum_gated("https://www.adjudicacionestic.com/front/licitaciones-ficha.php?id=1")
