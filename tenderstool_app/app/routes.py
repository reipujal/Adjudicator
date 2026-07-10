from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from .schemas import ExtractionRequest
from .services import excel_exporter, lock, tenderstool_client
from .services.selectors import SearchType

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@router.post("/ejecutar", response_class=HTMLResponse)
def ejecutar(
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

    params = tenderstool_client.ExtractionParams(
        username=payload.username,
        password=payload.password,
        search_type=SearchType(payload.search_type),
        favorite_name=payload.favorite_name,
        max_results=payload.max_results,
        diagnostic_mode=payload.diagnostic_mode,
    )

    try:
        with lock.acquire_or_reject():
            result = tenderstool_client.run_extraction(params)
    except lock.ExtractionInProgressError as exc:
        return templates.TemplateResponse(
            request, "index.html", {"error": str(exc)}, status_code=409
        )
    except tenderstool_client.LoginError:
        return templates.TemplateResponse(
            request, "index.html", {"error": "usr/pwd incorrectos"}, status_code=401
        )
    except tenderstool_client.FavoriteNotFoundError:
        return templates.TemplateResponse(
            request, "index.html", {"error": "favorito no encontrado"}, status_code=404
        )
    except (tenderstool_client.TenderstoolTimeoutError, tenderstool_client.ElementNotFoundError):
        return templates.TemplateResponse(
            request,
            "index.html",
            {"error": "Error técnico durante la extracción. Actívese el modo diagnóstico para más detalle."},
            status_code=502,
        )
    finally:
        params.password = ""  # no conservar la credencial más allá de esta función

    return templates.TemplateResponse(request, "result.html", {"result": result})


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
