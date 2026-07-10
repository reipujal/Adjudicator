"""Orquestación Playwright (API async): login, navegación, favoritos,
extracción y paginación. La lógica de parsing en sí vive en parsing.py
(pura, testable sin navegador); este módulo solo mueve el navegador y
delega el parseo. La API async permite abrir varias fichas de detalle en
paralelo (acotado por semáforo) y reportar progreso en vivo sin bloquear
el hilo del servidor.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from playwright.async_api import (
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from . import excel_exporter, parsing, selectors
from .diagnostics import DiagnosticsLogger, resolve_headless

DEFAULT_PAGE_TIMEOUT_MS = 30_000
DEFAULT_DETAIL_TIMEOUT_MS = 20_000
MAX_PAGINATION_PAGES = 200  # cinturón de seguridad anti bucle infinito
MAX_DETAIL_CONCURRENCY = 4  # fichas en paralelo; acotado a propósito para no
# machacar el sitio real con demasiadas pestañas simultáneas


class LoginError(Exception):
    """Credenciales incorrectas. Mensaje funcional exacto: 'usr/pwd incorrectos'."""


class FavoriteNotFoundError(Exception):
    """Mensaje funcional exacto: 'favorito no encontrado'."""


class TenderstoolTimeoutError(Exception):
    """Timeout de carga controlado (login, navegación, página o ficha)."""


class ElementNotFoundError(Exception):
    """Cambio de estructura de pantalla: no se ha podido localizar un
    elemento esperado."""


@dataclass
class ExtractionParams:
    username: str
    password: str
    search_type: selectors.SearchType
    favorite_name: str
    max_results: int | None
    diagnostic_mode: bool


@dataclass
class ExtractionResult:
    search_type: str
    favorite_name: str
    max_results: int | None
    processed_count: int
    partial_error_count: int
    duration_seconds: float
    excel_path: Path
    run_id: str


async def accept_cookies_if_present(page: Page) -> None:
    try:
        await page.click(selectors.COOKIE_ACCEPT_SELECTOR, timeout=3000)
        await page.wait_for_load_state("networkidle")
    except PlaywrightTimeoutError:
        pass


async def login(page: Page, username: str, password: str, diag: DiagnosticsLogger) -> None:
    diag.step("login iniciado")
    try:
        await page.goto(selectors.LOGIN_URL, wait_until="networkidle", timeout=DEFAULT_PAGE_TIMEOUT_MS)
        await accept_cookies_if_present(page)
        if selectors.LOGIN_URL_MARKER not in page.url:
            await page.goto(selectors.LOGIN_URL, wait_until="networkidle", timeout=DEFAULT_PAGE_TIMEOUT_MS)
        await page.fill(selectors.USERNAME_SELECTOR, username, timeout=DEFAULT_PAGE_TIMEOUT_MS)
        await page.fill(selectors.PASSWORD_SELECTOR, password, timeout=DEFAULT_PAGE_TIMEOUT_MS)
        async with page.expect_navigation(timeout=DEFAULT_PAGE_TIMEOUT_MS):
            await page.click(selectors.SUBMIT_SELECTOR)
    except PlaywrightTimeoutError as exc:
        await diag.error_screenshot(page, "login_timeout")
        raise TenderstoolTimeoutError("Timeout durante el login") from exc

    if selectors.LOGIN_URL_MARKER in page.url:
        await diag.error_screenshot(page, "login_fallido")
        raise LoginError("usr/pwd incorrectos")

    diag.step("login correcto")


async def go_to_search_type(page: Page, search_type: selectors.SearchType, diag: DiagnosticsLogger) -> None:
    url = selectors.MODULE_URLS[search_type]
    try:
        await page.goto(url, wait_until="networkidle", timeout=DEFAULT_PAGE_TIMEOUT_MS)
    except PlaywrightTimeoutError as exc:
        await diag.error_screenshot(page, "navegacion_modulo_timeout")
        raise TenderstoolTimeoutError(f"Timeout navegando al módulo {search_type.value}") from exc
    diag.step(f"navegación a módulo: {search_type.value}")


async def open_favorites(page: Page, diag: DiagnosticsLogger) -> list[tuple[str, str]]:
    """Lee la lista de favoritos ya presente en la página del buscador (no
    requiere abrir el modal de la UI, que no es fiable bajo automatización)."""
    favorites = parsing.parse_favorites(await page.content())
    diag.step(f"favoritos abierto: {len(favorites)} favoritos disponibles")
    return favorites


async def select_favorite(
    page: Page, favorites: list[tuple[str, str]], favorite_name: str, diag: DiagnosticsLogger
) -> None:
    try:
        favorite_id = parsing.find_favorite_id(favorites, favorite_name)
    except (parsing.FavoriteNotFoundError, parsing.AmbiguousFavoriteError) as exc:
        raise FavoriteNotFoundError("favorito no encontrado") from exc

    diag.step(f"favorito seleccionado: id={favorite_id}")

    resp = await page.request.post(
        selectors.FAVORITES_AJAX_URL,
        data=json.dumps({"id_cliente_busqueda": favorite_id}),
        headers={"Content-Type": "application/json"},
        timeout=DEFAULT_PAGE_TIMEOUT_MS,
    )
    body = await resp.json() if resp.ok else {}
    if not resp.ok or not body.get("success"):
        raise ElementNotFoundError("No se pudo consultar los parámetros del favorito seleccionado")

    build_script = ""
    for dato in body.get("data", []):
        nombre = dato["filtro"]
        if nombre == "areas":
            nombre = "buscador_area[]"
        build_script += (
            f"$('<input>').attr({{name:{json.dumps(nombre)}, type:'hidden', "
            f"value:{json.dumps(dato['valor'])}}}).appendTo({json.dumps(selectors.FAVORITES_FORM_SELECTOR)});\n"
        )

    try:
        async with page.expect_navigation(timeout=DEFAULT_PAGE_TIMEOUT_MS):
            await page.evaluate(
                "() => {"
                + build_script
                + f"document.querySelector({json.dumps(selectors.FAVORITES_FORM_SELECTOR)}).submit();"
                + "}"
            )
    except PlaywrightTimeoutError as exc:
        await diag.error_screenshot(page, "aplicar_favorito_timeout")
        raise TenderstoolTimeoutError("Timeout aplicando el favorito seleccionado") from exc

    diag.step("búsqueda ejecutada (favorito aplicado)")


async def extract_listing_rows(
    page: Page,
    search_type: selectors.SearchType,
    max_results: int | None,
    diag: DiagnosticsLogger,
) -> list[dict]:
    parse_fn = (
        parsing.parse_licitaciones_listing
        if search_type == selectors.SearchType.LICITACIONES
        else parsing.parse_vencimientos_listing
    )
    table_id = selectors.LISTING_TABLE_ID[search_type]
    next_selector = selectors.PAGINATION_NEXT_SELECTOR[search_type]

    try:
        await page.wait_for_selector(f"#{table_id}", timeout=DEFAULT_PAGE_TIMEOUT_MS)
    except PlaywrightTimeoutError as exc:
        await diag.error_screenshot(page, "listado_no_encontrado")
        raise ElementNotFoundError("No se ha podido localizar la tabla de resultados") from exc

    all_rows: list[dict] = []
    seen_urls: set[str] = set()
    page_number = 1

    while True:
        rows = parse_fn(await page.content())
        new_rows = [r for r in rows if r["detail_url"] not in seen_urls]
        for r in new_rows:
            seen_urls.add(r["detail_url"])
        all_rows.extend(new_rows)
        diag.step(f"página {page_number} procesada ({len(new_rows)} filas nuevas, {len(all_rows)} acumuladas)")

        if max_results is not None and len(all_rows) >= max_results:
            all_rows = all_rows[:max_results]
            break
        if not new_rows and page_number > 1:
            break  # fin real de resultados (página repetida o vacía)

        next_button = await page.query_selector(next_selector)
        if next_button is None:
            break
        classes = await next_button.get_attribute("class") or ""
        if selectors.PAGINATION_DISABLED_CLASS in classes:
            break
        if page_number >= MAX_PAGINATION_PAGES:
            diag.step("límite de seguridad de páginas alcanzado, deteniendo paginación")
            break

        page_number += 1
        try:
            await next_button.click()
            await page.wait_for_load_state("networkidle", timeout=DEFAULT_PAGE_TIMEOUT_MS)
        except PlaywrightTimeoutError as exc:
            await diag.error_screenshot(page, f"paginacion_pagina_{page_number}_timeout")
            raise TenderstoolTimeoutError(f"Timeout cargando la página {page_number} de resultados") from exc

    diag.step(f"resultados detectados: {len(all_rows)} filas totales, {page_number} páginas procesadas")
    return all_rows


async def extract_detail(
    context: BrowserContext, detail_url: str, diag: DiagnosticsLogger, semaphore: asyncio.Semaphore
) -> tuple[dict, str, str]:
    """Devuelve (campos, estado_extraccion, mensaje_error). Nunca lanza: un
    fallo en una ficha concreta se registra en la fila y el proceso continúa
    con la siguiente (requisito explícito del encargo)."""
    async with semaphore:
        full_url = detail_url if detail_url.startswith("http") else f"{selectors.BASE_URL}/{detail_url}"
        detail_page = await context.new_page()
        try:
            await detail_page.goto(full_url, wait_until="networkidle", timeout=DEFAULT_DETAIL_TIMEOUT_MS)
            if parsing.is_platinum_gated(detail_page.url):
                return {}, "sin acceso (contenido Platinum)", ""
            fields = parsing.parse_detail(await detail_page.content())
            return fields, "ok", ""
        except PlaywrightTimeoutError as exc:
            await diag.error_screenshot(detail_page, "detalle_timeout")
            return {}, "error", f"timeout cargando ficha: {exc}"
        except Exception as exc:  # noqa: BLE001 - contención deliberada por fila (ver docstring)
            await diag.error_screenshot(detail_page, "detalle_error")
            return {}, "error", str(exc)
        finally:
            await detail_page.close()


async def extract_all_details(
    context: BrowserContext,
    rows: list[dict],
    diag: DiagnosticsLogger,
    max_concurrency: int = MAX_DETAIL_CONCURRENCY,
) -> list[tuple[dict, str, str]]:
    """Extrae el detalle de todas las filas con concurrencia acotada por
    semáforo (no ilimitada, para no saturar el sitio real). El progreso se
    reporta según van completándose, no en el orden original."""
    semaphore = asyncio.Semaphore(max_concurrency)
    total = len(rows)
    completed = 0

    async def _one(index: int, row: dict) -> tuple[int, dict, str, str]:
        nonlocal completed
        fields, estado, error_msg = await extract_detail(context, row["detail_url"], diag, semaphore)
        completed += 1
        diag.step(f"ficha {completed}/{total} procesada: estado={estado}")
        return index, fields, estado, error_msg

    tasks = [asyncio.create_task(_one(i, row)) for i, row in enumerate(rows)]
    results: list[tuple[dict, str, str] | None] = [None] * total
    for coro in asyncio.as_completed(tasks):
        index, fields, estado, error_msg = await coro
        results[index] = (fields, estado, error_msg)
    return results  # type: ignore[return-value]


async def fetch_favorites(
    username: str, password: str, search_type: selectors.SearchType
) -> list[str]:
    """Login ligero solo para poblar el desplegable de favoritos de la
    pantalla inicial. No hace nada más (ni busca, ni extrae) — sesión propia
    que se cierra al terminar, no se comparte con la ejecución real."""
    diag = DiagnosticsLogger(diagnostic_mode=False)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        try:
            await login(page, username, password, diag)
            await go_to_search_type(page, search_type, diag)
            favorites = await open_favorites(page, diag)
        finally:
            await context.close()
            await browser.close()
    return [alias for _, alias in favorites]


async def run_extraction(
    params: ExtractionParams,
    run_id: str,
    on_step: Callable[[str], None] | None = None,
) -> ExtractionResult:
    start = time.monotonic()
    diag = DiagnosticsLogger(diagnostic_mode=params.diagnostic_mode, run_id=run_id, on_step=on_step)
    diag.step(
        f"ejecución iniciada: tipo={params.search_type.value} favorito={params.favorite_name!r} "
        f"max_results={params.max_results}"
    )

    headless = resolve_headless(params.diagnostic_mode)
    rows: list[dict] = []
    partial_errors = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()
        try:
            await login(page, params.username, params.password, diag)
            await go_to_search_type(page, params.search_type, diag)
            favorites = await open_favorites(page, diag)
            await select_favorite(page, favorites, params.favorite_name, diag)
            listing_rows = await extract_listing_rows(page, params.search_type, params.max_results, diag)

            detail_results = await extract_all_details(context, listing_rows, diag)

            for row, (fields, estado, error_msg) in zip(listing_rows, detail_results):
                if estado == "error":
                    partial_errors += 1

                record = {
                    "tipo_busqueda": params.search_type.value,
                    "favorito": params.favorite_name,
                    "detail_url": row.get("detail_url", ""),
                    "titulo": row.get("titulo", ""),
                    "importe": row.get("importe", ""),
                    "extraido_en": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "estado_extraccion": estado,
                    "error_extraccion": error_msg,
                }
                if params.search_type == selectors.SearchType.LICITACIONES:
                    record["fecha"] = row.get("fecha", "")
                    record["fecha_normalizada"] = excel_exporter.normalize_date(row.get("fecha", ""))
                    record["limite_ofertas"] = row.get("limite_ofertas", "")
                else:
                    record["fecha"] = row.get("fecha_adjudicacion", "")
                    record["fecha_normalizada"] = excel_exporter.normalize_date(row.get("fecha_adjudicacion", ""))
                    record["limite_ofertas"] = row.get("fecha_adjudicacion", "")
                    record["fecha_vencimiento"] = row.get("fecha_vencimiento", "")
                    record["prorrogable_hasta"] = row.get("prorrogable_hasta", "")
                record.update(fields)
                rows.append(record)

            diag.step("Excel generado: iniciando construcción")
        finally:
            await context.close()
            await browser.close()

    excel_path = excel_exporter.build_excel(rows, params.search_type.value, params.favorite_name)
    duration = time.monotonic() - start
    diag.step(f"ejecución finalizada en {duration:.1f}s, excel={excel_path.name}")

    return ExtractionResult(
        search_type=params.search_type.value,
        favorite_name=params.favorite_name,
        max_results=params.max_results,
        processed_count=len(rows),
        partial_error_count=partial_errors,
        duration_seconds=duration,
        excel_path=excel_path,
        run_id=run_id,
    )
