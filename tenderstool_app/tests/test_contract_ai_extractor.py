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
