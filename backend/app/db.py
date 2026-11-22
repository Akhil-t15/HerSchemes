import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_default_db = os.path.join(_backend_dir, "herscheme.db").replace("\\", "/")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_default_db}")

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
