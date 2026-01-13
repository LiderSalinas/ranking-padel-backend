# routers/ranking.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Dict

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_

from database import get_db
from models import Pareja, Desafio

router = APIRouter(prefix="/ranking", tags=["ranking"])


class PosicionRanking(BaseModel):
    id: int
    pareja_id: int
    nombre_pareja: str
    grupo: str
    posicion_actual: int

    ganados: int
    perdidos: int
    retiros: int

    cuota_al_dia: bool


@router.get("/posiciones", response_model=List[PosicionRanking])
def get_posiciones_ranking(db: Session = Depends(get_db)):
    # 1) Parejas activas con posición
    parejas = (
        db.query(Pareja)
        .options(
            joinedload(Pareja.jugador1),
            joinedload(Pareja.jugador2),
        )
        .filter(Pareja.activo.is_(True), Pareja.posicion_actual.isnot(None))
        .order_by(Pareja.grupo.asc(), Pareja.posicion_actual.asc())
        .all()
    )

    if not parejas:
        return []

    pareja_ids = [p.id for p in parejas]

    # 2) Traemos todos los desafíos jugados donde participó cualquiera de esas parejas
    desafios = (
        db.query(Desafio)
        .filter(
            Desafio.estado == "Jugado",
            or_(
                Desafio.retadora_pareja_id.in_(pareja_ids),
                Desafio.retada_pareja_id.in_(pareja_ids),
            ),
        )
        .all()
    )

    # 3) Armamos stats por pareja
    played: Dict[int, int] = {pid: 0 for pid in pareja_ids}
    wins: Dict[int, int] = {pid: 0 for pid in pareja_ids}
    retiros: Dict[int, int] = {pid: 0 for pid in pareja_ids}  # por ahora 0 (no hay campo en BD)

    for d in desafios:
        # suma partidos a ambos participantes
        if d.retadora_pareja_id in played:
            played[d.retadora_pareja_id] += 1
        if d.retada_pareja_id in played:
            played[d.retada_pareja_id] += 1

        # suma victoria al ganador si existe
        if d.ganador_pareja_id is not None and d.ganador_pareja_id in wins:
            wins[d.ganador_pareja_id] += 1

        # retiros: si más adelante agregás un campo (ej: d.resultado_tipo == "retiro"),
        # acá se incrementa. Por ahora queda 0.

    # 4) Respuesta final
    resp: List[PosicionRanking] = []
    for p in parejas:
        j1 = p.jugador1
        j2 = p.jugador2
        nombre = f"{j1.nombre} {j1.apellido} / {j2.nombre} {j2.apellido}"

        ganados = wins.get(p.id, 0)
        partidos = played.get(p.id, 0)
        perdidos = max(partidos - ganados, 0)
        ret = retiros.get(p.id, 0)

        resp.append(
            PosicionRanking(
                id=p.id,
                pareja_id=p.id,
                nombre_pareja=nombre,
                grupo=p.grupo,
                posicion_actual=p.posicion_actual or 0,
                ganados=ganados,
                perdidos=perdidos,
                retiros=ret,
                cuota_al_dia=True,  # lo conectamos después
            )
        )

    return resp
