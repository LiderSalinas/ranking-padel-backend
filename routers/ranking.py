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

    pareja_ids = [p.id for p in parejas]

    # Stats por pareja
    stats: Dict[int, Dict[str, int]] = {pid: {"ganados": 0, "perdidos": 0, "retiros": 0} for pid in pareja_ids}

    if pareja_ids:
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

        jugados_count: Dict[int, int] = {pid: 0 for pid in pareja_ids}

        for d in desafios:
            # cuenta jugado para ambas parejas participantes
            if d.retadora_pareja_id in jugados_count:
                jugados_count[d.retadora_pareja_id] += 1
            if d.retada_pareja_id in jugados_count:
                jugados_count[d.retada_pareja_id] += 1

            # suma victoria al ganador
            if d.ganador_pareja_id is not None and d.ganador_pareja_id in stats:
                stats[d.ganador_pareja_id]["ganados"] += 1

        # perdidos = jugados - ganados
        for pid in pareja_ids:
            ganados = stats[pid]["ganados"]
            jugados = jugados_count.get(pid, 0)
            stats[pid]["perdidos"] = max(0, jugados - ganados)
            # retiros queda 0 por ahora

    resp: List[PosicionRanking] = []
    for p in parejas:
        j1 = p.jugador1
        j2 = p.jugador2

        nombre = f"{j1.nombre} {j1.apellido} / {j2.nombre} {j2.apellido}"

        s = stats.get(p.id, {"ganados": 0, "perdidos": 0, "retiros": 0})

        resp.append(
            PosicionRanking(
                id=p.id,
                pareja_id=p.id,
                nombre_pareja=nombre,
                grupo=p.grupo,
                posicion_actual=p.posicion_actual or 0,
                ganados=s["ganados"],
                perdidos=s["perdidos"],
                retiros=s["retiros"],
                cuota_al_dia=True,  # por ahora fijo; luego lo conectamos
            )
        )

    return resp
