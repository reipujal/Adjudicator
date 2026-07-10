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
    ("fecha", "Fecha"),
    ("fecha_normalizada", "Fecha (YYYY-MM-DD)"),
    ("limite_ofertas", "Límite ofertas / Fecha adjudicación"),
    ("fecha_vencimiento", "Fecha de vencimiento"),
    ("prorrogable_hasta", "Prorrogable hasta"),
    ("titulo", "Título"),
    ("organismo_licitador", "Órgano de contratación (Organismo licitador)"),
    ("importe", "Importe"),
    ("importe_licitacion", "Importe licitación"),
    ("importe_adjudicacion_vs_licitacion", "Importe adjudicación vs licitación"),
    ("numero_expediente", "Número de expediente"),
    ("estado", "Estado"),
    ("tipo_procedimiento", "Tipo de procedimiento"),
    ("tipo_tramitacion", "Tipo de tramitación"),
    ("clasificacion_cpv", "Clasificación CPV"),
    ("mercado_vertical", "Mercado vertical"),
    ("provincia", "Provincia"),
    ("comunidad_autonoma", "Comunidad autónoma"),
    ("criterios_adjudicacion", "Criterios de adjudicación"),
    ("fuente_informacion", "Fuente de información"),
    ("detail_url", "URL del detalle"),
    ("extraido_en", "Fecha/hora de extracción"),
    ("estado_extraccion", "Estado de extracción del registro"),
    ("error_extraccion", "Mensaje de error del registro"),
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


def build_excel(rows: list[dict], search_type: str, favorite_name: str, output_dir: Path | None = None) -> Path:
    """Construye el .xlsx a partir de las filas ya extraídas. No falla si
    faltan campos: se rellenan como cadena vacía."""
    output_dir = output_dir or DOWNLOADS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    data = []
    for row in rows:
        record = {key: row.get(key, "") for key, _ in COLUMNS}
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
