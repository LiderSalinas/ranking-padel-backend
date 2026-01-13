# schemas/player.py
from datetime import date, time
from typing import List, Optional

from pydantic import BaseModel


class JugadorBase(BaseModel):
    nombre: str
    apellido: str
    telefono: str
    email: str
    foto_url: Optional[str] = None


class JugadorSimple(JugadorBase):
    id: int


class JugadorListaResponse(JugadorSimple):
    """
    Para listar jugadores (GET /jugadores/)

    Incluye estadísticas básicas.
    """
    grupo_principal: Optional[str] = None
    partidos_jugados: int
    victorias: int
    derrotas: int
    retiros: int = 0  # ✅ nuevo


class JugadorDesafioItem(BaseModel):
    """
    Item de un desafío en el historial de un jugador.
    """
    id: int
    fecha: date
    hora: time
    estado: str
    titulo_desafio: str
    grupo: str
    pareja_id: int
    rol: str          # "retadora" / "retada"
    es_ganado: bool


class JugadorDetalleResponse(JugadorSimple):
    """
    Para detalle de jugador con historial
    (GET /jugadores/{jugador_id}/detalle)
    """
    grupo_principal: Optional[str] = None
    partidos_jugados: int
    victorias: int
    derrotas: int
    retiros: int = 0  # ✅ nuevo
    desafios: List[JugadorDesafioItem]
