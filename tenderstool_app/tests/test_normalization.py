from app.services import excel_exporter, parsing


def test_normalize_favorite_name_trims_and_casefolds():
    assert parsing.normalize_favorite_name("  SAP > 1M  ") == "sap > 1m"


def test_normalize_favorite_name_collapses_internal_spaces():
    assert parsing.normalize_favorite_name("SAP   >   1M") == "sap > 1m"


def test_normalize_favorite_name_different_case_matches():
    assert parsing.normalize_favorite_name("sap > 1m") == parsing.normalize_favorite_name("SAP > 1M")


def test_infer_technology_detects_sap():
    assert parsing.infer_technology("Servicio de mantenimiento SAP") == "SAP"


def test_infer_technology_detects_salesforce_variants():
    assert parsing.infer_technology("Implantación SalesForce CRM") == "Salesforce"
    assert parsing.infer_technology("Servicios Sales Force") == "Salesforce"


def test_infer_technology_unknown_returns_empty():
    assert parsing.infer_technology("Servicio de mantenimiento") == ""


def test_infer_technology_uses_favorite_name():
    assert parsing.infer_technology("SAP > 1M", "Suministro sin marca en el título") == "SAP"


def test_infer_technology_detects_generic_categories():
    assert parsing.infer_technology("Servicios de ciberseguridad gestionada") == "Ciberseguridad"
    assert parsing.infer_technology("Suministro de electrolinera fotovoltaica 250 kWp") == "Energía solar"
    assert parsing.infer_technology("Centro de atención al usuario y soporte al puesto de trabajo") == "CAU"
    assert parsing.infer_technology("Servicios de telecomunicaciones corporativas") == "Telecomunicaciones"
    assert parsing.infer_technology("Adquisición de equipamiento de captación ligero") == "Audiovisual"
    assert parsing.infer_technology("Evolución y mantenimiento de frameworks corporativos") == "Software"
    assert parsing.infer_technology("Soporte de la oficina de entrega de valor VMO") == "Sistemas TI"


def test_infer_technology_detects_generic_software_terms():
    assert parsing.infer_technology("Software de gestion municipal en modalidad SaaS") == "Software"
    assert parsing.infer_technology("Sistema de informacion para salud publica") == "Software"
    assert parsing.infer_technology("Plataforma de gestion de contenidos y portales") == "Software"


def test_infer_technology_does_not_mark_hardware_workplace_as_cau():
    assert parsing.infer_technology("Adquisicion de equipamiento informatico de puesto de trabajo") == ""


def test_normalize_date_valid():
    assert excel_exporter.normalize_date("24/06/2026") == "2026-06-24"


def test_normalize_date_with_extra_text():
    assert excel_exporter.normalize_date("10/07/2026\n10:00h") == "2026-07-10"


def test_normalize_date_empty_returns_empty():
    assert excel_exporter.normalize_date("") == ""


def test_normalize_date_unparseable_returns_empty():
    assert excel_exporter.normalize_date("fecha no disponible") == ""


def test_normalize_favorite_for_filename_replaces_special_chars():
    assert excel_exporter.normalize_favorite_for_filename("SAP > 1M") == "SAP_1M"


def test_normalize_favorite_for_filename_empty_falls_back():
    assert excel_exporter.normalize_favorite_for_filename("   ") == "favorito"


def test_build_filename_pattern():
    import datetime

    when = datetime.datetime(2026, 7, 10, 10, 30, 0, tzinfo=datetime.timezone.utc)
    name = excel_exporter.build_filename("vencimientos", "SAP > 1M", when=when)
    assert name == "tenderstool_vencimientos_SAP_1M_20260710_103000.xlsx"
