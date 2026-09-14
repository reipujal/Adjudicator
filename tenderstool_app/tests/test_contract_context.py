from app.services import tenderstool_client


def test_infer_lot_context_from_title_description():
    assert (
        tenderstool_client._infer_lot_context(
            "Suministro de licencias. Lote 1: Renovacion SAP. Lote 2: Soporte"
        )
        == "Lote 1: Renovacion SAP"
    )


def test_infer_lot_context_from_expediente_suffix():
    assert tenderstool_client._infer_lot_context("Contrato sin lote en titulo", "AB/2026_lote3") == "Lote 3"


def test_build_contract_extraction_context_uses_row_and_fields():
    context = tenderstool_client._build_contract_extraction_context(
        {"titulo": "Acuerdo marco. Lote 2: Software tributario"},
        {"numero_expediente": "FELIB_lote2"},
    )

    assert context.title == "Acuerdo marco. Lote 2: Software tributario"
    assert context.expediente == "FELIB_lote2"
    assert context.lot == "Lote 2: Software tributario"
