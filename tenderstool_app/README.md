# TendersTool Automation

Aplicación web interna que automatiza, vía Playwright (API async), la
ejecución de un favorito guardado en TendersTool/AdjudicacionesTIC
(Licitaciones o Vencimientos), abre cada ficha de detalle en paralelo
(acotado) y exporta el resultado a Excel, con progreso en vivo durante la
ejecución.

Pensada para ejecutarse dentro de la red corporativa/VPN. **No debe
exponerse a Internet.**

## Flujo de pantallas

Una sola página, dinámica (no hay navegación real entre "login" y
"selección" — así la password nunca sale del formulario ni se guarda en
servidor entre pasos):

1. Usuario rellena usuario/password/tipo de búsqueda y pulsa "Buscar
   favoritos" → `POST /favoritos` hace un login ligero (sesión propia,
   se cierra al momento), trae la lista real de favoritos de ese módulo y
   rellena el desplegable por AJAX, sin recargar la página.
2. Elige favorito, opcionalmente máximo de resultados y modo diagnóstico,
   pulsa "Ejecutar extracción" → `POST /ejecutar` devuelve al instante una
   pantalla de progreso con un `run_id` (no bloquea la petición HTTP: la
   extracción corre en segundo plano).
3. La pantalla de progreso sondea `GET /progreso/{run_id}` cada 1.5s y
   muestra los últimos pasos en vivo (login, página N, ficha N/M…).
4. Al terminar, redirige a `GET /resultado/{run_id}`: resumen + botón de
   descarga (éxito) o mensaje de error (`usr/pwd incorrectos`, `favorito no
   encontrado`, error técnico).

## Instalación

Desde la raíz de `tenderstool_app/` (usa el mismo entorno `uv`/venv que el
resto del repo, o uno propio):

```bash
uv pip install -r requirements.in
playwright install chromium
```

## Ejecutar en local (desarrollo)

```bash
uvicorn app.main:app --reload
```

Abre `http://localhost:8000`. La contraseña de TendersTool se introduce en
el formulario en cada ejecución — la aplicación nunca la guarda.

## Variables de entorno

Ninguna es obligatoria para el uso normal (usuario y password de TendersTool
se envían por el formulario, no por entorno). Opcional:

| Variable | Uso | Por defecto |
|---|---|---|
| — | (reservado para futura configuración de timeouts/URL base) | — |

## Progreso en vivo y concurrencia

- El motor (`app/services/tenderstool_client.py`) usa la API async de
  Playwright, no la síncrona: es lo que permite reportar progreso sin
  bloquear el hilo del servidor y abrir varias fichas de detalle en
  paralelo desde el mismo contexto de navegador.
- Las fichas de detalle se extraen con concurrencia acotada a
  `MAX_DETAIL_CONCURRENCY = 4` (constante en `tenderstool_client.py`) —
  deliberadamente limitada para no saturar el sitio real con demasiadas
  pestañas simultáneas.
- El estado de cada ejecución (pasos, si terminó, resultado o error) vive
  en `app/services/run_registry.py`, un registro en memoria de proceso.
  Igual que el guard de concurrencia anterior, esto asume un único worker
  de uvicorn (ver sección Docker) y no persiste entre reinicios ni limpia
  ejecuciones antiguas — aceptable para un piloto de un usuario; si esto
  crece, añadir una TTL/limpieza sería lo primero a hacer.

## Descarga del Excel

El botón "Descargar Excel" de la pantalla de resultado usa la File System
Access API (`showSaveFilePicker`) para abrir el diálogo nativo "Guardar
como" del navegador y elegir carpeta de destino (`app/static/download.js`).
Solo la soportan navegadores basados en Chromium (Chrome, Edge) y requiere
un contexto seguro (`localhost` cuenta como tal; en despliegue detrás de
VPN sin HTTPS, dejará de estar disponible). Si el navegador no la soporta,
cae automáticamente a la descarga normal a la carpeta de descargas por
defecto — nunca se rompe, solo se pierde el diálogo de "dónde guardar".

## Modo diagnóstico

Checkbox "Modo diagnóstico" en el formulario:

- En local (Windows/con display), lanza Chromium visible (`headless=False`)
  y registra cada paso del flujo (login, navegación, favorito, páginas,
  fichas) por log.
- En servidor sin display gráfico, se mantiene `headless=True` automáticamente
  (no intenta abrir una ventana) y en su lugar guarda capturas de pantalla en
  `app/diagnostics/<run_id>/` ante cualquier error. Esa carpeta no se sirve
  públicamente ni se commitea (ver `.gitignore`).

## Despliegue en Docker

```bash
docker build -t tenderstool-automation .
docker run -p 8000:8000 tenderstool-automation
```

La imagen usa un único worker de uvicorn a propósito: el guard de "una
extracción a la vez" del MVP es un lock en memoria de proceso y **no**
protege frente a varios workers o réplicas. Si en el futuro se necesita
escalar horizontalmente, ese lock debe sustituirse por uno externo
(fichero compartido, Redis, etc.) antes de subir `--workers` o el número de
réplicas.

## Limitaciones conocidas

- **Paginación**: verificada en vivo con un favorito real de 23 resultados
  (3 páginas de 10+10+3) — el click en "Siguiente" y la detección de fin
  por botón deshabilitado funcionan correctamente contra el sitio real.
- **Mensaje exacto de login incorrecto**: no se ha provocado un login
  fallido real contra el sitio (para no generar ruido en la cuenta del
  cliente). La detección actual asume fallo si, tras enviar el formulario,
  la URL sigue conteniendo `login.php`. Si el sitio muestra un mensaje de
  error sin redirigir, ajustar `tenderstool_client.login()`.
- **Contenido Platinum**: la variante `licitaciones-ficha-proceso.php` (vista
  en algunos resultados) requiere un plan de suscripción superior al de la
  cuenta usada para las pruebas. La aplicación detecta el redirect a
  `registro.php` y marca la fila como `sin acceso (contenido Platinum)` sin
  intentar sortearlo — es una restricción contractual del proveedor, no un
  bug a resolver.
- **"Órgano de contratación"**: el sitio no tiene ningún campo con ese
  nombre literal (comprobado en vivo sobre 12 fichas reales distintas). El
  campo equivalente real es **"Organismo licitador"**, visible en la
  cabecera de toda ficha (no en el bloque "Otros datos"), y sí se extrae
  como columna `organismo_licitador` / "Órgano de contratación (Organismo
  licitador)" en el Excel.
- **Campo "Adjudicatario"**: también visible en la cabecera de la ficha de
  adjudicación, pero sigue sin extraerse (no estaba en la lista de campos
  del encargo original). Añadirlo es trivial: mismo patrón que
  `_extract_organismo_licitador` en `parsing.py`, buscando el `<h2>`
  siguiente al texto "Adjudicatario".
- **Selectores centralizados**: todo lo específico del DOM vive en
  `app/services/selectors.py`. Si el sitio cambia de estructura, ese es el
  único fichero que debería necesitar tocarse.

## Consideraciones de seguridad

- La contraseña se usa solo en memoria durante la ejecución: no se persiste
  en disco, base de datos, ni se escribe en logs. Al finalizar cada
  petición HTTP se descarta explícitamente.
- Los logs de diagnóstico registran pasos del flujo (p.ej. "login correcto",
  "página 2 procesada") pero nunca credenciales, cookies ni tokens de
  sesión.
- La automatización solo reproduce acciones equivalentes al uso normal de
  la interfaz por un usuario autorizado (login con credenciales propias,
  aplicar un favorito ya guardado, leer resultados). No se implementan ni
  se deben implementar técnicas para sortear CAPTCHAs, límites de plan,
  roles o cualquier otra barrera de acceso.
- `GET /descargar/{filename}` sanea el nombre de fichero (`Path(...).name`)
  para evitar path traversal y solo sirve `.xlsx` dentro de `app/downloads/`.
- Pensada para red corporativa/VPN; no lleva autenticación propia todavía
  (ver "Próximos pasos" más abajo).

## Si cambia la web de TendersTool

1. Repetir el mismo proceso de inspección que se usó para construir esta
   app: cargar la pantalla afectada con Playwright, volcar `page.content()`
   a un fichero y localizar los selectores nuevos.
2. Actualizar únicamente `app/services/selectors.py` (y, si cambia la
   estructura de datos, `app/services/parsing.py`).
3. Actualizar las fixtures en `tests/fixtures/` con HTML real capturado de
   nuevo y ajustar los tests que dependan de valores concretos.
4. Repasar en particular el mecanismo de favoritos: la UI de "Ver
   favoritas" no dispara su propio evento de click bajo automatización
   (verificado), por eso se replica la llamada AJAX
   (`ajax-busquedas-favoritas-consultar.php`) directamente. Si el sitio
   cambia ese endpoint, este es el punto a revisar primero.

## Tests

```bash
pytest              # suite normal (offline, sin tocar el sitio real)
pytest -m integration   # chequeo de salud contra el sitio real:
                        # requiere TENDERSTOOL_USER/TENDERSTOOL_PASSWORD
                        # reales en el entorno (ver tests/test_live_site_health.py).
                        # Si falla, el sitio probablemente cambió de
                        # estructura — repetir la inspección de la sección
                        # anterior antes de tocar nada más.
```

## Próximos pasos (fuera del alcance del MVP)

Diagnóstico avanzado más detallado (tracing de Playwright), mejoras
visuales, cola de trabajos para varias ejecuciones en paralelo (más allá
del guard actual de "una a la vez"), autenticación corporativa delante de
la app, histórico de ejecuciones, limpieza/TTL del registro de progreso en
memoria.
