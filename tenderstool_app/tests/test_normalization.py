from app.services import excel_exporter, parsing


def test_normalize_favorite_name_trims_and_casefolds():
    assert parsing.normalize_favorite_name("  SAP > 1M  ") == "sap > 1m"


def test_normalize_favorite_name_collapses_internal_spaces():
    assert parsing.normalize_favorite_name("SAP   >   1M") == "sap > 1m"


def test_normalize_favorite_name_different_case_matches():
    assert parsing.normalize_favorite_name("sap > 1m") == parsing.normalize_favorite_name("SAP > 1M")


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
