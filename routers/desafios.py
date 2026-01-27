# routers/desafios.py
from datetime import date, timedelta, datetime, time
from typing import List, Optional, Set, Tuple

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy import or_
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from models import Pareja, Desafio, Jugador, PushToken
from schemas.desafio import DesafioResponse, DesafioHistorialItem
from core.security import get_current_jugador
from core.firebase_admin import send_push_to_tokens

router = APIRouter(tags=["Desafios"])


# ✅ NUEVO: payload de creación (retadora se calcula por token)
class DesafioCreateAuto(BaseModel):
    # compat: si viene, se ignora (para no romper front viejo)
    retadora_pareja_id: Optional[int] = None

    retada_pareja_id: int
    fecha: date
    hora: str  # "HH:MM" o "HH:MM:SS"
    observacion: Optional[str] = None


class ResultadoSets(BaseModel):
    # ✅ fecha jugado real (DATE) - viene del frontend como "YYYY-MM-DD"
    fecha_jugado: Optional[date] = None

    set1_retador: int
    set1_desafiado: int
    set2_retador: int
    set2_desafiado: int
    set3_retador: Optional[int] = None
    set3_desafiado: Optional[int] = None


class ReprogramarPayload(BaseModel):
    fecha: date
    hora: str  # "HH:MM" o "HH:MM:SS"


# ----------------- Helpers de reglas -----------------
def _parse_hora(h: str) -> time:
    h = (h or "").strip()
    if not h:
        raise HTTPException(status_code=400, detail="Hora inválida.")
    try:
        if len(h) == 5:  # HH:MM
            return datetime.strptime(h, "%H:%M").time()
        return datetime.strptime(h[:8], "%H:%M:%S").time()
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Formato de hora inválido. Use HH:MM o HH:MM:SS",
        )


# ✅ Solo horas redondas (HH:00)
def _ensure_hora_redonda(t: time) -> None:
    if t.minute != 0 or t.second != 0:
        raise HTTPException(
            status_code=400,
            detail="Hora inválida. Solo se permiten horas redondas (ej: 15:00).",
        )


def _pareja_label(db: Session, pareja: Pareja) -> str:
    j1 = db.get(Jugador, pareja.jugador1_id)
    j2 = db.get(Jugador, pareja.jugador2_id)
    n1 = f"{j1.nombre} {j1.apellido}".strip() if j1 else f"Jugador {pareja.jugador1_id}"
    n2 = f"{j2.nombre} {j2.apellido}".strip() if j2 else f"Jugador {pareja.jugador2_id}"
    return f"{n1} / {n2}"


def _categoria_from_grupo(grupo: str) -> str:
    """
    Con tu BD real:
      "Femenino A" -> "Femenino"
      "Masculino B" -> "Masculino"
    """
    g = (grupo or "").strip()
    if not g:
        return ""
    return g.split()[0].capitalize()


def _division_from_grupo(grupo: str) -> str:
    """
    "Femenino A" -> "A"
    "Masculino B" -> "B"
    """
    g = (grupo or "").strip()
    parts = g.split()
    if len(parts) >= 2:
        return parts[1].upper()
    return ""


def _genero_from_categoria(cat: str) -> Optional[str]:
    c = (cat or "").strip().lower()
    if c == "femenino":
        return "F"
    if c == "masculino":
        return "M"
    return None


def _same_category(db: Session, retadora: Pareja, retada: Pareja) -> bool:
    """
    ✅ Regla dura: no mezclar Masculino/Femenino.
    - Preferimos `genero` si está cargado.
    - Si está NULL en data vieja, caemos a prefijo de `grupo`.
    """
    gr = (getattr(retadora, "genero", None) or "").strip() or None
    gd = (getattr(retada, "genero", None) or "").strip() or None

    if gr and gd:
        return gr == gd

    # fallback por grupo (data legacy)
    cat_r = _categoria_from_grupo(retadora.grupo)
    cat_d = _categoria_from_grupo(retada.grupo)
    return bool(cat_r and cat_d and cat_r == cat_d)


def _semana_range(fecha: date) -> Tuple[date, date]:
    """
    Semana Lunes-Domingo.
    Devuelve (inicio, fin_inclusive).
    """
    start = fecha - timedelta(days=fecha.weekday())  # Monday=0
    end = start + timedelta(days=6)
    return start, end


def _count_partidos_semana(
    db: Session,
    pareja_id: int,
    fecha: date,
    exclude_desafio_id: Optional[int] = None,
) -> int:
    """
    Regla: Máx 2 partidos por semana por pareja.
    Cuenta desafíos en estados Pendiente/Aceptado/Jugado cuya fecha cae en esa semana.
    ✅ FIX: en reprogramación excluimos el desafío actual.
    """
    w_start, w_end = _semana_range(fecha)
    estados = ["Pendiente", "Aceptado", "Jugado"]

    q = (
        db.query(Desafio)
        .filter(
            Desafio.estado.in_(estados),
            Desafio.fecha >= w_start,
            Desafio.fecha <= w_end,
            or_(
                Desafio.retadora_pareja_id == pareja_id,
                Desafio.retada_pareja_id == pareja_id,
            ),
        )
    )

    if exclude_desafio_id is not None:
        q = q.filter(Desafio.id != exclude_desafio_id)

    return q.count()


def _interdivision_allowed(db: Session, retadora: Pareja, retada: Pareja) -> bool:
    """
    Regla:
      - Top 3 del grupo B puede desafiar a las últimas 3 del grupo A (misma categoría Masculino/Femenino)
      - Especial: Puesto 1 del B puede desafiar al Puesto 18 del A
    """
    div_r = _division_from_grupo(retadora.grupo)
    div_d = _division_from_grupo(retada.grupo)

    if not div_r or not div_d:
        return False

    # Solo B -> A
    if not (div_r == "B" and div_d == "A"):
        return False

    # debe haber posiciones
    if retadora.posicion_actual is None or retada.posicion_actual is None:
        return False

    # regla especial 1B -> 18A
    if retadora.posicion_actual == 1 and retada.posicion_actual == 18:
        return True

    # top 3 de B
    if retadora.posicion_actual not in (1, 2, 3):
        return False

    # últimas 3 de A: calculamos max en A (de esa categoría)
    categoria = _categoria_from_grupo(retadora.grupo)
    grupo_A = f"{categoria} A"

    max_pos_A = (
        db.query(Pareja.posicion_actual)
        .filter(Pareja.activo.is_(True), Pareja.grupo == grupo_A, Pareja.posicion_actual.isnot(None))
        .order_by(Pareja.posicion_actual.desc())
        .first()
    )
    if not max_pos_A or max_pos_A[0] is None:
        return False

    last = max_pos_A[0]
    ultimas = {last, max(1, last - 1), max(1, last - 2)}

    return retada.posicion_actual in ultimas


def _validate_desafio_rules(
    db: Session,
    retadora: Pareja,
    retada: Pareja,
    fecha: date,
    exclude_desafio_id: Optional[int] = None,
) -> None:
    """
    Aplica TODAS las reglas duras:
      - no cruza Masculino/Femenino (grupo + genero)
      - max 2 partidos por semana por pareja (Pendiente/Aceptado/Jugado)
      - dentro de la misma división: max 3 puestos y solo hacia arriba
      - interdivisión B->A: solo top3 vs last3 (+ especial 1B->18A)
    """
    if not _same_category(db, retadora, retada):
        raise HTTPException(status_code=400, detail="No se permiten desafíos entre Masculino y Femenino.")

    # Max 2 partidos por semana (para ambos)
    c1 = _count_partidos_semana(db, retadora.id, fecha, exclude_desafio_id=exclude_desafio_id)
    if c1 >= 2:
        raise HTTPException(status_code=400, detail="Tu dupla ya tiene 2 partidos esta semana.")

    c2 = _count_partidos_semana(db, retada.id, fecha, exclude_desafio_id=exclude_desafio_id)
    if c2 >= 2:
        raise HTTPException(status_code=400, detail="La dupla desafiada ya tiene 2 partidos esta semana.")

    # Misma división o interdivisión
    if retadora.grupo == retada.grupo:
        # regla max 3 puestos (y solo hacia arriba)
        if retadora.posicion_actual is None or retada.posicion_actual is None:
            return

        # retadora debe estar más abajo (número mayor) y retada arriba (número menor)
        if retada.posicion_actual >= retadora.posicion_actual:
            raise HTTPException(
                status_code=400,
                detail="Solo podés desafiar a una dupla por encima tuyo (mejor posición).",
            )

        diff = retadora.posicion_actual - retada.posicion_actual
        if diff > 3:
            raise HTTPException(status_code=400, detail="Solo se puede desafiar hasta 3 puestos arriba.")
        return

    # si no es mismo grupo, debe cumplir interdivisión
    if not _interdivision_allowed(db, retadora, retada):
        raise HTTPException(
            status_code=400,
            detail="Desafío no permitido entre grupos. Solo Top 3 de B puede desafiar a últimas 3 de A (misma categoría).",
        )


def _tokens_by_players(db: Session, jugador_ids: Set[int]) -> List[str]:
    """
    ✅ FIX iPhone: devuelve SOLO 1 token por jugador (el más reciente), dedupeado.
    - Si el jugador tiene Safari + PWA, evitamos doble notificación.
    """
    if not jugador_ids:
        return []

    rows = (
        db.query(PushToken)
        .filter(PushToken.jugador_id.in_(list(jugador_ids)))
        .order_by(PushToken.created_at.desc())
        .all()
    )

    seen_tokens = set()
    seen_players = set()
    out: List[str] = []

    for r in rows:
        jid = r.jugador_id
        if jid in seen_players:
            continue

        tok = (r.fcm_token or "").strip()
        if not tok or len(tok) < 20:
            continue

        if tok in seen_tokens:
            seen_players.add(jid)
            continue

        seen_tokens.add(tok)
        seen_players.add(jid)
        out.append(tok)

    return out


def _delete_invalid_tokens(invalid_tokens: List[str]) -> None:
    if not invalid_tokens:
        return

    try:
        from database import SessionLocal  # type: ignore
    except Exception:
        print("ℹ️ No pude importar SessionLocal para limpiar tokens inválidos. (Se omite cleanup)")
        return

    db2 = None
    try:
        db2 = SessionLocal()
        (
            db2.query(PushToken)
            .filter(PushToken.fcm_token.in_([t.strip() for t in invalid_tokens if t and t.strip()]))
            .delete(synchronize_session=False)
        )
        db2.commit()
        print(f"🧹 Tokens inválidos eliminados: {len(invalid_tokens)}")
    except Exception as e:
        print("❌ Error limpiando tokens inválidos:", str(e))
        try:
            if db2:
                db2.rollback()
        except Exception:
            pass
    finally:
        try:
            if db2:
                db2.close()
        except Exception:
            pass


def _add_background_push(
    background_tasks: BackgroundTasks,
    tokens: List[str],
    title: str,
    body: str,
    data: dict,
) -> None:
    def _job():
        try:
            result = send_push_to_tokens(tokens, title=title, body=body, data=data)
            invalids = (result or {}).get("invalid_tokens") or []
            if invalids:
                _delete_invalid_tokens(invalids)
        except Exception as e:
            print("❌ Error enviando push (background):", str(e))

    background_tasks.add_task(_job)


def _apply_forfeit_if_expired(db: Session) -> int:
    """
    Regla: el desafiado tiene 3 días para aceptar/rechazar.
    Si vence y sigue Pendiente -> pierde posición automáticamente (gana retador).
    """
    now = datetime.utcnow()
    limite = now - timedelta(days=3)

    expired = (
        db.query(Desafio)
        .filter(
            Desafio.estado == "Pendiente",
            Desafio.created_at <= limite,
        )
        .all()
    )

    if not expired:
        return 0

    updated = 0
    for d in expired:
        retadora = db.query(Pareja).filter(Pareja.id == d.retadora_pareja_id).first()
        retada = db.query(Pareja).filter(Pareja.id == d.retada_pareja_id).first()
        if not retadora or not retada:
            continue

        # no mezclar categoría
        if not _same_category(db, retadora, retada):
            continue

        d.pos_retadora_old = retadora.posicion_actual
        d.pos_retada_old = retada.posicion_actual

        # gana retador por forfeit
        d.estado = "Jugado"
        d.ganador_pareja_id = retadora.id
        d.fecha_jugado = date.today()

        # aplicar swap como si retador ganó
        if retadora.posicion_actual is not None and retada.posicion_actual is not None:
            if retadora.grupo != retada.grupo and _interdivision_allowed(db, retadora, retada):
                old_retadora_grupo = retadora.grupo
                old_retadora_pos = retadora.posicion_actual

                retadora.grupo = retada.grupo
                retadora.posicion_actual = retada.posicion_actual

                retada.grupo = old_retadora_grupo
                retada.posicion_actual = old_retadora_pos

                d.swap_aplicado = True
                d.ranking_aplicado = True
            else:
                retadora.posicion_actual, retada.posicion_actual = (
                    retada.posicion_actual,
                    retadora.posicion_actual,
                )
                d.swap_aplicado = True
                d.ranking_aplicado = True

        updated += 1

    if updated:
        db.commit()

    return updated


# ----------------- Endpoints -----------------
@router.get("/mi-dupla")
def mi_dupla(
    db: Session = Depends(get_db),
    jugador_actual: Jugador = Depends(get_current_jugador),
):
    p = (
        db.query(Pareja)
        .filter(
            Pareja.activo.is_(True),
            or_(
                Pareja.jugador1_id == jugador_actual.id,
                Pareja.jugador2_id == jugador_actual.id,
            ),
        )
        .order_by(Pareja.id.desc())
        .first()
    )

    if not p:
        raise HTTPException(status_code=404, detail="No tenés una DUPLA activa asignada.")

    etiqueta = _pareja_label(db, p)
    nombre = getattr(p, "nombre", None)

    return {
        "id": p.id,
        "etiqueta": etiqueta,
        "nombre": nombre,
        "grupo": getattr(p, "grupo", None),
        "posicion": getattr(p, "posicion_actual", None),
    }


@router.get("/mis-proximos", response_model=List[DesafioResponse])
def mis_proximos(
    db: Session = Depends(get_db),
    current_jugador: Jugador = Depends(get_current_jugador),
):
    _apply_forfeit_if_expired(db)

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
    _apply_forfeit_if_expired(db)

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
        .order_by(Desafio.fecha.desc(), Desafio.hora.desc(), Desafio.id.desc())
        .all()
    )
    return desafios


@router.get("/proximos", response_model=List[DesafioResponse])
def listar_proximos_desafios(db: Session = Depends(get_db)):
    _apply_forfeit_if_expired(db)

    desafios = (
        db.query(Desafio)
        .filter(Desafio.estado.in_(["Pendiente", "Aceptado"]))
        .order_by(Desafio.fecha.asc(), Desafio.hora.asc())
        .all()
    )
    return desafios


# ✅✅✅ NUEVO: MURO (global por jugar + mis jugados)
@router.get("/muro", response_model=List[DesafioResponse])
def muro_desafios(
    db: Session = Depends(get_db),
    jugador_actual: Jugador = Depends(get_current_jugador),
):
    """
    Muro:
      - Global por jugar: Pendiente/Aceptado (de todos)
      - Mis jugados: Jugado (solo los del usuario)
    Devuelve sin duplicar por id.
    """
    _apply_forfeit_if_expired(db)

    # 1) Global por jugar (todos)
    global_por_jugar = (
        db.query(Desafio)
        .filter(Desafio.estado.in_(["Pendiente", "Aceptado"]))
        .order_by(Desafio.fecha.desc(), Desafio.hora.desc(), Desafio.id.desc())
        .all()
    )

    # 2) Mis jugados (histórico)
    mis_parejas_ids = (
        db.query(Pareja.id)
        .filter(
            or_(
                Pareja.jugador1_id == jugador_actual.id,
                Pareja.jugador2_id == jugador_actual.id,
            )
        )
        .all()
    )
    mis_ids = {pid for (pid,) in mis_parejas_ids}

    mis_jugados = []
    if mis_ids:
        mis_jugados = (
            db.query(Desafio)
            .filter(
                Desafio.estado == "Jugado",
                or_(
                    Desafio.retadora_pareja_id.in_(list(mis_ids)),
                    Desafio.retada_pareja_id.in_(list(mis_ids)),
                ),
            )
            .order_by(Desafio.fecha_jugado.desc(), Desafio.fecha.desc(), Desafio.hora.desc(), Desafio.id.desc())
            .all()
        )

    # 3) Dedup por id
    seen = set()
    out: List[Desafio] = []
    for d in list(global_por_jugar) + list(mis_jugados):
        if d.id in seen:
            continue
        seen.add(d.id)
        out.append(d)

    return out


@router.post("/", response_model=DesafioResponse, status_code=status.HTTP_201_CREATED)
def crear_desafio(
    payload: DesafioCreateAuto,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    jugador_actual: Jugador = Depends(get_current_jugador),
):
    _apply_forfeit_if_expired(db)

    # ✅ retadora automática por token
    retadora = (
        db.query(Pareja)
        .filter(
            Pareja.activo.is_(True),
            or_(
                Pareja.jugador1_id == jugador_actual.id,
                Pareja.jugador2_id == jugador_actual.id,
            ),
        )
        .order_by(Pareja.id.desc())
        .first()
    )
    if not retadora:
        raise HTTPException(
            status_code=400,
            detail="Tu cuenta no tiene una DUPLA activa asignada. Contactá al admin.",
        )

    retada = (
        db.query(Pareja)
        .filter(Pareja.id == payload.retada_pareja_id, Pareja.activo.is_(True))
        .first()
    )
    if not retada:
        raise HTTPException(status_code=404, detail="Dupla desafiada no encontrada o inactiva.")

    if retadora.id == retada.id:
        raise HTTPException(status_code=400, detail="No podés desafiar a tu misma dupla.")

    hora_parsed = _parse_hora(str(payload.hora))
    _ensure_hora_redonda(hora_parsed)

    # ✅ REGLAS DURAS (siempre)
    _validate_desafio_rules(db, retadora, retada, payload.fecha)

    label_retadora = _pareja_label(db, retadora)
    label_retada = _pareja_label(db, retada)
    titulo_desafio = f"{label_retadora} vs {label_retada}"

    nuevo_desafio = Desafio(
        retadora_pareja_id=retadora.id,
        retada_pareja_id=retada.id,
        fecha=payload.fecha,
        hora=hora_parsed,
        observacion=payload.observacion,
        estado="Pendiente",
        titulo_desafio=titulo_desafio,
    )

    db.add(nuevo_desafio)
    db.commit()
    db.refresh(nuevo_desafio)

    recipients: Set[int] = {
        retada.jugador1_id,
        retada.jugador2_id,
        retadora.jugador1_id,
        retadora.jugador2_id,
        jugador_actual.id,
    }

    token_list = _tokens_by_players(db, recipients)

    if token_list:
        title = "🆕 Nuevo desafío"
        body = (
            f"⏱ {payload.fecha.strftime('%d/%m')} {str(hora_parsed)[:5]}\n"
            f"🎾 {titulo_desafio}\n"
            f"👉 Toca para ver el detalle"
        )

        _add_background_push(
            background_tasks,
            token_list,
            title=title,
            body=body,
            data={
                "type": "desafio",
                "event": "created",
                "desafio_id": str(nuevo_desafio.id),
                "estado": str(nuevo_desafio.estado),
                "fecha": str(nuevo_desafio.fecha),
                "hora": str(nuevo_desafio.hora),
                "retadora_pareja_id": str(retadora.id),
                "retada_pareja_id": str(retada.id),
            },
        )

    return nuevo_desafio


@router.post("/{desafio_id}/aceptar", response_model=DesafioResponse)
def aceptar_desafio(desafio_id: int, db: Session = Depends(get_db)):
    _apply_forfeit_if_expired(db)

    desafio = db.query(Desafio).filter(Desafio.id == desafio_id).first()
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafío no encontrado.")
    if desafio.estado == "Jugado":
        raise HTTPException(status_code=400, detail="No se puede aceptar un desafío que ya fue jugado.")
    if desafio.estado != "Pendiente":
        raise HTTPException(status_code=400, detail="Solo se puede aceptar si está Pendiente.")

    desafio.estado = "Aceptado"
    db.commit()
    db.refresh(desafio)
    return desafio


@router.post("/{desafio_id}/rechazar", response_model=DesafioResponse)
def rechazar_desafio(desafio_id: int, db: Session = Depends(get_db)):
    _apply_forfeit_if_expired(db)

    desafio = db.query(Desafio).filter(Desafio.id == desafio_id).first()
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafío no encontrado.")
    if desafio.estado == "Jugado":
        raise HTTPException(status_code=400, detail="No se puede rechazar un desafío que ya fue jugado.")
    if desafio.estado == "Rechazado":
        raise HTTPException(status_code=400, detail="Este desafío ya está rechazado.")
    if desafio.estado != "Pendiente":
        raise HTTPException(status_code=400, detail="Solo se puede rechazar si está Pendiente.")

    desafio.estado = "Rechazado"
    db.commit()
    db.refresh(desafio)
    return desafio


@router.patch("/{desafio_id}/reprogramar", response_model=DesafioResponse)
def reprogramar_desafio(
    desafio_id: int,
    payload: ReprogramarPayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    jugador_actual: Jugador = Depends(get_current_jugador),
):
    _apply_forfeit_if_expired(db)

    desafio = db.query(Desafio).filter(Desafio.id == desafio_id).first()
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafío no encontrado.")

    if desafio.estado != "Pendiente":
        raise HTTPException(status_code=400, detail="Solo se puede reprogramar si el desafío está Pendiente.")

    retadora = db.query(Pareja).filter(Pareja.id == desafio.retadora_pareja_id).first()
    retada = db.query(Pareja).filter(Pareja.id == desafio.retada_pareja_id).first()
    if not retadora or not retada:
        raise HTTPException(status_code=404, detail="Parejas del desafío no encontradas")

    if jugador_actual.id not in (
        retadora.jugador1_id,
        retadora.jugador2_id,
        retada.jugador1_id,
        retada.jugador2_id,
    ):
        raise HTTPException(status_code=403, detail="No pertenecés a este desafío.")

    nueva_hora = _parse_hora(payload.hora)
    _ensure_hora_redonda(nueva_hora)

    # ✅ revalidar reglas, excluyendo el desafío actual
    _validate_desafio_rules(db, retadora, retada, payload.fecha, exclude_desafio_id=desafio.id)

    desafio.fecha = payload.fecha
    desafio.hora = nueva_hora

    db.commit()
    db.refresh(desafio)

    recipients: Set[int] = {
        retada.jugador1_id,
        retada.jugador2_id,
        retadora.jugador1_id,
        retadora.jugador2_id,
        jugador_actual.id,
    }

    token_list = _tokens_by_players(db, recipients)

    if token_list:
        label_retadora = _pareja_label(db, retadora)
        label_retada = _pareja_label(db, retada)
        titulo = f"{label_retadora} vs {label_retada}"

        title = "📅 Desafío reprogramado"
        body = (
            f"🗓 {payload.fecha.strftime('%d/%m')} {str(nueva_hora)[:5]}\n"
            f"🎾 {titulo}\n"
            f"👉 Toca para ver el detalle"
        )

        _add_background_push(
            background_tasks,
            token_list,
            title=title,
            body=body,
            data={
                "type": "desafio",
                "event": "rescheduled",
                "desafio_id": str(desafio.id),
                "estado": str(desafio.estado),
                "fecha": str(desafio.fecha),
                "hora": str(desafio.hora),
                "retadora_pareja_id": str(retadora.id),
                "retada_pareja_id": str(retada.id),
            },
        )

    return desafio


def _gana_retador(data: ResultadoSets) -> bool:
    sets_ret = 0
    sets_des = 0

    if data.set1_retador == data.set1_desafiado:
        raise HTTPException(status_code=400, detail="Set 1 no puede quedar empatado.")
    if data.set2_retador == data.set2_desafiado:
        raise HTTPException(status_code=400, detail="Set 2 no puede quedar empatado.")

    if data.set1_retador > data.set1_desafiado:
        sets_ret += 1
    else:
        sets_des += 1

    if data.set2_retador > data.set2_desafiado:
        sets_ret += 1
    else:
        sets_des += 1

    if sets_ret == sets_des:
        if data.set3_retador is None or data.set3_desafiado is None:
            raise HTTPException(
                status_code=400,
                detail="Falta cargar el Set 3 (Super Tie-Break) porque van 1-1.",
            )
        if data.set3_retador == data.set3_desafiado:
            raise HTTPException(status_code=400, detail="Set 3 no puede quedar empatado.")

        if data.set3_retador > data.set3_desafiado:
            sets_ret += 1
        else:
            sets_des += 1

    return sets_ret > sets_des


def _fmt_sets(data: ResultadoSets) -> str:
    s = []
    s.append(f"{data.set1_retador}-{data.set1_desafiado}")
    s.append(f"{data.set2_retador}-{data.set2_desafiado}")
    if data.set3_retador is not None and data.set3_desafiado is not None:
        s.append(f"{data.set3_retador}-{data.set3_desafiado}")
    return " | ".join(s)


@router.post("/{desafio_id}/resultado", response_model=DesafioResponse)
def cargar_resultado(
    desafio_id: int,
    data: ResultadoSets,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    jugador_actual: Jugador = Depends(get_current_jugador),
):
    _apply_forfeit_if_expired(db)

    desafio = db.query(Desafio).filter(Desafio.id == desafio_id).first()
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafío no encontrado")
    if desafio.estado == "Jugado":
        raise HTTPException(status_code=400, detail="Este desafío ya está Jugado")

    retadora = db.query(Pareja).filter(Pareja.id == desafio.retadora_pareja_id).first()
    retada = db.query(Pareja).filter(Pareja.id == desafio.retada_pareja_id).first()
    if not retadora or not retada:
        raise HTTPException(status_code=404, detail="Parejas del desafío no encontradas")

    # ✅ No cruzar Masculino/Femenino
    if not _same_category(db, retadora, retada):
        raise HTTPException(status_code=400, detail="No se puede jugar entre Masculino y Femenino.")

    # ✅ Si es interdivisión, debe ser permitido
    if retadora.grupo != retada.grupo and not _interdivision_allowed(db, retadora, retada):
        raise HTTPException(status_code=400, detail="No se puede aplicar resultado: interdivisión no permitida.")

    if jugador_actual.id not in (
        retadora.jugador1_id,
        retadora.jugador2_id,
        retada.jugador1_id,
        retada.jugador2_id,
    ):
        raise HTTPException(status_code=403, detail="No pertenecés a este desafío.")

    retador_gana = _gana_retador(data)
    ganador_id = retadora.id if retador_gana else retada.id

    desafio.pos_retadora_old = retadora.posicion_actual
    desafio.pos_retada_old = retada.posicion_actual

    puesto_en_juego = None
    if desafio.pos_retadora_old is not None and desafio.pos_retada_old is not None:
        puesto_en_juego = min(desafio.pos_retadora_old, desafio.pos_retada_old)

    desafio.estado = "Jugado"
    desafio.ganador_pareja_id = ganador_id

    desafio.set1_retador = data.set1_retador
    desafio.set1_desafiado = data.set1_desafiado
    desafio.set2_retador = data.set2_retador
    desafio.set2_desafiado = data.set2_desafiado
    desafio.set3_retador = data.set3_retador
    desafio.set3_desafiado = data.set3_desafiado

    desafio.fecha_jugado = data.fecha_jugado or date.today()

    # ✅ Aplicación de ranking:
    # - mismo grupo: si gana retador => swap posiciones
    # - interdivisión B->A: si gana retador => swap grupo+pos entre ambos
    if retador_gana and not desafio.swap_aplicado:
        if retadora.posicion_actual is not None and retada.posicion_actual is not None:
            if retadora.grupo != retada.grupo and _interdivision_allowed(db, retadora, retada):
                old_retadora_grupo = retadora.grupo
                old_retadora_pos = retadora.posicion_actual

                retadora.grupo = retada.grupo
                retadora.posicion_actual = retada.posicion_actual

                retada.grupo = old_retadora_grupo
                retada.posicion_actual = old_retadora_pos

                desafio.swap_aplicado = True
            else:
                retadora.posicion_actual, retada.posicion_actual = (
                    retada.posicion_actual,
                    retadora.posicion_actual,
                )
                desafio.swap_aplicado = True
        else:
            desafio.swap_aplicado = False
    else:
        desafio.swap_aplicado = False

    desafio.ranking_aplicado = True

    db.commit()
    db.refresh(desafio)

    recipients: Set[int] = {
        retada.jugador1_id,
        retada.jugador2_id,
        retadora.jugador1_id,
        retadora.jugador2_id,
        jugador_actual.id,
    }

    token_list = _tokens_by_players(db, recipients)

    if token_list:
        label_retadora = _pareja_label(db, retadora)
        label_retada = _pareja_label(db, retada)
        titulo = f"{label_retadora} vs {label_retada}"

        ganador_label = label_retadora if ganador_id == retadora.id else label_retada
        sets_txt = _fmt_sets(data)

        title = "🏁 Resultado cargado"
        body = (
            f"🏆 Ganó: {ganador_label}\n"
            f"🎾 Sets: {sets_txt}\n"
            + (f"🏅 Puesto en juego: N.º {puesto_en_juego}\n" if puesto_en_juego else "")
            + "👉 Toca para ver el detalle"
        )

        _add_background_push(
            background_tasks,
            token_list,
            title=title,
            body=body,
            data={
                "type": "desafio",
                "event": "result",
                "desafio_id": str(desafio.id),
                "ganador_pareja_id": str(desafio.ganador_pareja_id or ""),
                "swap_aplicado": str(bool(desafio.swap_aplicado)),
                "pos_retadora_old": str(desafio.pos_retadora_old or ""),
                "pos_retada_old": str(desafio.pos_retada_old or ""),
                "puesto_en_juego": str(puesto_en_juego or ""),
                "set1": f"{data.set1_retador}-{data.set1_desafiado}",
                "set2": f"{data.set2_retador}-{data.set2_desafiado}",
                "set3": (
                    f"{data.set3_retador}-{data.set3_desafiado}"
                    if data.set3_retador is not None and data.set3_desafiado is not None
                    else ""
                ),
                "titulo": titulo,
            },
        )

    return desafio


@router.get("/pareja/{pareja_id}", response_model=List[DesafioHistorialItem])
def listar_desafios_pareja(pareja_id: int, db: Session = Depends(get_db)):
    _apply_forfeit_if_expired(db)

    desafios = (
        db.query(Desafio)
        .filter(
            or_(
                Desafio.retadora_pareja_id == pareja_id,
                Desafio.retada_pareja_id == pareja_id,
            )
        )
        .order_by(Desafio.fecha.desc(), Desafio.hora.desc(), Desafio.id.desc())
        .all()
    )
    return desafios


# ✅✅✅ NUEVO: detalle público para muro (sin 403)
@router.get("/{desafio_id}/publico", response_model=DesafioResponse)
def obtener_desafio_publico(
    desafio_id: int,
    db: Session = Depends(get_db),
    jugador_actual: Jugador = Depends(get_current_jugador),
):
    _apply_forfeit_if_expired(db)

    desafio = db.query(Desafio).filter(Desafio.id == desafio_id).first()
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafío no encontrado.")

    # Solo lectura: no validamos pertenencia
    return desafio


@router.get("/{desafio_id}", response_model=DesafioResponse)
def obtener_desafio(
    desafio_id: int,
    db: Session = Depends(get_db),
    jugador_actual: Jugador = Depends(get_current_jugador),
):
    _apply_forfeit_if_expired(db)

    desafio = db.query(Desafio).filter(Desafio.id == desafio_id).first()
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafío no encontrado.")

    parejas_del_jugador = (
        db.query(Pareja.id)
        .filter(
            or_(
                Pareja.jugador1_id == jugador_actual.id,
                Pareja.jugador2_id == jugador_actual.id,
            )
        )
        .all()
    )
    mis_parejas_ids = {pid for (pid,) in parejas_del_jugador}

    if desafio.retadora_pareja_id not in mis_parejas_ids and desafio.retada_pareja_id not in mis_parejas_ids:
        raise HTTPException(status_code=403, detail="No tenés acceso a este desafío.")

    return desafio
