import pytest
from pydantic import ValidationError

from app.schemas import ExtractionRequest


def _base_kwargs(**overrides):
    kwargs = dict(
        username="user@example.com",
        password="secret123",  # pragma: allowlist secret
        search_type="licitaciones",
        favorite_name="SAP > 1M",
        max_results=None,
        diagnostic_mode=False,
    )
    kwargs.update(overrides)
    return kwargs


def test_happy_path_accepts_valid_request():
    req = ExtractionRequest(**_base_kwargs(max_results=50))
    assert req.max_results == 50
    assert req.search_type.value == "licitaciones"


def test_max_results_none_means_all_results():
    req = ExtractionRequest(**_base_kwargs(max_results=None))
    assert req.max_results is None


def test_max_results_zero_is_rejected():
    with pytest.raises(ValidationError):
        ExtractionRequest(**_base_kwargs(max_results=0))


def test_max_results_negative_is_rejected():
    with pytest.raises(ValidationError):
        ExtractionRequest(**_base_kwargs(max_results=-5))


def test_blank_favorite_name_is_rejected():
    with pytest.raises(ValidationError):
        ExtractionRequest(**_base_kwargs(favorite_name="   "))


def test_blank_username_is_rejected():
    with pytest.raises(ValidationError):
        ExtractionRequest(**_base_kwargs(username=""))


def test_invalid_search_type_is_rejected():
    with pytest.raises(ValidationError):
        ExtractionRequest(**_base_kwargs(search_type="no_existe"))
