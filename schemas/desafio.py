# schemas/desafios.py
from datetime import date, datetime, time
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class DesafioBase(BaseModel):
    retadora_pareja_id: int
    retada_pareja_id: int
    fecha: date
    hora: time
    observacion: Optional[str] = None


class DesafioCreate(DesafioBase):
    pass


class DesafioResultadoIn(BaseModel):
    # ✅ NUEVO: fecha real de juego (YYYY-MM-DD)
    fecha_jugado: Optional[date] = None

    set1_retador: int = Field(ge=0, le=7)
    set1_desafiado: int = Field(ge=0, le=7)

    set2_retador: int = Field(ge=0, le=7)
    set2_desafiado: int = Field(ge=0, le=7)

    # set 3 opcional (puede ser TB o set normal)
    set3_retador: Optional[int] = Field(default=None, ge=0, le=99)
    set3_desafiado: Optional[int] = Field(default=None, ge=0, le=99)


class DesafioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    retadora_pareja_id: int
    retada_pareja_id: int
    ganador_pareja_id: Optional[int] = None

    estado: str

    fecha: date
    hora: time
    observacion: Optional[str] = None

    limite_semana_ok: bool
    swap_aplicado: bool
    pos_retadora_old: Optional[int] = None
    pos_retada_old: Optional[int] = None
    ranking_aplicado: bool

    titulo_desafio: str

    # ✅ resultado
    set1_retador: Optional[int] = None
    set1_desafiado: Optional[int] = None
    set2_retador: Optional[int] = None
    set2_desafiado: Optional[int] = None
    set3_retador: Optional[int] = None
    set3_desafiado: Optional[int] = None
    fecha_jugado: Optional[date] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
