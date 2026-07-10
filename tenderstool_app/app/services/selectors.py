"""Selectores y constantes del DOM real de adjudicacionesTIC/TendersTool.

Verificados en vivo el 2026-07-10 contra el sitio real (ver docs/memory para
el registro de la sesión de inspección). Si el sitio cambia de estructura,
este es el único fichero que debería necesitar tocarse.
"""
from enum import Enum


class SearchType(str, Enum):
    LICITACIONES = "licitaciones"
    VENCIMIENTOS = "vencimientos"


BASE_URL = "https://www.adjudicacionestic.com/front"
LOGIN_URL = f"{BASE_URL}/login.php"

# --- login ---
COOKIE_ACCEPT_SELECTOR = "#cookiesButtons a.button-cookiesSI"
USERNAME_SELECTOR = "#username"
PASSWORD_SELECTOR = "#password"
SUBMIT_SELECTOR = 'input[type="submit"]'
LANDING_URL_MARKER = "mi-panel.php"
LOGIN_URL_MARKER = "login.php"

# --- módulos ---
MODULE_URLS = {
    SearchType.LICITACIONES: f"{BASE_URL}/licitaciones.php",
    SearchType.VENCIMIENTOS: f"{BASE_URL}/adjudicaciones-vencimientos-ampliado.php",
}

# --- favoritos ---
# El click de la UI sobre ".link_cargar" no dispara su propio handler delegado
# de forma fiable bajo automatización (verificado). En su lugar, replicamos la
# llamada AJAX que hace el propio JS del sitio.
FAVORITES_AJAX_URL = f"{BASE_URL}/ajax-busquedas-favoritas-consultar.php"
FAVORITES_TABLE_ROW_SELECTOR = "#busquedas tbody tr"
FAVORITES_LINK_SELECTOR = "a.link_cargar"
FAVORITES_FORM_SELECTOR = "#enviarBusqueda"

# --- listados ---
LISTING_TABLE_ID = {
    SearchType.LICITACIONES: "licitaciones",
    SearchType.VENCIMIENTOS: "adjudicaciones",
}

# Índices de <td> confirmados en vivo sobre la fila real (4 columnas, sin
# columnas ocultas pese a que la config aoColumns del sitio sugiere 7 — se
# ha priorizado el HTML real capturado sobre la config JS genérica).
LICITACIONES_COLUMN_INDEXES = {
    "fecha": 0,
    "limite_ofertas": 1,
    "titulo": 2,
    "importe": 3,
}
# Vencimientos/adjudicaciones: 6 columnas, todas visibles.
VENCIMIENTOS_COLUMN_INDEXES = {
    "fecha_adjudicacion": 0,
    "fecha_vencimiento": 1,
    "prorrogable_hasta": 2,
    "titulo": 3,
    "importe_adjudicacion": 4,
}

PAGINATION_NEXT_SELECTOR = {
    SearchType.LICITACIONES: "#licitaciones_next",
    SearchType.VENCIMIENTOS: "#adjudicaciones_next",
}
PAGINATION_DISABLED_CLASS = "disabled"

# --- ficha de detalle ---
DETAIL_DATO_SELECTOR = ".adjudicacion-dato"
DETAIL_DATO_NOMBRE_SELECTOR = ".adjudicacion-dato-nombre"
DETAIL_DATO_VALOR_SELECTOR = ".adjudicacion-dato-valor"

# Bloqueo de contenido Platinum: al navegar a una ficha (p.ej. la variante
# licitaciones-ficha-proceso.php) el sitio redirige a esta URL si el plan del
# usuario no incluye ese contenido. No se intenta sortear: es una barrera
# contractual legítima (verificado en vivo el 2026-07-10, error=5, mensaje
# "Esta información sólo está disponible para usuarios Platinum").
PLATINUM_GATE_URL_MARKER = "registro.php"

# Mapa de etiquetas reales (tal cual aparecen en pantalla) -> nombre de campo
# interno. Si el sitio cambia el texto de una etiqueta, el campo quedará
# vacío (comportamiento esperado, no falla el proceso) hasta que se actualice
# este mapa.
DETAIL_FIELD_LABELS = {
    "Importe licitación": "importe_licitacion",
    "Importe adjudicación vs licitación": "importe_adjudicacion_vs_licitacion",
    "Número de expediente": "numero_expediente",
    "Estado": "estado",
    "Tipo de procedimiento": "tipo_procedimiento",
    "Tipo de tramitación": "tipo_tramitacion",
    "Clasificación CPV": "clasificacion_cpv",
    "Mercado vertical": "mercado_vertical",
    "Provincia": "provincia",
    "Comunidad autónoma": "comunidad_autonoma",
    "Criterios de adjudicación": "criterios_adjudicacion",
    "Fuente de información": "fuente_informacion",
}
