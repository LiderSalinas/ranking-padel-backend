# schemas/pair.py
from datetime import date, time
from typing import List, Optional

from pydantic import BaseModel


# ---- Datos de jugadores usados en parejas ----
class JugadorDatos(BaseModel):
    nombre: str
    apellido: str
    telefono: str
    email: str


class JugadorEnPareja(JugadorDatos):
    id: int
    foto_url: Optional[str] = None  # ✅ NUEVO

    class Config:
        from_attributes = True


# ---- Crear pareja ----
class ParejaRegistro(BaseModel):
    jugador1: JugadorDatos
    jugador2: JugadorDatos
    capitan: int   # 1 ó 2
    grupo: str


# ---- Respuestas básicas de pareja ----
class ParejaResponse(BaseModel):
    id: int
    jugador1_id: int
    jugador2_id: int
    capitan_id: int
    grupo: str
    posicion_actual: int
    activo: bool

    class Config:
        from_attributes = True


# ---- Historial de pareja ----
class DesafioHistorialItem(BaseModel):
    id: int
    fecha: date
    hora: time
    estado: str
    titulo_desafio: str
    es_ganado: bool


class ParejaHistorialResponse(BaseModel):
    pareja_id: int
    grupo: str
    posicion_actual: int
    partidos_jugados: int
    victorias: int
    derrotas: int
    desafios: List[DesafioHistorialItem]


# ---- Detalle de pareja con jugadores ----
class ParejaDetalleResponse(BaseModel):
    pareja_id: int
    grupo: str
    posicion_actual: int
    activo: bool
    jugador1: JugadorEnPareja
    jugador2: JugadorEnPareja
    capitan: JugadorEnPareja
    partidos_jugados: int
    victorias: int
    derrotas: int


# ---- Parejas desafiables (para modal/crear desafío) ----
class ParejaDesafiableResponse(BaseModel):
    id: int
    nombre: str
    posicion_actual: int
    grupo: str  # ✅ faltaba

    class Config:
        from_attributes = True


# ---- Cards (vista pública tipo AppSheet) ----
class ParejaCardResponse(BaseModel):
    pareja_id: int
    grupo: str
    posicion_actual: int
    activo: bool

    nombre_pareja: str

    jugador1: JugadorEnPareja
    jugador2: JugadorEnPareja

    partidos_jugados: int
    victorias: int
    derrotas: int

    class Config:
        from_attributes = True
