# routers/desafios.py

from datetime import date, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from models import Pareja, Desafio, Jugador

from schemas.desafio import (
    DesafioCreate,
    DesafioResponse,
    DesafioHistorialItem,
)

from core.settings import settings
from core.security import get_current_jugador
from pydantic import BaseModel
from typing import Optional

class ResultadoSets(BaseModel):
    set1_retador: int
    set1_desafiado: int
    set2_retador: int
    set2_desafiado: int
    set3_retador: Optional[int] = None
    set3_desafiado: Optional[int] = None



router = APIRouter(
    tags=["Desafios"],  # OJO: SIN prefix acá, el prefix se pone en main.py
)

# -------------------------------------------------------------------
# MIS PRÓXIMOS DESAFÍOS (Pendiente / Aceptado / Jugado del jugador autenticado)
# -------------------------------------------------------------------
@router.get("/mis-proximos", response_model=List[DesafioResponse])
def mis_proximos(
    db: Session = Depends(get_db),
    current_jugador: Jugador = Depends(get_current_jugador),
):
    hoy = date.today()

    # 1) Subquery con las parejas donde juega el jugador logueado
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

    # 2) Estados que queremos mostrar
    estados_visibles = ["Pendiente", "Aceptado", "Jugado"]

    # 3) Limitar a la última semana (opcional)
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


# -------------------------------------------------------------------
# MIS DESAFÍOS (JUGADOR AUTENTICADO)
# -------------------------------------------------------------------
@router.get(
    "/mis-desafios",
    response_model=List[DesafioResponse],
    summary="Listar desafíos donde participa el jugador autenticado",
)
def listar_mis_desafios(
    db: Session = Depends(get_db),
    jugador_actual: Jugador = Depends(get_current_jugador),
):
    """
    Devuelve todos los desafíos donde el jugador autenticado participa,
    ya sea como jugador1 o jugador2 de alguna pareja.
    """
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


# -------------------------------------------------------------------
# LISTAR PRÓXIMOS DESAFÍOS (Pendientes / Aceptados - general)
# -------------------------------------------------------------------
@router.get(
    "/proximos",
    response_model=List[DesafioResponse],
    summary="Listar Próximos Desafíos (Pendientes / Aceptados)",
)
def listar_proximos_desafios(db: Session = Depends(get_db)):
    """
    Lista desafíos con estado Pendiente o Aceptado.
    """
    desafios = (
        db.query(Desafio)
        .filter(Desafio.estado.in_(["Pendiente", "Aceptado"]))
        .order_by(Desafio.fecha.asc(), Desafio.hora.asc())
        .all()
    )
    return desafios


# -------------------------------------------------------------------
# CREAR DESAFÍO
# -------------------------------------------------------------------
@router.post(
    "/",
    response_model=DesafioResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear Desafío",
)
def crear_desafio(payload: DesafioCreate, db: Session = Depends(get_db)):
    """
    Crea un nuevo desafío entre dos parejas.
    """

    retadora = (
        db.query(Pareja)
        .filter(Pareja.id == payload.retadora_pareja_id, Pareja.activo.is_(True))
        .first()
    )
    if not retadora:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pareja retadora no encontrada o inactiva.",
        )

    retada = (
        db.query(Pareja)
        .filter(Pareja.id == payload.retada_pareja_id, Pareja.activo.is_(True))
        .first()
    )
    if not retada:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pareja retada no encontrada o inactiva.",
        )

    if retadora.id == retada.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Una pareja no puede desafiarse a sí misma.",
        )

    # --- Validaciones adicionales del reglamento (apagadas en desarrollo) ---
    if settings.STRICT_RULES:
        # Acá vamos a ir metiendo reglas duras (3 puestos arriba, 2 partidos/semana, etc.)
        pass

    # Generar titulo_desafio
    if retadora.posicion_actual is not None and retada.posicion_actual is not None:
        titulo_desafio = f"{retadora.posicion_actual} vs {retada.posicion_actual}"
    else:
        titulo_desafio = f"{retadora.id} vs {retada.id}"

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

    return nuevo_desafio


# -------------------------------------------------------------------
# ACEPTAR DESAFÍO
# -------------------------------------------------------------------
@router.post(
    "/{desafio_id}/aceptar",
    response_model=DesafioResponse,
    summary="Aceptar Desafío",
)
def aceptar_desafio(desafio_id: int, db: Session = Depends(get_db)):
    """
    Marca un desafío como 'Aceptado'.
    """
    desafio = db.query(Desafio).filter(Desafio.id == desafio_id).first()

    if not desafio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Desafío no encontrado.",
        )

    if desafio.estado == "Jugado":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede aceptar un desafío que ya fue jugado.",
        )

    desafio.estado = "Aceptado"
    db.commit()
    db.refresh(desafio)
    return desafio


# -------------------------------------------------------------------
# RECHAZAR DESAFÍO
# -------------------------------------------------------------------
@router.post(
    "/{desafio_id}/rechazar",
    response_model=DesafioResponse,
    summary="Rechazar Desafío",
)
def rechazar_desafio(desafio_id: int, db: Session = Depends(get_db)):
    """
    Marca un desafío como 'Rechazado'.
    Solo se permite si está Pendiente o Aceptado.
    """
    desafio = db.query(Desafio).filter(Desafio.id == desafio_id).first()

    if not desafio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Desafío no encontrado.",
        )

    if desafio.estado == "Jugado":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede rechazar un desafío que ya fue jugado.",
        )

    if desafio.estado == "Rechazado":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este desafío ya está rechazado.",
        )

    desafio.estado = "Rechazado"
    db.commit()
    db.refresh(desafio)
    return desafio


# -------------------------------------------------------------------
# CARGAR RESULTADO Y APLICAR SWAP DE RANKING (REGALMENTO REAL)
# -------------------------------------------------------------------
from sqlalchemy import and_

def _gana_retador(data) -> bool:
    # Cuenta sets ganados por retador vs desafiado
    sets_ret = 0
    sets_des = 0

    # Set 1
    if data.set1_retador > data.set1_desafiado:
        sets_ret += 1
    elif data.set1_desafiado > data.set1_retador:
        sets_des += 1

    # Set 2
    if data.set2_retador > data.set2_desafiado:
        sets_ret += 1
    elif data.set2_desafiado > data.set2_retador:
        sets_des += 1

    # Set 3 (si existe)
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
    # 1) Buscar el desafío
    desafio = db.query(Desafio).filter(Desafio.id == desafio_id).first()
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafío no encontrado")

    if desafio.estado == "Jugado":
        # Evita doble carga
        raise HTTPException(status_code=400, detail="Este desafío ya está Jugado")

    # 2) Buscar parejas
    retadora = db.query(Pareja).filter(Pareja.id == desafio.retadora_pareja_id).first()
    retada = db.query(Pareja).filter(Pareja.id == desafio.retada_pareja_id).first()

    if not retadora or not retada:
        raise HTTPException(status_code=404, detail="Parejas del desafío no encontradas")

    # 3) Determinar ganador por sets
    retador_gana = _gana_retador(data)
    ganador_id = retadora.id if retador_gana else retada.id

    # 4) Guardar resultado mínimo en desafio
    desafio.estado = "Jugado"
    desafio.ganador_pareja_id = ganador_id

    # 5) Aplicar ranking (swap) SOLO si gana la retadora
    # Regla: el retador ocupa el puesto del desafiado (swap)
    desafio.pos_retadora_old = retadora.posicion_actual
    desafio.pos_retada_old = retada.posicion_actual

    if retador_gana:
        # swap posiciones
        retadora.posicion_actual, retada.posicion_actual = (
            retada.posicion_actual,
            retadora.posicion_actual,
        )
        desafio.swap_aplicado = True
    else:
        desafio.swap_aplicado = False

    desafio.ranking_aplicado = True

    db.commit()
    db.refresh(desafio)

    return desafio

# -------------------------------------------------------------------
# LISTAR DESAFÍOS DE UNA PAREJA (HISTORIAL)
# -------------------------------------------------------------------
@router.get(
    "/pareja/{pareja_id}",
    response_model=List[DesafioHistorialItem],
    summary="Listar desafíos de una pareja (historial)",
)
def listar_desafios_pareja(pareja_id: int, db: Session = Depends(get_db)):
    """
    Lista todos los desafíos donde participó una pareja,
    ya sea como retadora o como retada.
    """
    desafios = (
        db.query(Desafio)
        .filter(
            or_(
                Desafio.retadora_pareja_id == pareja_id,
                Desafio.retada_pareja_id == pareja_id,
            )
        )
        .order_by(Desafio.fecha.desc(), Desafio.hora.desc())
        .all()
    )

    return desafios


# -------------------------------------------------------------------
# OBTENER UN DESAFÍO POR ID
# -------------------------------------------------------------------
@router.get(
    "/{desafio_id}",
    response_model=DesafioResponse,
    summary="Obtener Desafío por ID",
)
def obtener_desafio(desafio_id: int, db: Session = Depends(get_db)):
    desafio = db.query(Desafio).filter(Desafio.id == desafio_id).first()
    if not desafio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Desafío no encontrado.",
        )
    return desafio
