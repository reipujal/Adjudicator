"""Extraccion contractual semantica mediante IA.

La navegacion y descarga de documentos siguen siendo deterministas. Este modulo
solo interpreta el texto de los pliegos: recibe paginas, pregunta al modelo por
los campos que no vienen bien estructurados en la ficha y devuelve valores con
documento y pagina.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

DEFAULT_MODEL = "gpt-5-mini"
MAX_PAGE_CHARS = 6000
MAX_TOTAL_CHARS = 90000

FIELD_KEYS = [
    "fecha_inicio_contrato",
    "fecha_fin_contrato",
    "fecha_vencimiento",
    "prorrogable_hasta",
    "duracion_contrato",
    "numero_maximo_prorrogas",
    "duracion_prorroga",
    "solvencia",
]

ORIGIN_KEYS = {
    "fecha_inicio_contrato": "fecha_inicio_origen",
    "fecha_fin_contrato": "fecha_fin_origen",
    "fecha_vencimiento": "fecha_vencimiento_origen",
    "prorrogable_hasta": "prorrogable_hasta_origen",
}

CALCULATION_KEYS = {
    "fecha_fin_contrato": "fecha_fin_calculo",
    "fecha_vencimiento": "fecha_vencimiento_calculo",
    "prorrogable_hasta": "prorrogable_hasta_calculo",
}

PROVENANCE_KEYS = {
    "fecha_inicio_contrato": ("fecha_inicio_documento", "fecha_inicio_pagina"),
    "fecha_fin_contrato": ("fecha_fin_documento", "fecha_fin_pagina"),
    "fecha_vencimiento": ("fecha_vencimiento_documento", "fecha_vencimiento_pagina"),
    "prorrogable_hasta": ("prorrogable_hasta_documento", "prorrogable_hasta_pagina"),
    "duracion_contrato": ("duracion_contrato_documento", "duracion_contrato_pagina"),
    "numero_maximo_prorrogas": ("numero_maximo_prorrogas_documento", "numero_maximo_prorrogas_pagina"),
    "duracion_prorroga": ("duracion_prorroga_documento", "duracion_prorroga_pagina"),
    "solvencia": ("solvencia_documento", "solvencia_pagina"),
}

QUESTIONS = {
    "fecha_inicio_contrato": "Fecha de inicio del contrato o de la prestacion objeto del contrato.",
    "fecha_fin_contrato": "Fecha de fin de la duracion inicial del contrato, sin incluir prorrogas.",
    "fecha_vencimiento": "Fecha de vencimiento del contrato inicial, sin incluir prorrogas.",
    "prorrogable_hasta": "Fecha maxima hasta la que puede prorrogarse el contrato.",
    "duracion_contrato": "Duracion inicial del contrato.",
    "numero_maximo_prorrogas": "Numero maximo de prorrogas permitidas.",
    "duracion_prorroga": "Duracion de cada prorroga o del periodo de prorroga.",
    "solvencia": "Requisitos de solvencia economica, financiera, tecnica o profesional.",
}


@dataclass(frozen=True)
class DocumentPage:
    document_name: str
    page_number: int | None
    text: str


class ContractAIUnavailableError(Exception):
    pass


def extract_contract_fields_from_pages(
    pages: list[DocumentPage],
    *,
    model: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    if not pages:
        return {}
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ContractAIUnavailableError("OPENAI_API_KEY no configurada")

    response_data = _call_model(
        _build_prompt_pages(pages),
        model=model or os.getenv("TENDERSTOOL_AI_MODEL", DEFAULT_MODEL),
        api_key=api_key,
    )
    return _flatten_response(response_data)


def _build_prompt_pages(pages: list[DocumentPage]) -> str:
    chunks: list[str] = []
    total = 0
    for page in pages:
        text = " ".join(page.text.split())
        if not text:
            continue
        text = text[:MAX_PAGE_CHARS]
        header = f"[DOCUMENTO: {page.document_name} | PAGINA: {page.page_number or ''}]"
        chunk = f"{header}\n{text}"
        if total + len(chunk) > MAX_TOTAL_CHARS:
            break
        chunks.append(chunk)
        total += len(chunk)
    return "\n\n".join(chunks)


def _call_model(document_text: str, *, model: str, api_key: str) -> dict[str, Any]:
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise ContractAIUnavailableError("paquete openai no instalado") from exc

    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": (
                    "Eres un auditor de pliegos de contratacion publica. "
                    "Extraes datos solo si hay evidencia literal en el texto. "
                    "No infieras por fechas de publicacion, presentacion de ofertas, "
                    "apertura, formalizacion futura no fijada o conocimiento externo. "
                    "Si no hay evidencia clara, usa value=null. Devuelve fechas ISO YYYY-MM-DD. "
                    "Normaliza duraciones en espanol: '1 año', '3 años', '6 meses'. "
                    "Si hay fecha de inicio explicita y duracion inicial explicita, puedes calcular "
                    "la fecha de fin/vencimiento inicial: origin='calculated', document y page deben "
                    "apuntar a la evidencia usada, y calculation debe explicar el calculo."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Lee las paginas de documentos y responde a estas preguntas por campo:\n"
                    + "\n".join(f"- {key}: {question}" for key, question in QUESTIONS.items())
                    + "\n\nPara cada campo relleno debes indicar documento y pagina.\n\n"
                    + document_text
                ),
            },
        ],
        text={"format": _response_format()},
    )
    return json.loads(response.output_text)


def _response_format() -> dict[str, Any]:
    field_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "value": {"type": ["string", "null"]},
            "document": {"type": ["string", "null"]},
            "page": {"type": ["integer", "null"]},
            "origin": {"type": "string", "enum": ["explicit", "calculated", "null"]},
            "calculation": {"type": ["string", "null"]},
        },
        "required": ["value", "document", "page", "origin", "calculation"],
    }
    return {
        "type": "json_schema",
        "name": "contract_extraction",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {key: field_schema for key in FIELD_KEYS},
            "required": FIELD_KEYS,
        },
    }


def _flatten_response(data: dict[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for field in FIELD_KEYS:
        item = data.get(field) or {}
        value = item.get("value")
        document = item.get("document")
        page = item.get("page")
        origin = item.get("origin")
        if value in ("", None) or not document or page in ("", None):
            continue
        flattened[field] = value
        if origin_key := ORIGIN_KEYS.get(field):
            flattened[origin_key] = origin if origin in {"explicit", "calculated"} else "explicit"
        document_key, page_key = PROVENANCE_KEYS[field]
        flattened[document_key] = document
        flattened[page_key] = page
        if calculation_key := CALCULATION_KEYS.get(field):
            if calculation := item.get("calculation"):
                flattened[calculation_key] = calculation
    _normalize_calculated_end_dates(flattened)
    return flattened


def _normalize_calculated_end_dates(fields: dict[str, Any]) -> None:
    start = _parse_iso_date(fields.get("fecha_inicio_contrato", ""))
    duration = _parse_duration_label(fields.get("duracion_contrato", ""))
    if start is None or duration is None:
        return

    amount, unit = duration
    if unit == "years":
        end = start + relativedelta(years=amount) - timedelta(days=1)
    else:
        end = start + relativedelta(months=amount) - timedelta(days=1)

    for field, origin_key, calculation_key in [
        ("fecha_fin_contrato", "fecha_fin_origen", "fecha_fin_calculo"),
        ("fecha_vencimiento", "fecha_vencimiento_origen", "fecha_vencimiento_calculo"),
    ]:
        if fields.get(field) and fields.get(origin_key) != "calculated":
            continue
        fields[field] = end.isoformat()
        fields[origin_key] = "calculated"
        fields[calculation_key] = (
            f"Calculado por la aplicación: fecha inicio {start.isoformat()} + "
            f"duración inicial {fields['duracion_contrato']} - 1 día."
        )
        for suffix in ("documento", "pagina"):
            source_key = f"duracion_contrato_{suffix}"
            target_key = f"{field.removesuffix('_contrato')}_{suffix}"
            if fields.get(source_key):
                fields[target_key] = fields[source_key]


def _parse_iso_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _parse_duration_label(value: str) -> tuple[int, str] | None:
    normalized = " ".join(str(value).casefold().split())
    parts = normalized.split(" ")
    if len(parts) < 2 or not parts[0].isdigit():
        return None
    unit = parts[1]
    if unit.startswith("año"):
        return int(parts[0]), "years"
    if unit.startswith("mes"):
        return int(parts[0]), "months"
    return None
