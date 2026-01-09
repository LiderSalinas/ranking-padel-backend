# core/settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # -----------------------------
    # Reglas del reglamento oficial
    # -----------------------------
    STRICT_RULES: bool = False  # si True, se aplican reglas duras

    # Máximo de puestos que se puede desafiar por encima
    MAX_SALTOS_DESAFIO: int = 3

    # Máximo de partidos por semana por pareja
    # (cuenta Pendiente, Aceptado y Jugado)
    MAX_PARTIDOS_SEMANA: int = 2

    # -----------------------------
    # Config JWT / Auth
    # -----------------------------
    JWT_SECRET_KEY: str = "CAMBIAME_POR_UNA_CLAVE_MUY_SECRETA"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 días

    # URL base del frontend (para armar el link mágico)
    FRONTEND_BASE_URL: str = "http://localhost:5173"

    # Configuración de Pydantic Settings (v2)
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
