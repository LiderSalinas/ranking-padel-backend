# core/rules.py
from datetime import date, timedelta
from typing import Tuple

from sqlalchemy.orm import Session
from sqlalchemy import or_

from models import Desafio, Pareja
from core.settings import settings


def valida_tres_puestos(pareja_retadora: Pareja, pareja_retada: Pareja) -> bool:
    """
    Regla: la pareja retadora solo puede desafiar hasta N puestos
    por encima (por defecto 3), según settings.MAX_SALTOS_DESAFIO.

    Devuelve True si la diferencia de posiciones es válida.
    """
    if (
        pareja_retadora.posicion_actual is None
        or pareja_retada.posicion_actual is None
    ):
        # Si falta algún dato, no bloqueamos (por ahora)
        return True

    # Ejemplo: retadora en puesto 8, retada en puesto 6 => diferencia = 2
    diferencia = pareja_retadora.posicion_actual - pareja_retada.posicion_actual

    # Queremos que la retadora esté "debajo o igual" a la retada
    # y que la diferencia no supere el máximo configurado.
    return (
        diferencia >= 0
        and diferencia <= settings.MAX_SALTOS_DESAFIO
    )


def _rango_semana(fecha_ref: date | None = None) -> Tuple[date, date]:
    """
    Calcula el rango [inicio_semana, fin_semana) para una fecha dada.
    Usamos lunes como inicio de semana.
    """
    if fecha_ref is None:
        fecha_ref = date.today()

    # weekday(): lunes=0 ... domingo=6
    inicio = fecha_ref - timedelta(days=fecha_ref.weekday())
    fin = inicio + timedelta(days=7)
    return inicio, fin


def valida_limite_partidos_semana(
    db: Session,
    pareja_id: int,
    fecha_ref: date | None = None,
) -> bool:
    """
    Regla: una pareja no puede tener más de N partidos por semana
    (Pendiente, Aceptado o Jugado), según settings.MAX_PARTIDOS_SEMANA.

    Devuelve True si TODAVÍA puede jugar más partidos esta semana.
    """
    inicio, fin = _rango_semana(fecha_ref)

    conteo = (
        db.query(Desafio)
        .filter(
            or_(
                Desafio.retadora_pareja_id == pareja_id,
                Desafio.retada_pareja_id == pareja_id,
            ),
            Desafio.fecha >= inicio,
            Desafio.fecha < fin,
            Desafio.estado.in_(["Pendiente", "Aceptado", "Jugado"]),
        )
        .count()
    )

    return conteo < settings.MAX_PARTIDOS_SEMANA
