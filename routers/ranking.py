# routers/ranking.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List

from sqlalchemy.orm import Session, joinedload

from database import get_db
from models import Pareja

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
    # 1) Traemos parejas con sus jugadores bien cargados (NO JOIN manual)
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

    # 2) Armamos respuesta sin mezclar nada
    resp: List[PosicionRanking] = []
    for p in parejas:
        j1 = p.jugador1
        j2 = p.jugador2

        nombre = f"{j1.nombre} {j1.apellido} / {j2.nombre} {j2.apellido}"

        resp.append(
            PosicionRanking(
                id=p.id,                 # id del registro (podés usar p.id)
                pareja_id=p.id,
                nombre_pareja=nombre,
                grupo=p.grupo,
                posicion_actual=p.posicion_actual or 0,
                ganados=0,
                perdidos=0,
                retiros=0,
                cuota_al_dia=True,       # por ahora fijo; luego lo conectamos
            )
        )

    return resp
