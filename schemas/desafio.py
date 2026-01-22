# schemas/desafio.py
from __future__ import annotations

from datetime import date, datetime, time
from typing import Optional

from pydantic import BaseModel, ConfigDict


class DesafioCreate(BaseModel):
    retadora_pareja_id: Optional [int] = None
    retada_pareja_id: int
    fecha: date
    hora: time
    observacion: Optional[str] = None


class DesafioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    retadora_pareja_id: int
    retada_pareja_id: int
    ganador_pareja_id: Optional[int] = None

    estado: str
    fecha: date
    hora: time
    observacion: Optional[str] = None

    limite_semana_ok: bool = True
    swap_aplicado: bool = False
    pos_retadora_old: Optional[int] = None
    pos_retada_old: Optional[int] = None
    ranking_aplicado: bool = False

    titulo_desafio: str

    # ✅ sets persistidos
    set1_retador: Optional[int] = None
    set1_desafiado: Optional[int] = None
    set2_retador: Optional[int] = None
    set2_desafiado: Optional[int] = None
    set3_retador: Optional[int] = None
    set3_desafiado: Optional[int] = None

    # ✅ fecha real de juego
    fecha_jugado: Optional[date] = None

    created_at: datetime
    updated_at: datetime

    # opcional futuro / calculado
    puesto_en_juego: Optional[int] = None


class DesafioHistorialItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha: date
    hora: time
    estado: str
    ganador_pareja_id: Optional[int] = None
    titulo_desafio: str

    fecha_jugado: Optional[date] = None
    set1_retador: Optional[int] = None
    set1_desafiado: Optional[int] = None
    set2_retador: Optional[int] = None
    set2_desafiado: Optional[int] = None
    set3_retador: Optional[int] = None
    set3_desafiado: Optional[int] = None
