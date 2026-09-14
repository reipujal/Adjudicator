import asyncio

from app.services import tenderstool_client


def test_document_merge_keeps_first_document_priority():
    target = {
        "duracion_contrato": "4 años",
        "fecha_inicio_contrato": "2027-01-01",
        "fecha_inicio_origen": "explicit",
    }
    source = {
        "duracion_contrato": "2 años",
        "fecha_inicio_contrato": "2028-01-01",
        "fecha_inicio_origen": "explicit",
        "solvencia": "Clasificación empresarial grupo V",
    }

    tenderstool_client._merge_contract_fields_without_overwrite(target, source)

    assert target["duracion_contrato"] == "4 años"
    assert target["fecha_inicio_contrato"] == "2027-01-01"
    assert target["solvencia"] == "Clasificación empresarial grupo V"


def test_contract_document_merge_overrides_visible_html_contract_fields():
    target = {
        "fecha_fin_contrato": "2026-10-15",
        "fecha_fin_origen": "explicit",
        "numero_expediente": "EXP-1",
    }
    source = {
        "fecha_fin_contrato": "2030-12-31",
        "fecha_fin_origen": "explicit",
        "numero_expediente": "EXP-2",
    }

    tenderstool_client._merge_contract_fields_from_primary_source(target, source)

    assert target["fecha_fin_contrato"] == "2030-12-31"
    assert target["fecha_fin_origen"] == "explicit"
    assert target["numero_expediente"] == "EXP-1"


def test_document_download_retry_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("TENDERSTOOL_DOCUMENT_DOWNLOAD_RETRIES", "bad")
    assert tenderstool_client._env_positive_int("TENDERSTOOL_DOCUMENT_DOWNLOAD_RETRIES", 2) == 2

    monkeypatch.setenv("TENDERSTOOL_DOCUMENT_DOWNLOAD_RETRIES", "-1")
    assert tenderstool_client._env_positive_int("TENDERSTOOL_DOCUMENT_DOWNLOAD_RETRIES", 2) == 2

    monkeypatch.setenv("TENDERSTOOL_DOCUMENT_DOWNLOAD_RETRIES", "4")
    assert tenderstool_client._env_positive_int("TENDERSTOOL_DOCUMENT_DOWNLOAD_RETRIES", 2) == 4


async def test_document_text_cache_reuses_concurrent_same_url(monkeypatch):
    calls = 0

    async def fake_download(page, url, label, diag):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return tenderstool_client.DocumentText(text=f"text for {url}", pages=[f"text for {url}"])

    monkeypatch.setattr(tenderstool_client, "_download_document_text", fake_download)
    cache = tenderstool_client.DocumentTextCache(texts={}, in_flight={}, lock=asyncio.Lock())

    class DummyDiag:
        def step(self, message):
            pass

    first, second = await asyncio.gather(
        tenderstool_client._get_document_text(None, "https://example.test/doc.pdf", "anuncio", DummyDiag(), cache),
        tenderstool_client._get_document_text(None, "https://example.test/doc.pdf", "anuncio", DummyDiag(), cache),
    )

    assert first.text == "text for https://example.test/doc.pdf"
    assert second.text == first.text
    assert calls == 1
    assert cache.texts["https://example.test/doc.pdf"].text == first.text


async def test_truncated_pdf_download_returns_empty_document_after_retries(monkeypatch):
    monkeypatch.setenv("TENDERSTOOL_DOCUMENT_DOWNLOAD_RETRIES", "1")

    class FakeResponse:
        ok = True
        status = 200

        async def body(self):
            return b"%PDF-1.4\ntruncated body"

    class FakeRequest:
        def __init__(self):
            self.calls = 0

        async def get(self, url, timeout):
            self.calls += 1
            return FakeResponse()

    class FakePage:
        def __init__(self):
            self.request = FakeRequest()

    class DummyDiag:
        def __init__(self):
            self.steps = []

        def step(self, message):
            self.steps.append(message)

    page = FakePage()
    diag = DummyDiag()

    document = await tenderstool_client._download_document_text(
        page, "https://example.test/truncated.pdf", "anuncio_licitacion", diag
    )

    assert document == tenderstool_client.DocumentText(text="", pages=[])
    assert page.request.calls == 2
    assert any("reintento descarga documento contractual" in step for step in diag.steps)
    assert any("PDF incompleto o invalido" in step for step in diag.steps)


async def test_contract_fields_are_extracted_by_ai_with_document_pages(monkeypatch):
    async def fake_get_document_text(*args, **kwargs):
        return tenderstool_client.DocumentText(
            text="pagina 1\npagina 2",
            pages=["sin datos", "El contrato dura un año"],
        )

    def fake_ai_extract(pages):
        assert [page.document_name for page in pages] == ["Anuncio de licitación", "Anuncio de licitación"]
        assert [page.page_number for page in pages] == [1, 2]
        return {
            "duracion_contrato": "1 año",
            "duracion_contrato_documento": "Anuncio de licitación",
            "duracion_contrato_pagina": 2,
        }

    class DummyDiag:
        def step(self, message):
            pass

    monkeypatch.setattr(tenderstool_client, "_get_document_text", fake_get_document_text)
    monkeypatch.setattr(tenderstool_client.contract_ai_extractor, "extract_contract_fields_from_pages", fake_ai_extract)

    detail_html = """
    <html><body>
      <a href="doc.pdf">Anuncio de licitación</a>
    </body></html>
    """
    fields = await tenderstool_client.extract_contract_fields_from_documents(
        page=None,
        detail_html=detail_html,
        source_url="",
        reference_dates=[],
        diag=DummyDiag(),
    )

    assert fields["duracion_contrato"] == "1 año"
    assert fields["duracion_contrato_documento"] == "Anuncio de licitación"
    assert fields["duracion_contrato_pagina"] == 2
