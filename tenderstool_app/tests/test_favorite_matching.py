import pytest

from app.services import parsing


def test_parse_favorites_from_real_page(fixture_html):
    html = fixture_html("licitaciones_search_with_favorites.html")
    favorites = parsing.parse_favorites(html)
    assert ("1518", "SAP > 1M") in favorites
    assert ("1523", "Software Gestión > 1M") in favorites


def test_find_favorite_id_exact_match():
    favorites = [("1518", "SAP > 1M"), ("1523", "Software Gestión > 1M")]
    assert parsing.find_favorite_id(favorites, "SAP > 1M") == "1518"


def test_find_favorite_id_is_case_and_whitespace_insensitive():
    favorites = [("1518", "SAP > 1M")]
    assert parsing.find_favorite_id(favorites, "  sap > 1m  ") == "1518"


def test_find_favorite_id_not_found_raises():
    favorites = [("1518", "SAP > 1M")]
    with pytest.raises(parsing.FavoriteNotFoundError):
        parsing.find_favorite_id(favorites, "No existe")


def test_find_favorite_id_rejects_partial_match():
    favorites = [("1518", "SAP > 1M")]
    with pytest.raises(parsing.FavoriteNotFoundError):
        parsing.find_favorite_id(favorites, "SAP")


def test_find_favorite_id_ambiguous_raises():
    favorites = [("1518", "SAP > 1M"), ("1600", "sap > 1m")]
    with pytest.raises(parsing.AmbiguousFavoriteError):
        parsing.find_favorite_id(favorites, "SAP > 1M")
