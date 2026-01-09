# database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# ✅ Base vive acá (evita circular import)
Base = declarative_base()

def _clean_db_url(url: str) -> str:
    # quita espacios y comillas por si Render lo guarda con ""
    return (url or "").strip().strip('"').strip("'")

# ✅ Primero intentamos por ENV (Render)
DATABASE_URL = _clean_db_url(os.getenv("DATABASE_URL"))

# ✅ Fallback (solo para local si no existe env)
if not DATABASE_URL:
    DATABASE_URL = _clean_db_url(
        "postgresql://neondb_owner:npg_ecQ2hPd1AvBE@ep-bold-term-aclik95n-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    )

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    # Import diferido para que NO haya circular import
    import models  # noqa: F401
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
