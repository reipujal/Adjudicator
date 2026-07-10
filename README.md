# Adjudicator

Aplicación web Python que agrega información de licitaciones y adjudicaciones
públicas de múltiples portales y permite descargarla en Excel.

## Stack

- **Web**: Flask + Jinja2
- **Scraping**: requests + BeautifulSoup4 + lxml
- **Datos**: pandas + openpyxl

## Entorno

```bash
uv pip sync requirements.lock   # instala dependencias
flask --app src/app run --debug  # arranca la app
pytest -v                        # ejecuta los tests
```

## Estructura

```
src/scrapers/   — un módulo por portal (fetch() -> list)
src/models.py   — dataclasses Licitacion, Adjudicacion
src/aggregator.py — combina scrapers
src/exporter.py — exporta a Excel
src/app.py      — Flask routes
tests/          — suite de tests
```
