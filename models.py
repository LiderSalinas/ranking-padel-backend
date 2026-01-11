# models.py
from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Date,
    Time,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from database import Base


class PushToken(Base):
    __tablename__ = "push_tokens"

    id = Column(Integer, primary_key=True, index=True)
    jugador_id = Column(Integer, ForeignKey("jugadores.id"), nullable=False)
    fcm_token = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # ✅ MULTI-DEVICE: unique por (jugador_id, fcm_token)
    __table_args__ = (
        UniqueConstraint("jugador_id", "fcm_token", name="uq_push_tokens_jugador_fcm"),
    )

    jugador = relationship("Jugador", lazy="joined")


class Jugador(Base):
    __tablename__ = "jugadores"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    apellido = Column(String(100), nullable=False)
    telefono = Column(String(30), nullable=True)
    email = Column(String(150), nullable=True, unique=True, index=True)
    foto_url = Column(String(500), nullable=True)

    activo = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relaciones con pareja
    parejas_como_j1 = relationship(
        "Pareja",
        back_populates="jugador1",
        foreign_keys="Pareja.jugador1_id",
    )
    parejas_como_j2 = relationship(
        "Pareja",
        back_populates="jugador2",
        foreign_keys="Pareja.jugador2_id",
    )
    parejas_capitan = relationship(
        "Pareja",
        back_populates="capitan",
        foreign_keys="Pareja.capitan_id",
    )


class Pareja(Base):
    __tablename__ = "parejas"

    __table_args__ = (
        UniqueConstraint(
            "jugador1_id",
            "jugador2_id",
            "grupo",
            name="uq_pareja_jugadores_grupo",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    jugador1_id = Column(Integer, ForeignKey("jugadores.id"), nullable=False)
    jugador2_id = Column(Integer, ForeignKey("jugadores.id"), nullable=False)
    capitan_id = Column(Integer, ForeignKey("jugadores.id"), nullable=False)

    grupo = Column(String(1), nullable=False)
    posicion_actual = Column(Integer, nullable=True, index=True)

    activo = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    jugador1 = relationship(
        "Jugador",
        foreign_keys=[jugador1_id],
        back_populates="parejas_como_j1",
    )
    jugador2 = relationship(
        "Jugador",
        foreign_keys=[jugador2_id],
        back_populates="parejas_como_j2",
    )
    capitan = relationship(
        "Jugador",
        foreign_keys=[capitan_id],
        back_populates="parejas_capitan",
    )


class Desafio(Base):
    __tablename__ = "desafios"

    id = Column(Integer, primary_key=True, index=True)

    retadora_pareja_id = Column(Integer, ForeignKey("parejas.id"), nullable=False)
    retada_pareja_id = Column(Integer, ForeignKey("parejas.id"), nullable=False)

    ganador_pareja_id = Column(Integer, ForeignKey("parejas.id"), nullable=True)

    estado = Column(String(20), nullable=False, default="Pendiente")

    fecha = Column(Date, nullable=False)
    hora = Column(Time, nullable=False)

    observacion = Column(String(255), nullable=True)

    limite_semana_ok = Column(Boolean, default=True)
    swap_aplicado = Column(Boolean, default=False)
    pos_retadora_old = Column(Integer, nullable=True)
    pos_retada_old = Column(Integer, nullable=True)
    ranking_aplicado = Column(Boolean, default=False)

    titulo_desafio = Column(String(255), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    retadora = relationship(
        "Pareja",
        foreign_keys=[retadora_pareja_id],
        backref="desafios_como_retadora",
    )
    retada = relationship(
        "Pareja",
        foreign_keys=[retada_pareja_id],
        backref="desafios_como_retada",
    )
    ganador = relationship(
        "Pareja",
        foreign_keys=[ganador_pareja_id],
        backref="desafios_ganados",
    )
