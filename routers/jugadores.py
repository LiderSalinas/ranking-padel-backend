# routers/jugadores.py
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from database import get_db
import models
from schemas.player import (
    JugadorListaResponse,
    JugadorDetalleResponse,
    JugadorDesafioItem,
)

router = APIRouter()


@router.get("/", response_model=List[JugadorListaResponse])
def listar_jugadores(
    grupo: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Lista jugadores con estadísticas básicas.
    Si se pasa ?grupo=A solo muestra jugadores que tengan pareja en ese grupo.
    """
    jugadores = db.query(models.Jugador).all()
    resultado: list[JugadorListaResponse] = []

    for j in jugadores:
        # Parejas activas del jugador
        q_parejas = db.query(models.Pareja).filter(
            models.Pareja.activo.is_(True),
            or_(
                models.Pareja.jugador1_id == j.id,
                models.Pareja.jugador2_id == j.id,
            ),
        )

        if grupo:
            q_parejas = q_parejas.filter(models.Pareja.grupo == grupo)

        parejas_jugador = q_parejas.all()

        # Si se filtró por grupo y no tiene pareja en ese grupo -> lo saltamos
        if grupo and not parejas_jugador:
            continue

        grupo_principal = (
            parejas_jugador[0].grupo if parejas_jugador else None
        )
        ids_parejas = [p.id for p in parejas_jugador]

        if ids_parejas:
            desafios = (
                db.query(models.Desafio)
                .filter(
                    models.Desafio.estado == "Jugado",
                    or_(
                        models.Desafio.retadora_pareja_id.in_(ids_parejas),
                        models.Desafio.retada_pareja_id.in_(ids_parejas),
                    ),
                )
                .all()
            )
        else:
            desafios = []

        partidos_jugados = len(desafios)
        victorias = 0
        for d in desafios:
            if d.ganador_pareja_id is not None and d.ganador_pareja_id in ids_parejas:
                victorias += 1
        derrotas = partidos_jugados - victorias

        resultado.append(
            JugadorListaResponse(
                id=j.id,
                nombre=j.nombre,
                apellido=j.apellido,
                telefono=j.telefono,
                email=j.email,
                grupo_principal=grupo_principal,
                partidos_jugados=partidos_jugados,
                victorias=victorias,
                derrotas=derrotas,
            )
        )

    return resultado


@router.get("/{jugador_id}/detalle", response_model=JugadorDetalleResponse)
def obtener_detalle_jugador(
    jugador_id: int,
    db: Session = Depends(get_db),
):
    """
    Detalle de un jugador con historial de desafíos.
    """
    jugador = (
        db.query(models.Jugador)
        .filter(models.Jugador.id == jugador_id)
        .first()
    )
    if not jugador:
        raise HTTPException(
            status_code=404, detail="Jugador no encontrado."
        )

    parejas = (
        db.query(models.Pareja)
        .filter(
            models.Pareja.activo.is_(True),
            or_(
                models.Pareja.jugador1_id == jugador_id,
                models.Pareja.jugador2_id == jugador_id,
            ),
        )
        .all()
    )

    grupo_principal = parejas[0].grupo if parejas else None
    ids_parejas = [p.id for p in parejas]

    if ids_parejas:
        desafios = (
            db.query(models.Desafio)
            .filter(
                models.Desafio.estado == "Jugado",
                or_(
                    models.Desafio.retadora_pareja_id.in_(ids_parejas),
                    models.Desafio.retada_pareja_id.in_(ids_parejas),
                ),
            )
            .order_by(models.Desafio.fecha.desc(), models.Desafio.hora.desc())
            .all()
        )
    else:
        desafios = []

    partidos_jugados = len(desafios)
    victorias = 0
    desafios_items: list[JugadorDesafioItem] = []

    for d in desafios:
        if d.ganador_pareja_id is not None and d.ganador_pareja_id in ids_parejas:
            es_ganado = True
            victorias += 1
        else:
            es_ganado = False

        # Con qué pareja jugó y qué rol tuvo
        if d.retadora_pareja_id in ids_parejas:
            pareja_id = d.retadora_pareja_id
            rol = "retadora"
        else:
            pareja_id = d.retada_pareja_id
            rol = "retada"

        grupo_desafio = None
        for p in parejas:
            if p.id == pareja_id:
                grupo_desafio = p.grupo
                break

        desafios_items.append(
            JugadorDesafioItem(
                id=d.id,
                fecha=d.fecha,
                hora=d.hora,
                estado=d.estado,
                titulo_desafio=d.titulo_desafio,
                grupo=grupo_desafio or "",
                pareja_id=pareja_id,
                rol=rol,
                es_ganado=es_ganado,
            )
        )

    derrotas = partidos_jugados - victorias

    return JugadorDetalleResponse(
        id=jugador.id,
        nombre=jugador.nombre,
        apellido=jugador.apellido,
        telefono=jugador.telefono,
        email=jugador.email,
        grupo_principal=grupo_principal,
        partidos_jugados=partidos_jugados,
        victorias=victorias,
        derrotas=derrotas,
        desafios=desafios_items,
    )
