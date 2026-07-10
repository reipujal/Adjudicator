"""Parsing puro de HTML de adjudicacionesTIC: sin Playwright, sin red.

Recibe HTML ya cargado (típicamente vía page.content()) y devuelve
estructuras de datos planas. Se puede testear directamente contra fixtures
reales sin necesidad de navegador ni mocks.
"""
from __future__ import annotations

from bs4 import BeautifulSoup

from . import selectors


def normalize_favorite_name(name: str) -> str:
    """Normaliza un nombre de favorito para comparación: minúsculas, sin
    espacios sobrantes al inicio/fin, espacios internos colapsados."""
    return " ".join(name.strip().split()).casefold()


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
        result[field_name] = value_el.get_text(" ", strip=True)
    return result


def is_platinum_gated(current_url: str) -> bool:
    return selectors.PLATINUM_GATE_URL_MARKER in current_url
