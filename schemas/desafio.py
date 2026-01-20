# schemas/desafio.py
from datetime import date, time, datetime
from typing import Optional

from pydantic import BaseModel
from pydantic import ConfigDict


class DesafioBase(BaseModel):
    retadora_pareja_id: int
    retada_pareja_id: int
    fecha: date
    hora: time
    observacion: Optional[str] = None


class DesafioCreate(DesafioBase):
    """
    Payload para crear un desafío.
    """
    pass


class DesafioResponse(DesafioBase):
    """
    Respuesta completa de un desafío (como viene de la BD).
    """
    id: int
    estado: str
    limite_semana_ok: bool
    swap_aplicado: bool
    pos_retadora_old: Optional[int] = None
    pos_retada_old: Optional[int] = None
    ranking_aplicado: bool
    titulo_desafio: str
    created_at: datetime
    updated_at: datetime
    ganador_pareja_id: Optional[int] = None

    # ✅ NUEVO: sets + fecha jugado (para detalle ideal)
    set1_retador: Optional[int] = None
    set1_desafiado: Optional[int] = None
    set2_retador: Optional[int] = None
    set2_desafiado: Optional[int] = None
    set3_retador: Optional[int] = None
    set3_desafiado: Optional[int] = None
    fecha_jugado: Optional[date] = None

    model_config = ConfigDict(from_attributes=True)


class DesafioResultadoPayload(BaseModel):
    """
    (Si lo usás en otro endpoint, lo dejamos intacto)
    """
    estado: str = "Jugado"
    ganador_pareja_id: int


class DesafioHistorialItem(BaseModel):
    id: int
    fecha: date
    hora: time
    estado: str
    titulo_desafio: str

    grupo: Optional[str] = None
    retadora_pareja_id: Optional[int] = None
    retada_pareja_id: Optional[int] = None
    ganador_pareja_id: Optional[int] = None
    pareja_id: Optional[int] = None
    rol: Optional[str] = None
    es_ganado: Optional[bool] = None
