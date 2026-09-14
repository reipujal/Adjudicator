"""Parsing puro de HTML de adjudicacionesTIC: sin Playwright, sin red.

Recibe HTML ya cargado (típicamente vía page.content()) y devuelve
estructuras de datos planas. Se puede testear directamente contra fixtures
reales sin necesidad de navegador ni mocks.
"""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from . import selectors

_ORGANISMO_LICITADOR_LABEL_RE = re.compile(r"Organismo licitador", re.IGNORECASE)
_DATE_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")


def normalize_date(raw: str) -> str:
    """Devuelve YYYY-MM-DD si el texto contiene una fecha DD/MM/YYYY fiable."""
    if not raw:
        return ""
    match = _DATE_RE.search(raw)
    if not match:
        return ""
    day, month, year = match.groups()
    return f"{year}-{month}-{day}"


def normalize_favorite_name(name: str) -> str:
    """Normaliza un nombre de favorito para comparación: minúsculas, sin
    espacios sobrantes al inicio/fin, espacios internos colapsados."""
    return " ".join(name.strip().split()).casefold()


def infer_technology(*values: str) -> str:
    raw_text = " ".join(value for value in values if value).casefold()
    text = "".join(
        ch for ch in unicodedata.normalize("NFKD", raw_text)
        if not unicodedata.combining(ch)
    )
    if re.search(r"\bsap\b", text, re.IGNORECASE):
        return "SAP"
    if re.search(r"\bsales\s*force\b|\bsalesforce\b", text, re.IGNORECASE):
        return "Salesforce"
    if re.search(r"\bpega\b", text, re.IGNORECASE):
        return "Pega"
    if re.search(r"ciberseguridad|seguridad\s+(?:tic|informatica|de\s+la\s+informacion)", text, re.IGNORECASE):
        return "Ciberseguridad"
    if re.search(r"telecomunicaciones|telefonia|redes\s+de\s+comunicaciones", text, re.IGNORECASE):
        return "Telecomunicaciones"
    if re.search(r"\bcpd\b|centro\s+de\s+(?:proceso|procesamiento)\s+de\s+datos|centro\s+de\s+datos", text, re.IGNORECASE):
        return "CPD"
    if re.search(r"fotovoltaic|solar|electrolinera|kwp\b", text, re.IGNORECASE):
        return "Energía solar"
    if re.search(
        r"\bcau\b|centro\s+de\s+atencion\s+al\s+usuario|"
        r"soporte\s+(?:al|de)\s+puesto\s+de\s+trabajo|help\s*desk|service\s*desk|ticketing",
        text,
        re.IGNORECASE,
    ):
        return "CAU"
    if re.search(r"inteligencia\s+artificial|\bia\b|machine\s+learning", text, re.IGNORECASE):
        return "IA"
    if re.search(r"captacion\s+liger|equipamiento\s+de\s+captacion|produccion\s+audiovisual", text, re.IGNORECASE):
        return "Audiovisual"
    if re.search(r"licencias?|suscripciones?", text, re.IGNORECASE):
        return "Licencias"
    if re.search(
        r"frameworks?|desarrollo\s+de\s+software|software|saas|aplicaciones?|"
        r"sistemas?\s+de\s+informacion|plataforma\s+de\s+gestion|portales|solucion\s+tecnologica",
        text,
        re.IGNORECASE,
    ):
        return "Software"
    if re.search(
        r"sistemas?\s+(?:ti|tic|informaticos)|plataforma\s+tecnologica|oficina\s+de\s+entrega\s+de\s+valor|\bvmo\b",
        text,
        re.IGNORECASE,
    ):
        return "Sistemas TI"
    return ""


def parse_favorites(html: str) -> list[tuple[str, str]]:
    """Devuelve [(id_cliente_busqueda, alias), ...] de la tabla de favoritos."""
    soup = BeautifulSoup(html, "lxml")
    favorites = []
    for row in soup.select(selectors.FAVORITES_TABLE_ROW_SELECTOR):
        link = row.select_one(selectors.FAVORITES_LINK_SELECTOR)
        if link is None or not link.get("id", "").startswith("cargar_"):
            continue
        id_cliente_busqueda = link["id"].removeprefix("cargar_")
        alias = link.get_text(strip=True)
        favorites.append((id_cliente_busqueda, alias))
    return favorites


class FavoriteNotFoundError(Exception):
    pass


class AmbiguousFavoriteError(Exception):
    pass


def find_favorite_id(favorites: list[tuple[str, str]], favorite_name: str) -> str:
    """Busca coincidencia exacta normalizada (case/espacios) del alias.

    No acepta coincidencias parciales. Lanza FavoriteNotFoundError si no hay
    ninguna, AmbiguousFavoriteError si hay más de una (caso borde raro pero
    posible si el usuario duplicó el alias).
    """
    target = normalize_favorite_name(favorite_name)
    matches = [
        (fid, alias) for fid, alias in favorites
        if normalize_favorite_name(alias) == target
    ]
    if not matches:
        raise FavoriteNotFoundError(favorite_name)
    if len(matches) > 1:
        raise AmbiguousFavoriteError(favorite_name)
    return matches[0][0]


def _cell_text_without_breadcrumb(cell) -> str:
    """Texto de una celda de título, descartando el <small> de
    categoría/organismo que antecede al título real."""
    small = cell.find("small")
    if small is not None:
        small.decompose()
    return cell.get_text(" ", strip=True)


def parse_licitaciones_listing(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find(id=selectors.LISTING_TABLE_ID[selectors.SearchType.LICITACIONES])
    if table is None:
        return []
    idx = selectors.LICITACIONES_COLUMN_INDEXES
    rows = []
    for tr in table.select("tbody tr"):
        cells = tr.find_all("td")
        if len(cells) <= max(idx.values()):
            continue
        detail_url = tr.get("href", "")
        rows.append({
            "fecha": cells[idx["fecha"]].get_text(strip=True),
            "limite_ofertas": cells[idx["limite_ofertas"]].get_text(" ", strip=True),
            "titulo": _cell_text_without_breadcrumb(cells[idx["titulo"]]),
            "importe": cells[idx["importe"]].get_text(strip=True),
            "detail_url": detail_url,
        })
    return rows


def parse_vencimientos_listing(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find(id=selectors.LISTING_TABLE_ID[selectors.SearchType.VENCIMIENTOS])
    if table is None:
        return []
    idx = selectors.VENCIMIENTOS_COLUMN_INDEXES
    rows = []
    for tr in table.select("tbody tr"):
        cells = tr.find_all("td")
        if len(cells) <= max(idx.values()):
            continue
        titulo_cell = cells[idx["titulo"]]
        link = titulo_cell.find("a", href=True)
        detail_url = link["href"] if link else ""
        rows.append({
            "fecha_adjudicacion": cells[idx["fecha_adjudicacion"]].get_text(strip=True),
            "fecha_vencimiento": cells[idx["fecha_vencimiento"]].get_text(strip=True),
            "prorrogable_hasta": cells[idx["prorrogable_hasta"]].get_text(strip=True),
            "titulo": _cell_text_without_breadcrumb(titulo_cell),
            "importe": cells[idx["importe_adjudicacion"]].get_text(strip=True),
            "detail_url": detail_url,
        })
    return rows


def _extract_organismo_licitador(soup: BeautifulSoup) -> str | None:
    """El sitio no tiene un campo 'Órgano de contratación' como tal; el
    equivalente real es 'Organismo licitador', que vive en la cabecera de la
    ficha (fuera del bloque .adjudicacion-dato) como texto suelto seguido de
    un <h2> con el valor. La estructura exacta del contenedor difiere entre
    ficha de licitación y de adjudicación, así que se localiza por texto y
    se toma el <h2> siguiente en orden de documento, no por clase de
    contenedor (verificado en vivo el 2026-07-10 sobre 12 fichas reales)."""
    label_node = soup.find(string=_ORGANISMO_LICITADOR_LABEL_RE)
    if label_node is None:
        return None
    value_el = label_node.find_next("h2")
    if value_el is None:
        return None
    return value_el.get_text(" ", strip=True)


def _extract_header_value_after_label(soup: BeautifulSoup, label_pattern: str) -> str:
    label_node = soup.find(string=re.compile(label_pattern, re.IGNORECASE))
    if label_node is None:
        return ""
    value_el = label_node.find_next(["h2", "h4"])
    if value_el is None:
        return ""
    return value_el.get_text(" ", strip=True)


def _extract_source_value(value_el) -> str:
    link = value_el.find("a", href=True)
    if link is not None:
        return urljoin(selectors.BASE_URL + "/", link["href"])
    return value_el.get_text(" ", strip=True)


def parse_announcement_pdf_url(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for link in soup.find_all("a", href=True):
        text = " ".join(link.get_text(" ", strip=True).split())
        if re.search(r"\bAnuncio\s+(de\s+)?licitaci[oó]n\b", text, re.IGNORECASE):
            return urljoin(selectors.BASE_URL + "/", link["href"])
    return ""


def parse_contract_document_urls(html: str) -> list[tuple[str, str]]:
    """Devuelve documentos contractuales en orden de prioridad.

    El anuncio de licitación es la fuente principal. Si no existe o no aporta
    datos, el cliente puede probar otros documentos contractuales enlazados.
    """
    soup = BeautifulSoup(html, "lxml")
    priority_patterns = [
        ("anuncio_licitacion", r"\bAnuncio\s+(de\s+)?licitaci[oó]n\b"),
        ("prescripciones_tecnicas", r"\bPrescripciones\s+t[eé]cnicas\b"),
        ("clausulas_administrativas", r"\bCl[aá][uú]?sulas\s+administrativas\b"),
    ]
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    links = list(soup.find_all("a", href=True))
    for label, pattern in priority_patterns:
        for link in links:
            text = " ".join(link.get_text(" ", strip=True).split())
            if not re.search(pattern, text, re.IGNORECASE):
                continue
            url = urljoin(selectors.BASE_URL + "/", link["href"])
            if url in seen:
                continue
            found.append((label, url))
            seen.add(url)
    return found


def parse_detail(html: str) -> dict[str, str]:
    """Extrae los pares etiqueta/valor de una ficha (licitación o
    adjudicación: ambas usan las mismas clases .adjudicacion-dato*).
    Solo se devuelven los campos reconocidos en selectors.DETAIL_FIELD_LABELS;
    cualquier otro par presente en la página se ignora. Los campos ausentes
    en la página simplemente no aparecen en el dict devuelto (columna vacía
    en el Excel final, nunca se inventa un valor).
    """
    soup = BeautifulSoup(html, "lxml")
    result: dict[str, str] = {}
    for dato in soup.select(selectors.DETAIL_DATO_SELECTOR):
        label_el = dato.select_one(selectors.DETAIL_DATO_NOMBRE_SELECTOR)
        value_el = dato.select_one(selectors.DETAIL_DATO_VALOR_SELECTOR)
        if label_el is None or value_el is None:
            continue
        label = " ".join(label_el.get_text(" ", strip=True).split())
        field_name = selectors.DETAIL_FIELD_LABELS.get(label)
        if field_name is None:
            continue
        if field_name == "fuente_informacion":
            result[field_name] = _extract_source_value(value_el)
        elif field_name in {"fecha_vencimiento", "prorrogable_hasta"}:
            result[field_name] = normalize_date(value_el.get_text(" ", strip=True))
            if field_name == "fecha_vencimiento" and result[field_name]:
                result["fecha_vencimiento_origen"] = "explicit"
                result["fecha_fin_contrato"] = result[field_name]
                result["fecha_fin_origen"] = "explicit"
            if field_name == "prorrogable_hasta" and result[field_name]:
                result["prorrogable_hasta_origen"] = "explicit"
        else:
            result[field_name] = value_el.get_text(" ", strip=True)

    organismo = _extract_organismo_licitador(soup)
    if organismo:
        result["organismo_licitador"] = organismo

    fecha_limite_ofertas = normalize_date(
        _extract_header_value_after_label(soup, r"Fecha\s+l[ií]mite\s+presentaci[oó]n\s+ofertas")
    )
    if fecha_limite_ofertas:
        result["limite_ofertas"] = fecha_limite_ofertas

    fecha_adjudicacion = normalize_date(_extract_header_value_after_label(soup, r"Fecha\s+adjudicaci[oó]n"))
    if fecha_adjudicacion:
        result["fecha_adjudicacion"] = fecha_adjudicacion

    return result


def is_platinum_gated(current_url: str) -> bool:
    return selectors.PLATINUM_GATE_URL_MARKER in current_url
