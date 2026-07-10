<!-- Autogenerado por `install.ps1 -Project`. No editar a mano. -->
<!-- Fuente: AGENTS.md (este proyecto). Regenerar si AGENTS.md cambia: `pwsh -File ../biblio_skills/install.ps1 -Project .` -->
<!-- Reglas universales: ya en CLAUDE.md global. Texto numerado: RULES.md -->

# AGENTS.md — Adjudicator

> Gobierno de este proyecto. Antigravity lo lee de forma nativa. No es un CLAUDE.md.

## Qué es este proyecto

Adjudicator es una aplicación web en Python que extrae información de portales
públicos de licitaciones y adjudicaciones, agrega los resultados en una vista
unificada y permite la descarga en Excel.

## Vocabulario de dominio

- **Licitación**: convocatoria de contrato público abierta a ofertas.
- **Adjudicación**: resolución de a quién se concede el contrato.
- **Portal**: cada fuente de datos (PLACE, Contratación del Estado, portales
  regionales, etc.).
- **Expediente**: identificador único de un procedimiento de contratación.
- **Pliego**: documento con las condiciones técnicas y económicas del contrato.
- **Convocatoria**: publicación formal de una licitación en un portal.

## Reglas globales que aplican

Este proyecto hereda las reglas universales de `biblio_skills/rules/`
(texto completo en `RULES.md`, importado por `CLAUDE.md`). Son críticas aquí:

- **Secretos fuera del código** (regla 01): cualquier credencial de portal,
  API key o URL privada va en `.env`, nunca en git.
- **Fail-closed en config de riesgo** (regla 01): si la config de un portal
  falla al leer, el scraper de ese portal se desactiva — no pasa en silencio.
- **Tests en la misma entrega** (regla 02): cada scraper nuevo lleva su test
  mínimo (happy path + portal caído + respuesta inesperada).
- **Idempotencia** (regla 09): los scrapers pueden ejecutarse varias veces sin
  duplicar datos. Usar claves de deduplicación por expediente + portal.
- **Falla ruidoso** (regla 09): errores de scraping se propagan con traza
  completa. No hay `except: pass`.

## Estructura

```
src/
├── scrapers/       # un módulo por portal (scraper_place.py, scraper_contratacion.py, …)
├── aggregator.py   # combina resultados de todos los scrapers
├── exporter.py     # exportación a Excel vía pandas + openpyxl
├── models.py       # dataclasses: Licitacion, Adjudicacion
├── app.py          # Flask: rutas y renderizado
└── templates/      # Jinja2 HTML
tests/
scripts/
  check_encoding.py
docs/memory/
```

## Convenciones específicas

- Runtime: Python 3.12+, gestionado con `uv`.
- Web: Flask + Jinja2 (sin JS framework hasta que haga falta).
- Scraping: `requests` + `beautifulsoup4` + `lxml`. Respetar `robots.txt` y
  añadir `time.sleep` entre requests al mismo portal.
- Datos: `pandas.DataFrame` como formato intermedio entre scrapers y exportador.
- Excel: `openpyxl` vía pandas (`to_excel`).
- Un scraper por portal, en `src/scrapers/scraper_<portal>.py`. Todos exponen
  la misma interfaz: `fetch() -> list[Licitacion | Adjudicacion]`.

## Comandos

- Instalar entorno: `uv pip sync requirements.lock`
- Tests: `pytest -v`
- Ejecutar app: `flask --app src/app run --debug`
- Regenerar lock: `uv pip compile requirements.in -o requirements.lock`

## Definition of Done de este proyecto

- Los tests pasan al 100% antes de cualquier cierre.
- Ningún portal nuevo se añade sin su scraper test correspondiente.
- La exportación Excel se verifica con un test de integración real (no mock).
- Datos sensibles de portales (credenciales, cookies de sesión) van en `.env`.
