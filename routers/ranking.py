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


def _calc_stats_for_parejas(db: Session, pareja_ids: List[int]) -> Dict[int, Dict[str, int]]:
    """
    Devuelve stats por pareja:
      stats[pareja_id] = {"ganados": X, "perdidos": Y, "retiros": Z}
    """
    stats: Dict[int, Dict[str, int]] = {
        pid: {"ganados": 0, "perdidos": 0, "retiros": 0} for pid in pareja_ids
    }

    if not pareja_ids:
        return stats

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

    for d in desafios:
        a = d.retadora_pareja_id
        b = d.retada_pareja_id
        w = d.ganador_pareja_id  # puede ser None si algún día metés “retiro/wo” sin ganador

        # Solo contamos si están en nuestra lista
        if a not in stats or b not in stats:
            continue

        # ✅ Retiros: hoy no tenés campo retiro/wo en tu modelo
        # Entonces dejamos retiros en 0, salvo el caso raro de Jugado sin ganador.
        if w is None:
            stats[a]["retiros"] += 1
            stats[b]["retiros"] += 1
            continue

        # ✅ Ganados/Perdidos
        if w == a:
            stats[a]["ganados"] += 1
            stats[b]["perdidos"] += 1
        elif w == b:
            stats[b]["ganados"] += 1
            stats[a]["perdidos"] += 1
        else:
            # ganador no coincide con ninguno (dato corrupto)
            pass

    return stats


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
    stats = _calc_stats_for_parejas(db, pareja_ids)

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
                cuota_al_dia=True,  # lo conectamos después
            )
        )

    return resp
