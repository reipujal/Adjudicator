import pytest

from app.services import contract_ai_extractor


def test_contract_ai_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(contract_ai_extractor.ContractAIUnavailableError):
        contract_ai_extractor.extract_contract_fields_from_pages(
            [contract_ai_extractor.DocumentPage("PCAP.pdf", 5, "El contrato dura un año")]
        )


def test_contract_ai_flatten_response_requires_document_and_page():
    data = {
        key: {"value": None, "document": None, "page": None, "origin": "null", "calculation": None}
        for key in contract_ai_extractor.FIELD_KEYS
    }
    data["fecha_inicio_contrato"] = {
        "value": "2027-01-01",
        "document": "PCAP.pdf",
        "page": 5,
        "origin": "explicit",
        "calculation": None,
    }
    data["fecha_fin_contrato"] = {
        "value": "2027-12-31",
        "document": "PCAP.pdf",
        "page": 5,
        "origin": "calculated",
        "calculation": "Inicio 2027-01-01 + duración inicial 1 año.",
    }
    data["duracion_contrato"] = {
        "value": "1 año",
        "document": "PCAP.pdf",
        "page": 5,
        "origin": "explicit",
        "calculation": None,
    }
    data["solvencia"] = {
        "value": "Ver cláusula 1.10",
        "document": "PCAP.pdf",
        "page": None,
        "origin": "explicit",
        "calculation": None,
    }

    flattened = contract_ai_extractor._flatten_response(data)

    assert flattened["fecha_inicio_contrato"] == "2027-01-01"
    assert flattened["fecha_inicio_origen"] == "explicit"
    assert flattened["fecha_inicio_documento"] == "PCAP.pdf"
    assert flattened["fecha_inicio_pagina"] == 5
    assert flattened["duracion_contrato"] == "1 año"
    assert flattened["duracion_contrato_documento"] == "PCAP.pdf"
    assert flattened["duracion_contrato_pagina"] == 5
    assert flattened["fecha_fin_origen"] == "calculated"
    assert flattened["fecha_fin_calculo"].startswith("Calculado por la aplicación")
    assert "solvencia" not in flattened


def test_contract_ai_recomputes_model_calculated_end_date():
    data = {
        key: {"value": None, "document": None, "page": None, "origin": "null", "calculation": None}
        for key in contract_ai_extractor.FIELD_KEYS
    }
    data["fecha_inicio_contrato"] = {
        "value": "2027-01-01",
        "document": "PCAP.pdf",
        "page": 5,
        "origin": "explicit",
        "calculation": None,
    }
    data["duracion_contrato"] = {
        "value": "1 año",
        "document": "PCAP.pdf",
        "page": 5,
        "origin": "explicit",
        "calculation": None,
    }
    data["fecha_fin_contrato"] = {
        "value": "2028-01-01",
        "document": "PCAP.pdf",
        "page": 5,
        "origin": "calculated",
        "calculation": "Modelo: suma un año.",
    }

    flattened = contract_ai_extractor._flatten_response(data)

    assert flattened["fecha_fin_contrato"] == "2027-12-31"
    assert flattened["fecha_fin_origen"] == "calculated"
    assert flattened["fecha_vencimiento"] == "2027-12-31"
    assert flattened["fecha_vencimiento_origen"] == "calculated"
    assert flattened["fecha_fin_documento"] == "PCAP.pdf"
    assert flattened["fecha_fin_pagina"] == 5


def test_contract_ai_normalizes_document_marker_returned_by_model():
    data = {
        key: {"value": None, "document": None, "page": None, "origin": "null", "calculation": None}
        for key in contract_ai_extractor.FIELD_KEYS
    }
    data["duracion_contrato"] = {
        "value": "2 anos",
        "document": "DOCUMENTO: Anuncio de licitacion | PAGINA: 4",
        "page": 4,
        "origin": "explicit",
        "calculation": None,
    }

    flattened = contract_ai_extractor._flatten_response(data)

    assert flattened["duracion_contrato_documento"] == "Anuncio de licitacion"
    assert flattened["duracion_contrato_pagina"] == 4


def test_contract_ai_timeout_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("TENDERSTOOL_AI_TIMEOUT_SECONDS", "nope")
    assert contract_ai_extractor._env_positive_int("TENDERSTOOL_AI_TIMEOUT_SECONDS", 90) == 90

    monkeypatch.setenv("TENDERSTOOL_AI_TIMEOUT_SECONDS", "0")
    assert contract_ai_extractor._env_positive_int("TENDERSTOOL_AI_TIMEOUT_SECONDS", 90) == 90

    monkeypatch.setenv("TENDERSTOOL_AI_TIMEOUT_SECONDS", "120")
    assert contract_ai_extractor._env_positive_int("TENDERSTOOL_AI_TIMEOUT_SECONDS", 90) == 120


def test_contract_ai_reuses_cached_model_response(monkeypatch, tmp_path):
    calls = 0
    cache_path = tmp_path / "contract_ai_cache.json"

    def fake_call_model(document_text, *, model, api_key):
        nonlocal calls
        calls += 1
        data = {
            key: {"value": None, "document": None, "page": None, "origin": "null", "calculation": None}
            for key in contract_ai_extractor.FIELD_KEYS
        }
        data["duracion_contrato"] = {
            "value": "1 año",
            "document": "PCAP.pdf",
            "page": 3,
            "origin": "explicit",
            "calculation": None,
        }
        data["numero_maximo_prorrogas"] = {
            "value": "0",
            "document": "PCAP.pdf",
            "page": 3,
            "origin": "explicit",
            "calculation": None,
        }
        data["duracion_prorroga"] = {
            "value": "0 meses",
            "document": "PCAP.pdf",
            "page": 3,
            "origin": "explicit",
            "calculation": None,
        }
        data["solvencia"] = {
            "value": "Solvencia",
            "document": "PCAP.pdf",
            "page": 3,
            "origin": "explicit",
            "calculation": None,
        }
        return data

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(contract_ai_extractor, "CACHE_PATH", cache_path)
    monkeypatch.setattr(contract_ai_extractor, "_call_model", fake_call_model)

    pages = [contract_ai_extractor.DocumentPage("PCAP.pdf", 3, "El contrato dura un año.")]

    first = contract_ai_extractor.extract_contract_fields_from_pages(pages, model="test-model")
    second = contract_ai_extractor.extract_contract_fields_from_pages(pages, model="test-model")

    assert first == second
    assert first["duracion_contrato"] == "1 año"
    assert calls == 1


def test_contract_ai_includes_lot_context_and_tracks_cache_stats(monkeypatch, tmp_path):
    seen_prompt = ""
    cache_path = tmp_path / "contract_ai_cache.json"
    stats = contract_ai_extractor.ExtractionStats()

    def fake_call_model(document_text, *, model, api_key):
        nonlocal seen_prompt
        seen_prompt = document_text
        data = {
            key: {"value": None, "document": None, "page": None, "origin": "null", "calculation": None}
            for key in contract_ai_extractor.FIELD_KEYS
        }
        data["duracion_contrato"] = {
            "value": "4 anos",
            "document": "PCAP.pdf",
            "page": 2,
            "origin": "explicit",
            "calculation": None,
        }
        data["numero_maximo_prorrogas"] = {
            "value": "0",
            "document": "PCAP.pdf",
            "page": 2,
            "origin": "explicit",
            "calculation": None,
        }
        data["duracion_prorroga"] = {
            "value": "0 meses",
            "document": "PCAP.pdf",
            "page": 2,
            "origin": "explicit",
            "calculation": None,
        }
        return data

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(contract_ai_extractor, "CACHE_PATH", cache_path)
    monkeypatch.setattr(contract_ai_extractor, "_call_model", fake_call_model)

    pages = [contract_ai_extractor.DocumentPage("PCAP.pdf", 2, "Duracion del lote 1: cuatro anos.")]
    context = contract_ai_extractor.ExtractionContext(
        title="Contrato marco. Lote 1: licencias SAP",
        expediente="AB/2026_lote1",
        lot="Lote 1: licencias SAP",
    )

    first = contract_ai_extractor.extract_contract_fields_from_pages(
        pages,
        model="test-model",
        context=context,
        stats=stats,
    )
    second = contract_ai_extractor.extract_contract_fields_from_pages(
        pages,
        model="test-model",
        context=context,
        stats=stats,
    )

    assert first == second
    assert "Lote objetivo: Lote 1: licencias SAP" in seen_prompt
    assert "responde solo para el lote objetivo" in seen_prompt
    assert stats.model_calls == 1
    assert stats.cache_hits == 1
    assert stats.cache_misses == 1
    assert stats.prompt_chars > 0


def test_contract_ai_normalizes_extensions_and_duration_labels():
    data = {
        key: {"value": None, "document": None, "page": None, "origin": "null", "calculation": None}
        for key in contract_ai_extractor.FIELD_KEYS
    }
    data["numero_maximo_prorrogas"] = {
        "value": "No",
        "document": "PCAP.pdf",
        "page": 4,
        "origin": "explicit",
        "calculation": None,
    }
    data["duracion_prorroga"] = {
        "value": "12 meses",
        "document": "PCAP.pdf",
        "page": 4,
        "origin": "explicit",
        "calculation": None,
    }

    flattened = contract_ai_extractor._flatten_response(data)

    assert flattened["numero_maximo_prorrogas"] == "0"
    assert flattened["duracion_prorroga"] == "1 año"


def test_contract_ai_selects_relevant_pages_before_prompt():
    pages = [
        contract_ai_extractor.DocumentPage("PPT.pdf", 1, "Arquitectura general sin datos contractuales."),
        contract_ai_extractor.DocumentPage("PCAP.pdf", 2, "Duracion del contrato y posible prorroga."),
        contract_ai_extractor.DocumentPage("PCAP.pdf", 3, "Solvencia economica y tecnica."),
        contract_ai_extractor.DocumentPage("PCAP.pdf", 4, "Anexo de personal asignado."),
    ]

    prompt = contract_ai_extractor._build_prompt_pages(pages)

    assert "PAGINA: 2" in prompt
    assert "PAGINA: 3" in prompt
    assert "PAGINA: 1" not in prompt
    assert "PAGINA: 4" not in prompt


def test_contract_ai_fallback_keeps_first_pages_for_each_document(monkeypatch):
    monkeypatch.setattr(contract_ai_extractor, "FALLBACK_PAGES_PER_DOCUMENT", 3)
    pages = [
        contract_ai_extractor.DocumentPage("Anuncio.pdf", 1, "Objeto del contrato."),
        contract_ai_extractor.DocumentPage("Anuncio.pdf", 2, "Presupuesto base."),
        contract_ai_extractor.DocumentPage("Anuncio.pdf", 3, "CPV."),
        contract_ai_extractor.DocumentPage("Anuncio.pdf", 4, "Mesa de contratacion."),
        contract_ai_extractor.DocumentPage("PCAP.pdf", 1, "Indice."),
        contract_ai_extractor.DocumentPage("PCAP.pdf", 2, "Cuadro de caracteristicas."),
        contract_ai_extractor.DocumentPage("PCAP.pdf", 3, "Condiciones generales."),
        contract_ai_extractor.DocumentPage("PCAP.pdf", 4, "Sin datos."),
    ]

    selected = contract_ai_extractor._select_fallback_pages(pages)

    assert [(page.document_name, page.page_number) for page in selected] == [
        ("Anuncio.pdf", 1),
        ("Anuncio.pdf", 2),
        ("Anuncio.pdf", 3),
        ("PCAP.pdf", 1),
        ("PCAP.pdf", 2),
        ("PCAP.pdf", 3),
    ]


def test_contract_ai_fallback_adds_relevant_pages(monkeypatch):
    monkeypatch.setattr(contract_ai_extractor, "FALLBACK_PAGES_PER_DOCUMENT", 0)
    pages = [
        contract_ai_extractor.DocumentPage("PCAP.pdf", 1, "Indice."),
        contract_ai_extractor.DocumentPage("PCAP.pdf", 2, "Contexto previo."),
        contract_ai_extractor.DocumentPage("PCAP.pdf", 3, "Duracion del contrato."),
        contract_ai_extractor.DocumentPage("PCAP.pdf", 4, "Contexto posterior."),
        contract_ai_extractor.DocumentPage("PCAP.pdf", 5, "Anexo."),
    ]

    selected = contract_ai_extractor._select_fallback_pages(pages)

    assert [page.page_number for page in selected] == [3]


def test_contract_ai_fallback_fills_only_missing_fields(monkeypatch, tmp_path):
    calls = 0
    cache_path = tmp_path / "contract_ai_cache.json"

    def empty_payload():
        return {
            key: {"value": None, "document": None, "page": None, "origin": "null", "calculation": None}
            for key in contract_ai_extractor.FIELD_KEYS
        }

    def fake_call_model(document_text, *, model, api_key):
        nonlocal calls
        calls += 1
        data = empty_payload()
        if "SEGUNDA PASADA" in document_text:
            data["duracion_contrato"] = {
                "value": "2 anos",
                "document": "PCAP.pdf",
                "page": 12,
                "origin": "explicit",
                "calculation": None,
            }
            data["numero_maximo_prorrogas"] = {
                "value": "1",
                "document": "PCAP.pdf",
                "page": 12,
                "origin": "explicit",
                "calculation": None,
            }
        else:
            data["solvencia"] = {
                "value": "Solvencia principal",
                "document": "PCAP.pdf",
                "page": 8,
                "origin": "explicit",
                "calculation": None,
            }
        return data

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(contract_ai_extractor, "CACHE_PATH", cache_path)
    monkeypatch.setattr(contract_ai_extractor, "_call_model", fake_call_model)
    monkeypatch.setattr(contract_ai_extractor, "_build_prompt_pages", lambda pages: "PROMPT PRINCIPAL")
    monkeypatch.setattr(
        contract_ai_extractor,
        "_build_fallback_prompt_pages",
        lambda pages: "PROMPT FALLBACK AMPLIO",
    )

    pages = [
        contract_ai_extractor.DocumentPage("PCAP.pdf", 8, "Solvencia economica."),
        contract_ai_extractor.DocumentPage("PCAP.pdf", 12, "Duracion del contrato dos anos y una prorroga."),
    ]

    flattened = contract_ai_extractor.extract_contract_fields_from_pages(pages, model="test-model")

    assert flattened["solvencia"] == "Solvencia principal"
    assert flattened["duracion_contrato"] == "2 años"
    assert flattened["numero_maximo_prorrogas"] == "1"
    assert calls == 2
