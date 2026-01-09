# database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

Base = declarative_base()

DATABASE_URL = (
    os.getenv("DATABASE_URL")
    or "postgresql://neondb_owner:npg_ecQ2hPd1AvBE@ep-bold-term-aclik95n-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    # ✅ Importa models para registrar todas las tablas en Base.metadata
    import models  # noqa: F401
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
