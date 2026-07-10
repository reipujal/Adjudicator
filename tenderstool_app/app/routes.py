from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from .schemas import ExtractionRequest, FavoritesRequest
from .services import excel_exporter, run_registry, tenderstool_client
from .services.selectors import SearchType

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@router.post("/favoritos")
async def favoritos(payload: FavoritesRequest):
    """Login ligero para poblar el desplegable de favoritos de la pantalla
    inicial. No guarda nada entre esta llamada y /ejecutar: la password
    solo vive en el cuerpo de esta petición y en la sesión de Playwright
    que se abre y se cierra aquí mismo."""
    try:
        names = await tenderstool_client.fetch_favorites(
            payload.username, payload.password, payload.search_type
        )
    except tenderstool_client.LoginError:
        return JSONResponse({"error": "usr/pwd incorrectos"}, status_code=401)
    except (tenderstool_client.TenderstoolTimeoutError, tenderstool_client.ElementNotFoundError):
        return JSONResponse(
            {"error": "Error técnico cargando los favoritos. Inténtalo de nuevo."}, status_code=502
        )
    return {"favorites": names}


@router.post("/ejecutar", response_class=HTMLResponse)
async def ejecutar(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    search_type: str = Form(...),
    favorite_name: str = Form(...),
    max_results: str = Form(""),
    diagnostic_mode: bool = Form(False),
):
    max_results_raw = max_results.strip()
    if max_results_raw:
        try:
            max_results_value = int(max_results_raw)
        except ValueError:
            return templates.TemplateResponse(
                request,
                "index.html",
                {"error": "El número máximo de resultados debe ser un entero positivo."},
                status_code=400,
            )
    else:
        max_results_value = None

    try:
        payload = ExtractionRequest(
            username=username,
            password=password,
            search_type=search_type,
            favorite_name=favorite_name,
            max_results=max_results_value,
            diagnostic_mode=diagnostic_mode,
        )
    except ValidationError:
        return templates.TemplateResponse(
            request,
            "index.html",
            {"error": "Datos de entrada inválidos: revisa el formulario."},
            status_code=400,
        )

    if not await run_registry.try_acquire():
        return templates.TemplateResponse(
            request,
            "index.html",
            {"error": "Ya hay una extracción en curso. Inténtalo de nuevo más tarde."},
            status_code=409,
        )

    run_id = uuid.uuid4().hex[:12]
    run_registry.create(run_id)

    params = tenderstool_client.ExtractionParams(
        username=payload.username,
        password=payload.password,
        search_type=SearchType(payload.search_type),
        favorite_name=payload.favorite_name,
        max_results=payload.max_results,
        diagnostic_mode=payload.diagnostic_mode,
    )

    async def _runner() -> None:
        try:
            result = await tenderstool_client.run_extraction(
                params, run_id=run_id, on_step=lambda msg: run_registry.append_step(run_id, msg)
            )
            run_registry.finish_success(run_id, result)
        except tenderstool_client.LoginError:
            run_registry.finish_error(run_id, "usr/pwd incorrectos", 401)
        except tenderstool_client.FavoriteNotFoundError:
            run_registry.finish_error(run_id, "favorito no encontrado", 404)
        except (tenderstool_client.TenderstoolTimeoutError, tenderstool_client.ElementNotFoundError):
            run_registry.finish_error(
                run_id,
                "Error técnico durante la extracción. Actívese el modo diagnóstico para más detalle.",
                502,
            )
        finally:
            params.password = ""  # no conservar la credencial más allá de esta ejecución
            run_registry.release()

    asyncio.create_task(_runner())

    return templates.TemplateResponse(request, "progress.html", {"run_id": run_id})


@router.get("/progreso/{run_id}")
async def progreso(run_id: str):
    state = run_registry.get(run_id)
    if state is None:
        return JSONResponse({"error": "run_id desconocido"}, status_code=404)
    return {"steps": state.steps, "done": state.done}


@router.get("/resultado/{run_id}", response_class=HTMLResponse)
async def resultado(request: Request, run_id: str):
    state = run_registry.get(run_id)
    if state is None or not state.done:
        return templates.TemplateResponse(
            request,
            "index.html",
            {"error": "Ejecución no encontrada o todavía en curso."},
            status_code=404,
        )
    if state.error:
        return templates.TemplateResponse(
            request, "index.html", {"error": state.error}, status_code=state.error_status
        )
    return templates.TemplateResponse(request, "result.html", {"result": state.result})


@router.get("/descargar/{filename}")
def descargar(filename: str):
    safe_name = Path(filename).name  # evita path traversal
    path = excel_exporter.DOWNLOADS_DIR / safe_name
    if not path.is_file() or path.suffix != ".xlsx":
        return HTMLResponse("Fichero no encontrado", status_code=404)
    return FileResponse(
        path,
        filename=safe_name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
