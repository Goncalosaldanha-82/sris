from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings

database_url = settings.database_url.replace("postgresql://", "postgresql+psycopg://", 1) if settings.database_url.startswith("postgresql://") else settings.database_url

connect_args = (
{"check_same_thread": False}
if database_url.startswith("sqlite")
else {}
)

engine = create_engine(
database_url,
pool_pre_ping=True,
future=True,
connect_args=connect_args,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
