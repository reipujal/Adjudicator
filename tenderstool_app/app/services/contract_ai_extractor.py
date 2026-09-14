"""Extraccion contractual semantica mediante IA.

La navegacion y descarga de documentos siguen siendo deterministas. Este modulo
solo interpreta el texto de los pliegos: recibe paginas, pregunta al modelo por
los campos que no vienen bien estructurados en la ficha y devuelve valores con
documento y pagina.
"""
from __future__ import annotations

import json
import os
import re
import hashlib
import threading
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=True)
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)

DEFAULT_MODEL = "gpt-5-mini"
DEFAULT_AI_TIMEOUT_SECONDS = 90
DEFAULT_AI_MAX_RETRIES = 2
AI_CACHE_VERSION = "contract-ai-v4"
CACHE_PATH = Path(__file__).resolve().parents[1] / "cache" / "contract_ai_cache.json"
_CACHE_LOCK = threading.Lock()
MAX_PAGE_CHARS = 6000
MAX_TOTAL_CHARS = 90000
MAX_SELECTED_PAGES = 24
FALLBACK_PAGES_PER_DOCUMENT = 18
FALLBACK_MAX_SELECTED_PAGES = 48
FALLBACK_FIELD_KEYS = {
    "duracion_contrato",
    "numero_maximo_prorrogas",
    "duracion_prorroga",
}

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

    resolved_model = model or os.getenv("TENDERSTOOL_AI_MODEL", DEFAULT_MODEL)
    prompt_pages = _build_prompt_pages(pages)
    response_data = _extract_response_with_cache(prompt_pages, model=resolved_model, api_key=api_key)
    if _needs_fallback_response(response_data):
        fallback_pages = _build_fallback_prompt_pages(pages)
        if fallback_pages and fallback_pages != prompt_pages:
            fallback_data = _extract_response_with_cache(
                "SEGUNDA PASADA: contexto ampliado para rellenar solo campos ausentes.\n\n" + fallback_pages,
                model=resolved_model,
                api_key=api_key,
            )
            response_data = _merge_missing_response_values(response_data, fallback_data)
    return _flatten_response(response_data)


def _build_prompt_pages(pages: list[DocumentPage]) -> str:
    return _format_prompt_pages(_select_relevant_pages(pages))


def _build_fallback_prompt_pages(pages: list[DocumentPage]) -> str:
    return _format_prompt_pages(_select_fallback_pages(pages))


def _format_prompt_pages(pages: list[DocumentPage]) -> str:
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


def _select_relevant_pages(pages: list[DocumentPage]) -> list[DocumentPage]:
    scored = [(index, _page_score(page), page) for index, page in enumerate(pages)]
    relevant = [(index, score, page) for index, score, page in scored if score > 0]
    if not relevant:
        return pages[:MAX_SELECTED_PAGES]
    selected = sorted(relevant, key=lambda item: (-item[1], item[0]))[:MAX_SELECTED_PAGES]
    return [page for _, _, page in sorted(selected, key=lambda item: item[0])]


def _select_fallback_pages(pages: list[DocumentPage]) -> list[DocumentPage]:
    counts_by_document: dict[str, int] = {}
    indexes: set[int] = set()
    for index, page in enumerate(pages):
        document_key = page.document_name or ""
        count = counts_by_document.get(document_key, 0)
        if count < FALLBACK_PAGES_PER_DOCUMENT:
            indexes.add(index)
        counts_by_document[document_key] = count + 1

    scored = [(index, _page_score(page), page) for index, page in enumerate(pages)]
    relevant = [(index, score, page) for index, score, page in scored if score > 0]
    for index, _score, _page in sorted(relevant, key=lambda item: (-item[1], item[0]))[:FALLBACK_MAX_SELECTED_PAGES]:
        indexes.add(index)

    selected = sorted(indexes)[:FALLBACK_MAX_SELECTED_PAGES]
    return [pages[index] for index in selected]


def _extract_response_with_cache(document_text: str, *, model: str, api_key: str) -> dict[str, Any]:
    cache_key = _cache_key(document_text, model)
    response_data = _read_cached_response(cache_key)
    if response_data is None:
        response_data = _call_model(
            document_text,
            model=model,
            api_key=api_key,
        )
        _write_cached_response(cache_key, response_data)
    return response_data


def _needs_fallback_response(response_data: dict[str, Any]) -> bool:
    for key in FALLBACK_FIELD_KEYS:
        value = response_data.get(key)
        if not isinstance(value, dict) or _is_empty(value.get("value")):
            return True
    return False


def _merge_missing_response_values(primary: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    merged = dict(primary)
    for key in FALLBACK_FIELD_KEYS:
        primary_value = primary.get(key)
        fallback_value = fallback.get(key)
        if not isinstance(fallback_value, dict):
            continue
        if not isinstance(primary_value, dict) or _is_empty(primary_value.get("value")):
            merged[key] = fallback_value
    return merged


def _is_empty(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def _page_score(page: DocumentPage) -> int:
    text = _ascii_lower(f"{page.document_name} {page.text}")
    score = 0
    for marker, weight in [
        ("duracion", 5),
        ("plazo", 5),
        ("vigencia", 4),
        ("inicio", 4),
        ("fecha de inicio", 6),
        ("prorroga", 5),
        ("vencimiento", 5),
        ("solvencia", 6),
        ("clausula", 2),
        ("apartado", 2),
    ]:
        if marker in text:
            score += weight
    return score


def _call_model(document_text: str, *, model: str, api_key: str) -> dict[str, Any]:
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise ContractAIUnavailableError("paquete openai no instalado") from exc

    client = OpenAI(
        api_key=api_key,
        timeout=_env_positive_int("TENDERSTOOL_AI_TIMEOUT_SECONDS", DEFAULT_AI_TIMEOUT_SECONDS),
        max_retries=_env_positive_int("TENDERSTOOL_AI_MAX_RETRIES", DEFAULT_AI_MAX_RETRIES),
    )
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


def _env_positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


def _ai_cache_enabled() -> bool:
    return os.getenv("TENDERSTOOL_AI_CACHE_ENABLED", "1").strip().casefold() not in {"0", "false", "no"}


def _cache_key(document_text: str, model: str) -> str:
    payload = json.dumps(
        {
            "version": AI_CACHE_VERSION,
            "model": model,
            "questions": QUESTIONS,
            "document_text": document_text,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_cached_response(cache_key: str) -> dict[str, Any] | None:
    if not _ai_cache_enabled():
        return None
    with _CACHE_LOCK:
        cache = _load_cache()
        value = cache.get(cache_key)
        return value if isinstance(value, dict) else None


def _write_cached_response(cache_key: str, response_data: dict[str, Any]) -> None:
    if not _ai_cache_enabled():
        return
    with _CACHE_LOCK:
        cache = _load_cache()
        cache[cache_key] = response_data
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = CACHE_PATH.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(cache, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        tmp_path.replace(CACHE_PATH)


def _load_cache() -> dict[str, Any]:
    if not CACHE_PATH.exists():
        return {}
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


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
        flattened[document_key] = _normalize_document_name(str(document))
        flattened[page_key] = page
        if calculation_key := CALCULATION_KEYS.get(field):
            if calculation := item.get("calculation"):
                flattened[calculation_key] = calculation
    _normalize_contract_values(flattened)
    _normalize_calculated_end_dates(flattened)
    return flattened


def _normalize_contract_values(fields: dict[str, Any]) -> None:
    if duration := _normalize_duration_label(fields.get("duracion_contrato", "")):
        fields["duracion_contrato"] = duration
    if duration := _normalize_duration_label(fields.get("duracion_prorroga", "")):
        fields["duracion_prorroga"] = duration
    if prorrogas := _normalize_extension_count(fields.get("numero_maximo_prorrogas", "")):
        fields["numero_maximo_prorrogas"] = prorrogas


def _normalize_duration_label(value: str) -> str:
    normalized = _ascii_lower(str(value))
    amount_match = re.search(r"\b(\d+)\s*(anos?|anys?|years?|mes(?:es)?|months?)\b", normalized)
    if not amount_match:
        words = {"un ano": "1 año", "una ano": "1 año", "un any": "1 año", "un mes": "1 mes"}
        return words.get(normalized, "")
    amount = int(amount_match.group(1))
    unit = amount_match.group(2)
    if unit.startswith(("ano", "any", "year")):
        return f"{amount} {'año' if amount == 1 else 'años'}"
    if amount % 12 == 0:
        years = amount // 12
        return f"{years} {'año' if years == 1 else 'años'}"
    return f"{amount} {'mes' if amount == 1 else 'meses'}"


def _normalize_extension_count(value: str) -> str:
    normalized = _ascii_lower(str(value))
    if normalized in {"no", "none", "null", "sin prorroga", "sin prorrogas", "no procede", "no aplica"}:
        return "0"
    match = re.search(r"\b(\d+)\b", normalized)
    if match and normalized == match.group(1):
        return match.group(1)
    return ""


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


def _normalize_document_name(value: str) -> str:
    document = value.strip().strip("[]")
    match = re.search(r"DOCUMENTO:\s*(.*?)(?:\s*\|\s*PAGINA:.*)?$", document, re.IGNORECASE)
    if match:
        document = match.group(1)
    document = re.sub(r"\s*\|\s*PAGINA:.*$", "", document, flags=re.IGNORECASE)
    return document.strip()


def _ascii_lower(value: str) -> str:
    text = (
        value.replace("\u00c3\u00b1", "n")
        .replace("\u00c3\u00b3", "o")
        .replace("\u00c3\u00a1", "a")
        .replace("\u00c3\u00a9", "e")
    )
    normalized = unicodedata.normalize("NFKD", text)
    return " ".join("".join(ch for ch in normalized if not unicodedata.combining(ch)).casefold().split())


def _parse_duration_label(value: str) -> tuple[int, str] | None:
    normalized = _ascii_lower(str(value))
    parts = normalized.split(" ")
    if len(parts) < 2 or not parts[0].isdigit():
        return None
    unit = parts[1]
    if unit.startswith("ano") or unit.startswith("año"):
        return int(parts[0]), "years"
    if unit.startswith("mes"):
        return int(parts[0]), "months"
    return None
