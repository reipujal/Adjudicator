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
import os
import re
import time
from io import BytesIO
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from zipfile import BadZipFile, ZipFile

from playwright.async_api import (
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from . import contract_ai_extractor, excel_exporter, parsing, selectors
from .diagnostics import DiagnosticsLogger, resolve_headless

DEFAULT_PAGE_TIMEOUT_MS = 30_000
DEFAULT_DETAIL_TIMEOUT_MS = 20_000
DEFAULT_DOCUMENT_DOWNLOAD_RETRIES = 2
MAX_PAGINATION_PAGES = 200  # cinturón de seguridad anti bucle infinito
MAX_DETAIL_CONCURRENCY = 4  # fichas en paralelo; acotado a propósito para no
# machacar el sitio real con demasiadas pestañas simultáneas

CONTRACT_FIELD_KEYS = {
    "fecha_inicio_contrato",
    "fecha_inicio_origen",
    "fecha_fin_contrato",
    "fecha_fin_origen",
    "fecha_vencimiento",
    "fecha_vencimiento_origen",
    "prorrogable_hasta",
    "prorrogable_hasta_origen",
    "duracion_contrato",
    "numero_maximo_prorrogas",
    "duracion_prorroga",
    "solvencia",
}

DOCUMENT_LABELS = {
    "anuncio_licitacion": "Anuncio de licitación",
    "prescripciones_tecnicas": "Prescripciones técnicas",
    "clausulas_administrativas": "Cláusulas administrativas",
}

try:
    import pdfplumber
except ImportError:  # pragma: no cover - depende del entorno de ejecución
    pdfplumber = None


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


@dataclass
class DocumentTextCache:
    texts: dict[str, "DocumentText"]
    in_flight: dict[str, asyncio.Task["DocumentText"]]
    lock: asyncio.Lock


@dataclass
class DocumentText:
    text: str
    pages: list[str]


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
        await submit_login_form(page)
    except PlaywrightTimeoutError as exc:
        await diag.error_screenshot(page, "login_timeout")
        raise TenderstoolTimeoutError("Timeout durante el login") from exc

    if selectors.LOGIN_URL_MARKER in page.url:
        await diag.error_screenshot(page, "login_fallido")
        raise LoginError("usr/pwd incorrectos")

    diag.step("login correcto")


async def submit_login_form(page: Page) -> None:
    """Envía el login tolerando portales que no emiten navegación detectable.

    En vivo se ha observado que el submit a veces termina correctamente, pero
    Playwright no recibe el evento de navegación esperado. En ese caso se
    valida por URL/carga posterior antes de declarar timeout.
    """
    try:
        async with page.expect_navigation(timeout=DEFAULT_PAGE_TIMEOUT_MS):
            await page.click(selectors.SUBMIT_SELECTOR)
    except PlaywrightTimeoutError:
        if selectors.LOGIN_URL_MARKER not in page.url:
            await page.wait_for_load_state("networkidle", timeout=DEFAULT_PAGE_TIMEOUT_MS)
            return
        try:
            await page.wait_for_url(
                lambda url: selectors.LOGIN_URL_MARKER not in url,
                timeout=5_000,
            )
            await page.wait_for_load_state("networkidle", timeout=DEFAULT_PAGE_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            raise


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
    context: BrowserContext,
    row: dict,
    diag: DiagnosticsLogger,
    semaphore: asyncio.Semaphore,
    document_cache: DocumentTextCache,
) -> tuple[dict, str, str]:
    """Devuelve (campos, estado_extraccion, mensaje_error). Nunca lanza: un
    fallo en una ficha concreta se registra en la fila y el proceso continúa
    con la siguiente (requisito explícito del encargo)."""
    async with semaphore:
        detail_url = row["detail_url"]
        full_url = detail_url if detail_url.startswith("http") else f"{selectors.BASE_URL}/{detail_url}"
        detail_page = await context.new_page()
        try:
            await detail_page.goto(full_url, wait_until="networkidle", timeout=DEFAULT_DETAIL_TIMEOUT_MS)
            if parsing.is_platinum_gated(detail_page.url):
                return {}, "sin acceso (contenido Platinum)", ""
            detail_html = await detail_page.content()
            fields = parsing.parse_detail(detail_html)
            ai_stats = contract_ai_extractor.ExtractionStats()
            pdf_fields = await extract_contract_fields_from_documents(
                detail_page,
                detail_html,
                source_url=fields.get("fuente_informacion", ""),
                reference_dates=[
                    parsing.normalize_date(row.get("fecha", "")),
                    parsing.normalize_date(row.get("limite_ofertas", "")),
                    parsing.normalize_date(row.get("fecha_adjudicacion", "")),
                    parsing.normalize_date(row.get("fecha_vencimiento", "")),
                ],
                diag=diag,
                document_cache=document_cache,
                context=_build_contract_extraction_context(row, fields),
                stats=ai_stats,
            )
            if ai_stats.cache_hits or ai_stats.cache_misses:
                diag.step(f"metricas IA contractual: {ai_stats.summary()}")
            _merge_contract_fields_from_primary_source(fields, pdf_fields)
            return fields, "ok", ""
        except PlaywrightTimeoutError as exc:
            await diag.error_screenshot(detail_page, "detalle_timeout")
            return {}, "error", f"timeout cargando ficha: {exc}"
        except Exception as exc:  # noqa: BLE001 - contención deliberada por fila (ver docstring)
            await diag.error_screenshot(detail_page, "detalle_error")
            return {}, "error", str(exc)
        finally:
            await detail_page.close()


def _merge_prefer_existing(target: dict, source: dict) -> None:
    for key, value in source.items():
        if value in ("", None, "null"):
            continue
        if target.get(key) in ("", None):
            target[key] = value


def _merge_contract_fields_from_primary_source(target: dict, source: dict) -> None:
    """PDF/documentos contractuales prevalecen sobre el HTML visible."""
    for key, value in source.items():
        if value in ("", None, "null"):
            continue
        if target.get(key) in ("", None) or key in CONTRACT_FIELD_KEYS:
            target[key] = value


def _build_contract_extraction_context(row: dict, fields: dict) -> contract_ai_extractor.ExtractionContext:
    title = row.get("titulo", "") or fields.get("titulo", "")
    expediente = fields.get("numero_expediente", "") or row.get("numero_expediente", "")
    return contract_ai_extractor.ExtractionContext(
        title=title,
        expediente=expediente,
        lot=_infer_lot_context(title) or _infer_lot_context("", expediente),
    )


def _infer_lot_context(title: str, expediente: str = "") -> str:
    text = " ".join(value for value in [title, expediente] if value)
    patterns = [
        r"\bLote\s+(\d+[A-Za-z]?)\b(?:\s*[:.-]\s*([^|]+?))?(?=$|\s+Lote\s+\d|\.)",
        r"_lote(\d+[A-Za-z]?)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        lot_id = match.group(1)
        description = match.group(2).strip() if len(match.groups()) > 1 and match.group(2) else ""
        return f"Lote {lot_id}: {description}" if description else f"Lote {lot_id}"
    return ""


def _merge_contract_fields_without_overwrite(target: dict, source: dict) -> None:
    """Mantiene el orden de prioridad documental: anuncio > PPT > PCAP."""
    for key, value in source.items():
        if value in ("", None, "null"):
            continue
        if target.get(key) in ("", None, "null"):
            target[key] = value


def _document_name(label: str) -> str:
    return DOCUMENT_LABELS.get(label, label.replace("_", " "))


def _extract_document_text_sync(document_bytes: bytes) -> DocumentText:
    if document_bytes.startswith(b"PK"):
        try:
            with ZipFile(BytesIO(document_bytes)) as archive:
                chunks = []
                for name in archive.namelist():
                    if name.lower().endswith((".xml", ".txt", ".html", ".htm")):
                        chunks.append(archive.read(name).decode("utf-8", errors="ignore"))
                return DocumentText(text="\n".join(chunks), pages=[])
        except BadZipFile:
            text = document_bytes.decode("utf-8", errors="ignore")
            return DocumentText(text=text, pages=[])
    if not document_bytes.startswith(b"%PDF"):
        text = document_bytes.decode("utf-8", errors="ignore")
        return DocumentText(text=text, pages=[text])
    if b"%%EOF" not in document_bytes[-4096:]:
        raise ValueError("PDF incompleto: falta marcador %%EOF")
    if pdfplumber is None:
        return DocumentText(text="", pages=[])
    with pdfplumber.open(BytesIO(document_bytes)) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
        return DocumentText(text="\n".join(pages), pages=pages)


def _extract_pdf_text_sync(pdf_bytes: bytes) -> str:
    return _extract_document_text_sync(pdf_bytes).text


async def extract_contract_fields_from_documents(
    page: Page,
    detail_html: str,
    source_url: str,
    reference_dates: list[str],
    diag: DiagnosticsLogger,
    document_cache: DocumentTextCache | None = None,
    context: contract_ai_extractor.ExtractionContext | None = None,
    stats: contract_ai_extractor.ExtractionStats | None = None,
) -> dict:
    if pdfplumber is None:
        diag.step("pdfplumber no instalado: se omite extracción contractual desde PDF")
        return {}

    ai_pages: list[contract_ai_extractor.DocumentPage] = []
    for label, url in parsing.parse_contract_document_urls(detail_html):
        try:
            document_text = await _get_document_text(
                page,
                url,
                label,
                diag,
                document_cache=document_cache,
            )
        except Exception as exc:  # noqa: BLE001 - un PDF concreto no debe tumbar la ficha
            diag.step(f"documento contractual no procesado: {label} error={exc}")
            continue
        if not document_text.text:
            continue

        document_name = _document_name(label)
        for page_number, page_text in enumerate(document_text.pages, start=1):
            ai_pages.append(
                contract_ai_extractor.DocumentPage(
                    document_name=document_name,
                    page_number=page_number,
                    text=page_text,
                )
            )

    used_source_fallback = False
    if not ai_pages and "contractaciopublica.cat" in source_url:
        ai_pages.extend(await _extract_contractaciopublica_source_pages(page, source_url, diag))
        used_source_fallback = True

    if not ai_pages:
        return {}

    try:
        diag.step(f"extraccion contractual IA iniciada: paginas={len(ai_pages)}")
        fields = await asyncio.to_thread(_extract_contract_fields_with_optional_context, ai_pages, context, stats)
    except contract_ai_extractor.ContractAIUnavailableError as exc:
        diag.step(f"extracción contractual IA omitida: {exc}")
        return {}
    except Exception as exc:  # noqa: BLE001 - un fallo IA no debe tumbar una ficha concreta
        diag.step(f"extracción contractual IA fallida: {exc}")
        return {}

    if not fields and not used_source_fallback and "contractaciopublica.cat" in source_url:
        source_pages = await _extract_contractaciopublica_source_pages(page, source_url, diag)
        if source_pages:
            try:
                diag.step(f"extraccion contractual IA desde fuente publica iniciada: paginas={len(source_pages)}")
                fields = await asyncio.to_thread(
                    _extract_contract_fields_with_optional_context,
                    source_pages,
                    context,
                    stats,
                )
            except Exception as exc:  # noqa: BLE001 - fallback best effort
                diag.step(f"extraccion contractual IA desde fuente publica fallida: {exc}")
                return {}

    if any(fields.get(key) for key in ("duracion_contrato", "fecha_inicio_contrato", "fecha_fin_contrato")):
        diag.step("datos contractuales extraídos mediante IA")
    return fields


def _extract_contract_fields_with_optional_context(
    pages: list[contract_ai_extractor.DocumentPage],
    context: contract_ai_extractor.ExtractionContext | None,
    stats: contract_ai_extractor.ExtractionStats | None,
) -> dict:
    if context is None and stats is None:
        return contract_ai_extractor.extract_contract_fields_from_pages(pages)
    return contract_ai_extractor.extract_contract_fields_from_pages(pages, context=context, stats=stats)


async def _get_document_text(
    page: Page,
    url: str,
    label: str,
    diag: DiagnosticsLogger,
    document_cache: DocumentTextCache | None = None,
) -> DocumentText:
    if document_cache is None:
        return await _download_document_text(page, url, label, diag)

    owner = False
    async with document_cache.lock:
        if url in document_cache.texts:
            diag.step(f"documento contractual reutilizado desde caché: {label}")
            return document_cache.texts[url]
        task = document_cache.in_flight.get(url)
        if task is None:
            task = asyncio.create_task(_download_document_text(page, url, label, diag))
            document_cache.in_flight[url] = task
            owner = True

    try:
        text = await task
    finally:
        if owner:
            async with document_cache.lock:
                document_cache.in_flight.pop(url, None)
    if owner:
        async with document_cache.lock:
            document_cache.texts[url] = text
    elif text.text:
        diag.step(f"documento contractual reutilizado desde caché: {label}")
    return text


async def _download_document_text(page: Page, url: str, label: str, diag: DiagnosticsLogger) -> DocumentText:
    max_retries = _env_positive_int("TENDERSTOOL_DOCUMENT_DOWNLOAD_RETRIES", DEFAULT_DOCUMENT_DOWNLOAD_RETRIES)
    last_error = ""
    for attempt in range(max_retries + 1):
        try:
            response = await page.request.get(url, timeout=DEFAULT_DETAIL_TIMEOUT_MS)
            if not response.ok:
                diag.step(f"documento contractual no descargado: {label} status={response.status}")
                return DocumentText(text="", pages=[])
            return await asyncio.to_thread(_extract_document_text_sync, await response.body())
        except Exception as exc:  # noqa: BLE001 - transient network/PDF failures are retried per document
            last_error = str(exc)
            if attempt >= max_retries:
                diag.step(
                    f"documento contractual no procesado: {label} "
                    f"error=PDF incompleto o invalido tras {max_retries + 1} intentos ({last_error})"
                )
                return DocumentText(text="", pages=[])
            diag.step(f"reintento descarga documento contractual: {label} intento={attempt + 2}")
            await asyncio.sleep(min(2**attempt, 8))
    raise ElementNotFoundError(f"No se pudo descargar documento {label}: {last_error}")


def _env_positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


async def _extract_contractaciopublica_source_pages(
    page: Page,
    source_url: str,
    diag: DiagnosticsLogger,
) -> list[contract_ai_extractor.DocumentPage]:
    source_page = await page.context.new_page()
    pages: list[contract_ai_extractor.DocumentPage] = []
    try:
        await source_page.goto(source_url, wait_until="networkidle", timeout=DEFAULT_PAGE_TIMEOUT_MS)
        buttons = source_page.locator("button")
        count = await buttons.count()
        for index in range(count):
            button = buttons.nth(index)
            label = " ".join((await button.inner_text(timeout=1000)).split())
            if not _is_contractaciopublica_contract_document(label):
                continue
            try:
                async with source_page.expect_download(timeout=DEFAULT_DETAIL_TIMEOUT_MS) as download_info:
                    await button.click(timeout=DEFAULT_DETAIL_TIMEOUT_MS)
                download = await download_info.value
                path = await download.path()
                if path is None:
                    continue
                document_text = await asyncio.to_thread(Path(path).read_bytes)
                parsed_text = await asyncio.to_thread(_extract_document_text_sync, document_text)
            except Exception as exc:  # noqa: BLE001 - fallback best effort por documento
                diag.step(f"documento fuente publica no procesado: {label} error={exc}")
                continue
            for page_number, page_text in enumerate(parsed_text.pages, start=1):
                pages.append(
                    contract_ai_extractor.DocumentPage(
                        document_name=label,
                        page_number=page_number,
                        text=page_text,
                    )
                )
        if pages:
            diag.step(f"documentos contractuales recuperados desde fuente publica: {source_url}")
    finally:
        await source_page.close()
    return pages


def _is_contractaciopublica_contract_document(label: str) -> bool:
    normalized = label.casefold()
    return normalized.endswith(".pdf") and any(
        marker in normalized
        for marker in [
            "pca",
            "pcap",
            "ppt",
            "plec",
            "claus",
            "prescrip",
        ]
    )


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
    document_cache = DocumentTextCache(texts={}, in_flight={}, lock=asyncio.Lock())
    total = len(rows)
    completed = 0

    async def _one(index: int, row: dict) -> tuple[int, dict, str, str]:
        nonlocal completed
        fields, estado, error_msg = await extract_detail(
            context,
            row,
            diag,
            semaphore,
            document_cache,
        )
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
                    "titulo": row.get("titulo", ""),
                    "importe": row.get("importe", ""),
                    "fecha_inicio_origen": "null",
                    "fecha_fin_origen": "null",
                    "fecha_vencimiento_origen": "null",
                    "prorrogable_hasta_origen": "null",
                }
                if params.search_type == selectors.SearchType.LICITACIONES:
                    record["limite_ofertas"] = fields.get("limite_ofertas", "")
                else:
                    record["limite_ofertas"] = fields.get("fecha_adjudicacion", "")
                    record["fecha_vencimiento"] = fields.get("fecha_vencimiento", "")
                    record["prorrogable_hasta"] = fields.get("prorrogable_hasta", "")
                record.update(fields)
                record["tecnologia"] = parsing.infer_technology(
                    params.favorite_name,
                    row.get("titulo", ""),
                    fields.get("numero_expediente", ""),
                    fields.get("criterios_adjudicacion", ""),
                    fields.get("fuente_informacion", ""),
                )
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
