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
