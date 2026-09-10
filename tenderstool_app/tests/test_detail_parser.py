from app.services import parsing


def test_parse_detail_adjudicacion_has_all_expected_fields(fixture_html):
    html = fixture_html("adjudicacion_ficha.html")
    data = parsing.parse_detail(html)
    assert data["numero_expediente"] == "MNTB008_20"
    assert "estado" not in data
    assert data["tipo_procedimiento"] == "Abierto"
    assert data["provincia"] == "Madrid"
    assert data["comunidad_autonoma"] == "Madrid, Comunidad de"
    assert "45 puntos" in data["criterios_adjudicacion"]
    assert data["organismo_licitador"] == "FUNDACIÓN COLECCIÓN THYSSEN BORNEMISZA"
    assert data["fecha_adjudicacion"] == "2020-07-16"
    assert data["fecha_vencimiento"] == "2021-07-16"
    assert data["importe_adjudicacion_vs_licitacion"] == "-27,87%"
    assert data["fuente_informacion"].startswith("https://contrataciondelestado.es/")


def test_parse_detail_licitacion_missing_fields_are_absent_not_invented(fixture_html):
    html = fixture_html("licitacion_ficha.html")
    data = parsing.parse_detail(html)
    # Una licitación no adjudicada no tiene "Importe adjudicación vs
    # licitación" en esta ficha concreta: no debe aparecer inventado.
    assert "importe_adjudicacion_vs_licitacion" not in data
    assert data["numero_expediente"] == "CSI2025005"
    assert data["tipo_procedimiento"] == "Simplificado"
    assert data["organismo_licitador"] == "CONSORCIO SANITARIO INTEGRAL"
    assert data["limite_ofertas"] == "2025-02-24"
    assert data["fuente_informacion"] == "https://contractaciopublica.cat/ca/detall-publicacio/300370218"


def test_parse_detail_organismo_licitador_absent_when_not_present():
    html = "<html><body><div class='adj-header-1'>sin cabecera reconocible</div></body></html>"
    assert "organismo_licitador" not in parsing.parse_detail(html)


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


def test_parse_detail_ignores_contract_document_fields_when_present_in_html():
    html = """
    <div class="adjudicacion-dato">
      <div class="adjudicacion-dato-nombre">Duración del contrato</div>
      <div class="adjudicacion-dato-valor">24 meses</div>
    </div>
    <div class="adjudicacion-dato">
      <div class="adjudicacion-dato-nombre">Solvencia</div>
      <div class="adjudicacion-dato-valor">Ver pliego administrativo</div>
    </div>
    <div class="adjudicacion-dato">
      <div class="adjudicacion-dato-nombre">Prorrogable hasta</div>
      <div class="adjudicacion-dato-valor">31/12/2028</div>
    </div>
    """
    data = parsing.parse_detail(html)
    assert "duracion_contrato" not in data
    assert "solvencia" not in data
    assert "prorrogable_hasta" not in data


def test_parse_announcement_pdf_url_finds_licitacion_document(fixture_html):
    html = fixture_html("licitacion_ficha.html")
    assert parsing.parse_announcement_pdf_url(html).endswith("descarga-adjudicacion.php?tipo=ANUNCIO&id=151135")


def test_parse_contract_document_urls_prioritizes_announcement(fixture_html):
    html = fixture_html("licitacion_ficha.html")
    urls = parsing.parse_contract_document_urls(html)
    assert urls[0][0] == "anuncio_licitacion"
    assert urls[0][1].endswith("descarga-adjudicacion.php?tipo=ANUNCIO&id=151135")
    assert any(label == "clausulas_administrativas" for label, _ in urls)


def test_is_platinum_gated_detects_redirect_to_registro():
    assert parsing.is_platinum_gated("https://www.adjudicacionestic.com/front/registro.php?error=5")
    assert not parsing.is_platinum_gated("https://www.adjudicacionestic.com/front/licitaciones-ficha.php?id=1")
