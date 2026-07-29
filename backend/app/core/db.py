from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings

database_url = settings.database_url

# Railway fornece "postgresql://", mas o projeto utiliza Psycopg 3.
if database_url.startswith("postgresql://"):
database_url = database_url.replace(
"postgresql://",
"postgresql+psycopg://",
1,
)

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
