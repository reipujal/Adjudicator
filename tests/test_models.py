from datetime import date

import pytest

from src.models import Adjudicacion, Licitacion


def test_licitacion_campos_minimos():
    l = Licitacion(expediente="EXP-001", portal="PLACE", titulo="Obras de X")
    assert l.expediente == "EXP-001"
    assert l.portal == "PLACE"
    assert l.importe is None
    assert l.url == ""


def test_adjudicacion_campos_minimos():
    a = Adjudicacion(expediente="EXP-002", portal="PLACE", adjudicatario="Empresa SA")
    assert a.adjudicatario == "Empresa SA"
    assert a.importe is None


def test_licitacion_con_todos_los_campos():
    l = Licitacion(
        expediente="EXP-003",
        portal="contratacion",
        titulo="Suministro de Y",
        fecha_publicacion=date(2025, 1, 15),
        importe=50000.0,
        url="https://example.com/exp003",
    )
    assert l.importe == 50000.0
    assert l.fecha_publicacion == date(2025, 1, 15)


def test_expediente_vacio_es_valido():
    l = Licitacion(expediente="", portal="PLACE", titulo="X")
    assert l.expediente == ""


def test_licitacion_y_adjudicacion_son_tipos_distintos():
    l = Licitacion(expediente="E1", portal="P", titulo="T")
    a = Adjudicacion(expediente="E1", portal="P", adjudicatario="A")
    assert type(l) is not type(a)
