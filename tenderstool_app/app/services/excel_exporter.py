"""Generación del Excel de salida: una fila por resultado, cabeceras claras,
fila de cabecera congelada, autofiltro, columnas ajustadas."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from openpyxl.utils import get_column_letter

DOWNLOADS_DIR = Path(__file__).resolve().parents[1] / "downloads"

# Orden y cabeceras finales del Excel. Las claves deben coincidir con las
# claves de los dicts de fila que construye tenderstool_client.run_extraction.
COLUMNS: list[tuple[str, str]] = [
    ("tipo_busqueda", "Tipo de búsqueda"),
    ("favorito", "Favorito usado"),
    ("limite_ofertas", "Límite ofertas / Fecha adjudicación"),
    ("fecha_inicio_contrato", "Fecha inicio contrato"),
    ("fecha_fin_contrato", "Fecha fin contrato"),
    ("fecha_vencimiento", "Fecha de vencimiento"),
    ("prorrogable_hasta", "Prorrogable hasta"),
    ("titulo", "Título"),
    ("tecnologia", "Tecnología"),
    ("organismo_licitador", "Órgano de contratación (Organismo licitador)"),
    ("importe", "Importe"),
    ("importe_adjudicacion_vs_licitacion", "Importe adjudicación vs licitación"),
    ("numero_expediente", "Número de expediente"),
    ("tipo_procedimiento", "Tipo de procedimiento"),
    ("provincia", "Provincia"),
    ("comunidad_autonoma", "Comunidad autónoma"),
    ("criterios_adjudicacion", "Criterios de adjudicación"),
    ("fuente_informacion", "Fuente de información"),
    ("duracion_contrato", "Duración del contrato"),
    ("numero_maximo_prorrogas", "Número máximo de prórrogas"),
    ("duracion_prorroga", "Duración prórroga"),
    ("solvencia", "Solvencia"),
    ("trazabilidad_fechas_contrato", "Trazabilidad fechas contrato"),
    ("trazabilidad_duracion_prorrogas", "Trazabilidad duración/prórrogas"),
    ("trazabilidad_solvencia", "Trazabilidad solvencia"),
    ("observaciones_ia", "Observaciones IA"),
]

_DATE_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")


def normalize_date(raw: str) -> str:
    """'DD/MM/YYYY...' -> 'YYYY-MM-DD'. Si no coincide el patrón, cadena vacía
    (nunca se inventa una fecha)."""
    if not raw:
        return ""
    match = _DATE_RE.search(raw)
    if not match:
        return ""
    day, month, year = match.groups()
    return f"{year}-{month}-{day}"


def normalize_favorite_for_filename(favorite_name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", favorite_name.strip())
    return slug.strip("_") or "favorito"


def build_filename(search_type: str, favorite_name: str, when: datetime | None = None) -> str:
    when = when or datetime.now(timezone.utc)
    timestamp = when.strftime("%Y%m%d_%H%M%S")
    favorito = normalize_favorite_for_filename(favorite_name)
    return f"tenderstool_{search_type}_{favorito}_{timestamp}.xlsx"


def _source(row: dict, prefix: str) -> str:
    document = row.get(f"{prefix}_documento")
    page = row.get(f"{prefix}_pagina")
    if document in ("", None) and page in ("", None):
        return ""
    if document not in ("", None) and page not in ("", None):
        return f"{document} p.{page}"
    return str(document or f"p.{page}")


def _trace_item(row: dict, label: str, prefix: str) -> str:
    source = _source(row, prefix)
    origin = row.get(f"{prefix}_origen")
    calculation = row.get(f"{prefix}_calculo")
    if not source and origin in ("", None, "null") and calculation in ("", None):
        return ""

    details = []
    if source:
        details.append(source)
    if origin not in ("", None, "null"):
        details.append(str(origin))
    if calculation:
        details.append(str(calculation))
    return f"{label}: {'; '.join(details)}"


def _join_trace(*items: str) -> str:
    return "\n".join(item for item in items if item)


def _compact_trace(row: dict) -> dict:
    record = dict(row)
    record["trazabilidad_fechas_contrato"] = _join_trace(
        _trace_item(row, "Inicio", "fecha_inicio"),
        _trace_item(row, "Fin", "fecha_fin"),
        _trace_item(row, "Vencimiento", "fecha_vencimiento"),
        _trace_item(row, "Prorrogable hasta", "prorrogable_hasta"),
    )
    record["trazabilidad_duracion_prorrogas"] = _join_trace(
        _trace_item(row, "Duración", "duracion_contrato"),
        _trace_item(row, "Número máximo de prórrogas", "numero_maximo_prorrogas"),
        _trace_item(row, "Duración prórroga", "duracion_prorroga"),
    )
    record["trazabilidad_solvencia"] = _trace_item(row, "Solvencia", "solvencia")
    record["observaciones_ia"] = _join_trace(
        str(row.get("fecha_fin_calculo", "") or ""),
        str(row.get("fecha_vencimiento_calculo", "") or ""),
        str(row.get("prorrogable_hasta_calculo", "") or ""),
    )
    return record


def build_excel(rows: list[dict], search_type: str, favorite_name: str, output_dir: Path | None = None) -> Path:
    """Construye el .xlsx a partir de las filas ya extraídas. No falla si
    faltan campos: se rellenan como cadena vacía."""
    output_dir = output_dir or DOWNLOADS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    data = []
    for row in rows:
        compact_row = _compact_trace(row)
        record = {key: compact_row.get(key, "") for key, _ in COLUMNS}
        data.append(record)

    df = pd.DataFrame(data, columns=[key for key, _ in COLUMNS])
    df.columns = [label for _, label in COLUMNS]

    filename = build_filename(search_type, favorite_name)
    path = output_dir / filename

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Resultados")
        worksheet = writer.sheets["Resultados"]
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions
        for i, (_, label) in enumerate(COLUMNS, start=1):
            max_len = max([len(label)] + [len(str(v)) for v in df[label].tolist()])
            worksheet.column_dimensions[get_column_letter(i)].width = min(max(max_len + 2, 10), 60)

    return path
