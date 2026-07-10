from __future__ import annotations

from pydantic import BaseModel, field_validator

from .services.selectors import SearchType


class ExtractionRequest(BaseModel):
    username: str
    password: str
    search_type: SearchType
    favorite_name: str
    max_results: int | None = None
    diagnostic_mode: bool = False

    @field_validator("username", "password", "favorite_name")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("no puede estar vacío")
        return value.strip()

    @field_validator("max_results")
    @classmethod
    def positive_int(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("debe ser un entero positivo")
        return value
