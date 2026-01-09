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

    # Para que pueda leer desde el modelo SQLAlchemy (Pydantic v2)
    model_config = ConfigDict(from_attributes=True)
     


class DesafioResultadoPayload(BaseModel):
    """
    Payload para cargar el resultado de un desafío.
    Lo usamos en:
      POST /desafios/{desafio_id}/resultado
    """
    estado: str = "Jugado"
    ganador_pareja_id: int


class DesafioHistorialItem(BaseModel):
    """
    Item para el historial de desafíos de una pareja.

    Lo usamos en:
      GET /desafios/pareja/{pareja_id}
    y también puede ser útil en otros endpoints de historial.
    Dejamos varios campos como opcionales para no romper nada.
    """
    id: int
    fecha: date
    hora: time
    estado: str
    titulo_desafio: str

    # Datos adicionales (opcionales)
    grupo: Optional[str] = None
    retadora_pareja_id: Optional[int] = None
    retada_pareja_id: Optional[int] = None
    ganador_pareja_id: Optional[int] = None
    pareja_id: Optional[int] = None
    rol: Optional[str] = None   # "retadora" / "retada"
    es_ganado: Optional[bool] = None
