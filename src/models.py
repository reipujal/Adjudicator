from dataclasses import dataclass
from datetime import date


@dataclass
class Licitacion:
    expediente: str
    portal: str
    titulo: str
    fecha_publicacion: date | None = None
    importe: float | None = None
    url: str = ""


@dataclass
class Adjudicacion:
    expediente: str
    portal: str
    adjudicatario: str
    importe: float | None = None
    fecha_adjudicacion: date | None = None
    url: str = ""
