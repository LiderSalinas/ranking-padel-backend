# routers/parejas.py
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, joinedload

from database import get_db
import models

from schemas.pair import (
    JugadorDatos,
    JugadorEnPareja,
    ParejaCardResponse,
    ParejaRegistro,
    ParejaResponse,
    ParejaHistorialResponse,
    DesafioHistorialItem,
    ParejaDetalleResponse,
    ParejaDesafiableResponse,
)

router = APIRouter()


# --------- Helpers ---------
def get_or_create_jugador(data: JugadorDatos, db: Session) -> models.Jugador:
    """
    Si existe jugador con ese email -> lo usa.
    Si no -> lo crea.
    """
    jugador = None

    if data.email:
        jugador = db.query(models.Jugador).filter(models.Jugador.email == data.email).first()

    if not jugador:
        jugador = models.Jugador(
            nombre=data.nombre,
            apellido=data.apellido,
            telefono=data.telefono,
            email=data.email,
            # foto_url no se carga acá por ahora (lo hará el admin más adelante)
        )
        db.add(jugador)
        db.flush()  # conseguimos el id sin commit

    return jugador


def nombre_pareja(j1: models.Jugador, j2: models.Jugador) -> str:
    return f"{j1.nombre} {j1.apellido} / {j2.nombre} {j2.apellido}"


def _normalize_grupo_filter(grupo: Optional[str]) -> Optional[str]:
    """
    Soporta:
    - grupo="Femenino"  -> filtra "Femenino %"
    - grupo="Masculino" -> filtra "Masculino %"
    - grupo="Femenino A" o "Masculino B" -> exact match
    - grupo="A"/"B" (legacy) -> no lo usamos para género, pero no rompemos (match exact si existe)
    """
    if not grupo:
        return None
    g = (grupo or "").strip()
    return g if g else None


def _categoria_to_genero(categoria: str) -> Optional[str]:
    """
    Convierte categoría -> genero guardado en BD
    - "Femenino"  -> "F"
    - "Masculino" -> "M"
    """
    c = (categoria or "").strip().lower()
    if c == "femenino":
        return "F"
    if c == "masculino":
        return "M"
    return None


def _genero_from_grupo(grupo: str) -> Optional[str]:
    """
    Lee el prefijo del grupo y devuelve genero:
      "Femenino A" -> "F"
      "Masculino B" -> "M"
    """
    g = (grupo or "").strip()
    if not g:
        return None
    pref = g.split()[0].strip()
    return _categoria_to_genero(pref)


def _apply_grupo_filter(q, grupo: Optional[str]):
    g = _normalize_grupo_filter(grupo)
    if not g:
        return q

    gl = g.lower()

    # categoría completa: "Femenino" / "Masculino"
    if gl == "femenino" or gl == "masculino":
        gen = _categoria_to_genero(g)
        # doble filtro: por texto del grupo y por genero (si existe en tu BD)
        if gen:
            return q.filter(
                models.Pareja.grupo.ilike(f"{g}%"),
                or_(models.Pareja.genero.is_(None), models.Pareja.genero == gen),
            )
        return q.filter(models.Pareja.grupo.ilike(f"{g}%"))

    # exacto (ej: "Femenino A", "Masculino B")
    gen = _genero_from_grupo(g)
    if gen:
        return q.filter(
            models.Pareja.grupo == g,
            or_(models.Pareja.genero.is_(None), models.Pareja.genero == gen),
        )

    return q.filter(models.Pareja.grupo == g)


# --------- Endpoints ---------
@router.post(
    "/registrar",
    response_model=ParejaResponse,
    status_code=status.HTTP_201_CREATED,
)
def registrar_pareja(payload: ParejaRegistro, db: Session = Depends(get_db)):
    # 1) Crear / obtener jugadores
    j1 = get_or_create_jugador(payload.jugador1, db)
    j2 = get_or_create_jugador(payload.jugador2, db)

    if j1.id == j2.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Los dos jugadores de la pareja deben ser distintos.",
        )

    # 2) Capitán
    capitan = j1 if payload.capitan == 1 else j2

    # 3) Verificar si ya existe esa pareja en ese grupo (en cualquier orden)
    existente = (
        db.query(models.Pareja)
        .filter(
            models.Pareja.grupo == payload.grupo,
            or_(
                and_(
                    models.Pareja.jugador1_id == j1.id,
                    models.Pareja.jugador2_id == j2.id,
                ),
                and_(
                    models.Pareja.jugador1_id == j2.id,
                    models.Pareja.jugador2_id == j1.id,
                ),
            ),
        )
        .first()
    )

    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta pareja ya está registrada en este grupo.",
        )

    # 4) Posición inicial = último lugar del grupo + 1
    last_pos = (
        db.query(models.Pareja.posicion_actual)
        .filter(models.Pareja.grupo == payload.grupo)
        .order_by(models.Pareja.posicion_actual.desc())
        .first()
    )
    next_pos = (last_pos[0] + 1) if last_pos and last_pos[0] is not None else 1

    # ✅ genero automático por grupo (porque ya lo agregaste en Neon)
    genero_auto = _genero_from_grupo(payload.grupo)

    # 5) Crear la pareja
    pareja = models.Pareja(
        jugador1_id=j1.id,
        jugador2_id=j2.id,
        capitan_id=capitan.id,
        grupo=payload.grupo,
        posicion_actual=next_pos,
        genero=genero_auto,  # ✅ NUEVO (no rompe, es nullable)
        activo=True,
    )

    db.add(pareja)
    db.commit()
    db.refresh(pareja)

    return pareja


@router.get("/", response_model=List[ParejaResponse])
def listar_parejas(
    grupo: str | None = None,
    db: Session = Depends(get_db),
):
    """
    Lista parejas. Si se pasa ?grupo=... filtra.
    Soporta:
      - grupo=Femenino | Masculino  (categoría)
      - grupo=Femenino A | Masculino B (exacto)
    """
    query = db.query(models.Pareja)
    query = _apply_grupo_filter(query, grupo)

    parejas = query.order_by(models.Pareja.grupo, models.Pareja.posicion_actual).all()
    return parejas


@router.get("/ranking/{grupo}", response_model=List[ParejaResponse])
def obtener_ranking_por_grupo(
    grupo: str,
    db: Session = Depends(get_db),
):
    """
    Devuelve el ranking de parejas de un grupo (solo activas),
    ordenado por posicion_actual ascendente.
    """
    parejas = (
        db.query(models.Pareja)
        .filter(
            models.Pareja.grupo == grupo,
            models.Pareja.activo.is_(True),
        )
        .order_by(models.Pareja.posicion_actual.asc())
        .all()
    )

    if not parejas:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontraron parejas activas en el grupo {grupo}.",
        )

    return parejas


@router.get("/{pareja_id}/historial", response_model=ParejaHistorialResponse)
def obtener_historial_pareja(
    pareja_id: int,
    db: Session = Depends(get_db),
):
    """
    Historial de desafíos de una pareja.
    """
    pareja = (
        db.query(models.Pareja)
        .filter(models.Pareja.id == pareja_id, models.Pareja.activo.is_(True))
        .first()
    )

    if not pareja:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pareja no encontrada.",
        )

    desafios = (
        db.query(models.Desafio)
        .filter(
            models.Desafio.estado == "Jugado",
            or_(
                models.Desafio.retadora_pareja_id == pareja_id,
                models.Desafio.retada_pareja_id == pareja_id,
            ),
        )
        .order_by(models.Desafio.fecha.desc(), models.Desafio.hora.desc())
        .all()
    )

    partidos_jugados = len(desafios)
    victorias = sum(1 for d in desafios if d.ganador_pareja_id == pareja_id)
    derrotas = partidos_jugados - victorias

    desafios_items = [
        DesafioHistorialItem(
            id=d.id,
            fecha=d.fecha,
            hora=d.hora,
            estado=d.estado,
            titulo_desafio=d.titulo_desafio,
            es_ganado=(d.ganador_pareja_id == pareja_id),
        )
        for d in desafios
    ]

    return ParejaHistorialResponse(
        pareja_id=pareja.id,
        grupo=pareja.grupo,
        posicion_actual=pareja.posicion_actual,
        partidos_jugados=partidos_jugados,
        victorias=victorias,
        derrotas=derrotas,
        desafios=desafios_items,
    )


@router.get("/{pareja_id}/detalle", response_model=ParejaDetalleResponse)
def obtener_detalle_pareja(
    pareja_id: int,
    db: Session = Depends(get_db),
):
    """
    Detalle de una pareja con info de jugadores y estadísticas.
    """
    pareja = db.query(models.Pareja).filter(models.Pareja.id == pareja_id).first()

    if not pareja:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pareja no encontrada.",
        )

    jugador1 = db.query(models.Jugador).filter(models.Jugador.id == pareja.jugador1_id).first()
    jugador2 = db.query(models.Jugador).filter(models.Jugador.id == pareja.jugador2_id).first()
    capitan = db.query(models.Jugador).filter(models.Jugador.id == pareja.capitan_id).first()

    if not jugador1 or not jugador2 or not capitan:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Datos de jugadores incompletos para esta pareja.",
        )

    desafios = (
        db.query(models.Desafio)
        .filter(
            models.Desafio.estado == "Jugado",
            or_(
                models.Desafio.retadora_pareja_id == pareja_id,
                models.Desafio.retada_pareja_id == pareja_id,
            ),
        )
        .all()
    )

    partidos_jugados = len(desafios)
    victorias = sum(1 for d in desafios if d.ganador_pareja_id == pareja_id)
    derrotas = partidos_jugados - victorias

    return ParejaDetalleResponse(
        pareja_id=pareja.id,
        grupo=pareja.grupo,
        posicion_actual=pareja.posicion_actual,
        activo=pareja.activo,
        jugador1=JugadorEnPareja(
            id=jugador1.id,
            nombre=jugador1.nombre,
            apellido=jugador1.apellido,
            telefono=jugador1.telefono,
            email=jugador1.email,
            foto_url=getattr(jugador1, "foto_url", None),
        ),
        jugador2=JugadorEnPareja(
            id=jugador2.id,
            nombre=jugador2.nombre,
            apellido=jugador2.apellido,
            telefono=jugador2.telefono,
            email=jugador2.email,
            foto_url=getattr(jugador2, "foto_url", None),
        ),
        capitan=JugadorEnPareja(
            id=capitan.id,
            nombre=capitan.nombre,
            apellido=capitan.apellido,
            telefono=capitan.telefono,
            email=capitan.email,
            foto_url=getattr(capitan, "foto_url", None),
        ),
        partidos_jugados=partidos_jugados,
        victorias=victorias,
        derrotas=derrotas,
    )


@router.get("/desafiables", response_model=List[ParejaDesafiableResponse])
def listar_parejas_desafiables(
    grupo: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    ✅ REAL:
    Lista parejas desafiables desde la BD.
    Ahora soporta filtros:
      - grupo=Femenino | Masculino (categoría)
      - grupo=Femenino A | Masculino B (exacto)
    """
    q = (
        db.query(models.Pareja)
        .options(joinedload(models.Pareja.jugador1), joinedload(models.Pareja.jugador2))
        .filter(models.Pareja.activo.is_(True), models.Pareja.posicion_actual.isnot(None))
    )

    q = _apply_grupo_filter(q, grupo)

    parejas = q.order_by(models.Pareja.grupo.asc(), models.Pareja.posicion_actual.asc()).all()

    resp: List[ParejaDesafiableResponse] = []
    for p in parejas:
        j1 = p.jugador1
        j2 = p.jugador2
        resp.append(
            ParejaDesafiableResponse(
                id=p.id,
                nombre=nombre_pareja(j1, j2),
                posicion_actual=p.posicion_actual or 0,
                grupo=p.grupo,
            )
        )

    return resp


@router.get("/cards", response_model=List[ParejaCardResponse])
def listar_parejas_cards(
    grupo: str | None = None,
    db: Session = Depends(get_db),
):
    """
    ✅ Vista pública tipo AppSheet:
    Cards por pareja con fotos + stats.
    Filtro:
      - grupo=Femenino | Masculino (categoría)
      - grupo=Femenino A | Masculino B (exacto)
    """
    q = (
        db.query(models.Pareja)
        .options(joinedload(models.Pareja.jugador1), joinedload(models.Pareja.jugador2))
        .filter(models.Pareja.activo.is_(True), models.Pareja.posicion_actual.isnot(None))
    )

    q = _apply_grupo_filter(q, grupo)

    parejas = q.order_by(models.Pareja.grupo.asc(), models.Pareja.posicion_actual.asc()).all()

    resp: List[ParejaCardResponse] = []

    for p in parejas:
        j1 = p.jugador1
        j2 = p.jugador2

        # Stats reales: desafíos jugados donde participó
        desafios = (
            db.query(models.Desafio)
            .filter(
                models.Desafio.estado == "Jugado",
                or_(
                    models.Desafio.retadora_pareja_id == p.id,
                    models.Desafio.retada_pareja_id == p.id,
                ),
            )
            .all()
        )

        partidos_jugados = len(desafios)
        victorias = sum(1 for d in desafios if d.ganador_pareja_id == p.id)
        derrotas = partidos_jugados - victorias

        resp.append(
            ParejaCardResponse(
                pareja_id=p.id,
                grupo=p.grupo,
                posicion_actual=p.posicion_actual or 0,
                activo=p.activo,
                nombre_pareja=f"{j1.nombre} {j1.apellido} / {j2.nombre} {j2.apellido}",
                jugador1=JugadorEnPareja(
                    id=j1.id,
                    nombre=j1.nombre,
                    apellido=j1.apellido,
                    telefono=j1.telefono,
                    email=j1.email,
                    foto_url=j1.foto_url,
                ),
                jugador2=JugadorEnPareja(
                    id=j2.id,
                    nombre=j2.nombre,
                    apellido=j2.apellido,
                    telefono=j2.telefono,
                    email=j2.email,
                    foto_url=j2.foto_url,
                ),
                partidos_jugados=partidos_jugados,
                victorias=victorias,
                derrotas=derrotas,
            )
        )

    return resp
