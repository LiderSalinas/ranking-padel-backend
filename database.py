# database.py

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from models import Base 
def init_db():
    Base.metadata.create_all(bind=engine)

# 🔗 URL directa de tu Neon (la que me mostraste en la captura)
DATABASE_URL = ("postgresql://neondb_owner:npg_ecQ2hPd1AvBE@ep-bold-term-aclik95n-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
)

# Creamos el engine con pre_ping para evitar errores de conexión cerrada
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # si Neon cierra la conexión, SQLAlchemy la reabre
)

# Sesiones
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base de los modelos
Base = declarative_base()


# Dependencia para obtener la sesión en FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
