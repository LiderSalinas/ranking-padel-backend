# routers/desafios.py
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy import or_
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from models import Pareja, Desafio, Jugador, PushToken
from schemas.desafio import DesafioCreate, DesafioResponse, DesafioHistorialItem
from core.settings import settings
from core.security import get_current_jugador
from core.firebase_admin import send_push_to_tokens


class ResultadoSets(BaseModel):
    set1_retador: int
    set1_desafiado: int
    set2_retador: int
    set2_desafiado: int
    set3_retador: Optional[int] = None
    set3_desafiado: Optional[int] = None


router = APIRouter(tags=["Desafios"])


def _pareja_label(db: Session, pareja: Pareja) -> str:
    j1 = db.get(Jugador, pareja.jugador1_id)
    j2 = db.get(Jugador, pareja.jugador2_id)
    n1 = f"{j1.nombre} {j1.apellido}".strip() if j1 else f"Jugador {pareja.jugador1_id}"
    n2 = f"{j2.nombre} {j2.apellido}".strip() if j2 else f"Jugador {pareja.jugador2_id}"
    return f"{n1} / {n2}"


def _send_push_desafio_creado(background_tasks: BackgroundTasks, tokens: List[str], desafio: Desafio, title: str, body: str):
    # background_tasks necesita función sync
    def _job():
        send_push_to_tokens(
            tokens,
            title=title,
            body=body,
            data={
                "type": "desafio",
                "event": "created",
                "desafio_id": str(desafio.id),
                "estado": str(desafio.estado),
                "fecha": str(desafio.fecha),
                "hora": str(desafio.hora),
            },
        )

    background_tasks.add_task(_job)


@router.get("/mis-proximos", response_model=List[DesafioResponse])
def mis_proximos(
    db: Session = Depends(get_db),
    current_jugador: Jugador = Depends(get_current_jugador),
):
    hoy = date.today()

    parejas_ids_subq = (
        db.query(Pareja.id)
        .filter(
            or_(
                Pareja.jugador1_id == current_jugador.id,
                Pareja.jugador2_id == current_jugador.id,
            )
        )
        .subquery()
    )

    estados_visibles = ["Pendiente", "Aceptado", "Jugado"]
    fecha_min = hoy - timedelta(days=7)

    query = (
        db.query(Desafio)
        .filter(
            or_(
                Desafio.retadora_pareja_id.in_(parejas_ids_subq),
                Desafio.retada_pareja_id.in_(parejas_ids_subq),
            ),
            Desafio.estado.in_(estados_visibles),
            Desafio.fecha >= fecha_min,
        )
        .order_by(Desafio.fecha, Desafio.hora)
    )

    return query.all()


@router.get("/mis-desafios", response_model=List[DesafioResponse])
def listar_mis_desafios(
    db: Session = Depends(get_db),
    jugador_actual: Jugador = Depends(get_current_jugador),
):
    parejas_ids_subq = (
        db.query(Pareja.id)
        .filter(
            or_(
                Pareja.jugador1_id == jugador_actual.id,
                Pareja.jugador2_id == jugador_actual.id,
            )
        )
        .subquery()
    )

    desafios = (
        db.query(Desafio)
        .filter(
            or_(
                Desafio.retadora_pareja_id.in_(parejas_ids_subq),
                Desafio.retada_pareja_id.in_(parejas_ids_subq),
            )
        )
        .order_by(Desafio.fecha.desc(), Desafio.hora.desc())
        .all()
    )
    return desafios


@router.get("/proximos", response_model=List[DesafioResponse])
def listar_proximos_desafios(db: Session = Depends(get_db)):
    desafios = (
        db.query(Desafio)
        .filter(Desafio.estado.in_(["Pendiente", "Aceptado"]))
        .order_by(Desafio.fecha.asc(), Desafio.hora.asc())
        .all()
    )
    return desafios


@router.post("/", response_model=DesafioResponse, status_code=status.HTTP_201_CREATED)
def crear_desafio(
    payload: DesafioCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    jugador_actual: Jugador = Depends(get_current_jugador),
):
    retadora = (
        db.query(Pareja)
        .filter(Pareja.id == payload.retadora_pareja_id, Pareja.activo.is_(True))
        .first()
    )
    if not retadora:
        raise HTTPException(status_code=404, detail="Pareja retadora no encontrada o inactiva.")

    retada = (
        db.query(Pareja)
        .filter(Pareja.id == payload.retada_pareja_id, Pareja.activo.is_(True))
        .first()
    )
    if not retada:
        raise HTTPException(status_code=404, detail="Pareja retada no encontrada o inactiva.")

    if retadora.id == retada.id:
        raise HTTPException(status_code=400, detail="Una pareja no puede desafiarse a sí misma.")

    if settings.STRICT_RULES:
        pass

    # ✅ título "lindo" (AppSheet style)
    label_retadora = _pareja_label(db, retadora)
    label_retada = _pareja_label(db, retada)
    titulo_desafio = f"{label_retadora} vs {label_retada}"

    nuevo_desafio = Desafio(
        retadora_pareja_id=retadora.id,
        retada_pareja_id=retada.id,
        fecha=payload.fecha,
        hora=payload.hora,
        observacion=payload.observacion,
        estado="Pendiente",
        titulo_desafio=titulo_desafio,
    )

    db.add(nuevo_desafio)
    db.commit()
    db.refresh(nuevo_desafio)

    # ✅ Buscar tokens de los 4 jugadores (multi-device)
    jugador_ids = list({
        retadora.jugador1_id,
        retadora.jugador2_id,
        retada.jugador1_id,
        retada.jugador2_id,
    })

    tokens_rows = db.query(PushToken).filter(PushToken.jugador_id.in_(jugador_ids)).all()
    token_list = [t.fcm_token for t in tokens_rows if t.fcm_token and len(t.fcm_token) > 20]

    if token_list:
        title = "🆕 Nuevo desafío"
        body = f"⏱ {payload.fecha.strftime('%d/%m')} {str(payload.hora)[:5]}\n🎾 {titulo_desafio}\n👉 Toca para ver el detalle"
        _send_push_desafio_creado(background_tasks, token_list, nuevo_desafio, title, body)

    return nuevo_desafio


@router.post("/{desafio_id}/aceptar", response_model=DesafioResponse)
def aceptar_desafio(desafio_id: int, db: Session = Depends(get_db)):
    desafio = db.query(Desafio).filter(Desafio.id == desafio_id).first()
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafío no encontrado.")
    if desafio.estado == "Jugado":
        raise HTTPException(status_code=400, detail="No se puede aceptar un desafío que ya fue jugado.")

    desafio.estado = "Aceptado"
    db.commit()
    db.refresh(desafio)
    return desafio


@router.post("/{desafio_id}/rechazar", response_model=DesafioResponse)
def rechazar_desafio(desafio_id: int, db: Session = Depends(get_db)):
    desafio = db.query(Desafio).filter(Desafio.id == desafio_id).first()
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafío no encontrado.")
    if desafio.estado == "Jugado":
        raise HTTPException(status_code=400, detail="No se puede rechazar un desafío que ya fue jugado.")
    if desafio.estado == "Rechazado":
        raise HTTPException(status_code=400, detail="Este desafío ya está rechazado.")

    desafio.estado = "Rechazado"
    db.commit()
    db.refresh(desafio)
    return desafio


def _gana_retador(data: ResultadoSets) -> bool:
    sets_ret = 0
    sets_des = 0

    if data.set1_retador > data.set1_desafiado:
        sets_ret += 1
    elif data.set1_desafiado > data.set1_retador:
        sets_des += 1

    if data.set2_retador > data.set2_desafiado:
        sets_ret += 1
    elif data.set2_desafiado > data.set2_retador:
        sets_des += 1

    if data.set3_retador is not None and data.set3_desafiado is not None:
        if data.set3_retador > data.set3_desafiado:
            sets_ret += 1
        elif data.set3_desafiado > data.set3_retador:
            sets_des += 1

    return sets_ret > sets_des


@router.post("/{desafio_id}/resultado", response_model=DesafioResponse)
def cargar_resultado(
    desafio_id: int,
    data: ResultadoSets,
    db: Session = Depends(get_db),
    jugador_actual: Jugador = Depends(get_current_jugador),
):
    desafio = db.query(Desafio).filter(Desafio.id == desafio_id).first()
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafío no encontrado")
    if desafio.estado == "Jugado":
        raise HTTPException(status_code=400, detail="Este desafío ya está Jugado")

    retadora = db.query(Pareja).filter(Pareja.id == desafio.retadora_pareja_id).first()
    retada = db.query(Pareja).filter(Pareja.id == desafio.retada_pareja_id).first()
    if not retadora or not retada:
        raise HTTPException(status_code=404, detail="Parejas del desafío no encontradas")

    retador_gana = _gana_retador(data)
    ganador_id = retadora.id if retador_gana else retada.id

    desafio.estado = "Jugado"
    desafio.ganador_pareja_id = ganador_id

    desafio.pos_retadora_old = retadora.posicion_actual
    desafio.pos_retada_old = retada.posicion_actual

    if retador_gana:
        retadora.posicion_actual, retada.posicion_actual = (retada.posicion_actual, retadora.posicion_actual)
        desafio.swap_aplicado = True
    else:
        desafio.swap_aplicado = False

    desafio.ranking_aplicado = True

    db.commit()
    db.refresh(desafio)
    return desafio


@router.get("/pareja/{pareja_id}", response_model=List[DesafioHistorialItem])
def listar_desafios_pareja(pareja_id: int, db: Session = Depends(get_db)):
    desafios = (
        db.query(Desafio)
        .filter(or_(Desafio.retadora_pareja_id == pareja_id, Desafio.retada_pareja_id == pareja_id))
        .order_by(Desafio.fecha.desc(), Desafio.hora.desc())
        .all()
    )
    return desafios


@router.get("/{desafio_id}", response_model=DesafioResponse)
def obtener_desafio(desafio_id: int, db: Session = Depends(get_db)):
    desafio = db.query(Desafio).filter(Desafio.id == desafio_id).first()
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafío no encontrado.")
    return desafio
