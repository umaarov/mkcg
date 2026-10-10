from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, event
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from .config import settings

Base = declarative_base()
engine = create_engine(settings.db_url, connect_args={"check_same_thread": False, "timeout": 30}, future=True)


@event.listens_for(engine, "connect")
def _pragmas(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA busy_timeout=30000")  # concurrent cases write while others are being analysed
    cur.close()


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(60), unique=True, nullable=False)
    name = Column(String(120), nullable=False)
    role = Column(String(30), nullable=False)  # officer | analyst | committee | admin
    password_hash = Column(String(200), nullable=False)


class Case(Base):
    __tablename__ = "cases"
    id = Column(String(20), primary_key=True)
    created = Column(DateTime, default=now)
    updated = Column(DateTime, default=now, onupdate=now)
    owner = Column(String(60))
    applicant = Column(String(200), default="")
    tin = Column(String(20), default="")
    amount = Column(Float, default=0)
    term = Column(Integer, default=12)
    lang = Column(String(8), default="uz")
    status = Column(String(30), default="UPLOADED")  # UPLOADED EXTRACTING NEEDS_REVIEW ANALYZING ANALYZED DECIDED FAILED
    sample = Column(String(60), default="")
    result = Column(JSON, default=dict)       # facts, rules, score, recon, memo
    steps = Column(JSON, default=list)        # pipeline step log with timings
    decision = Column(JSON, default=None)
    docs = relationship("Document", back_populates="case", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    case_id = Column(String(20), ForeignKey("cases.id"))
    filename = Column(String(200))
    path = Column(String(400))
    doc_type = Column(String(30), default="unknown")
    lang = Column(String(10), default="")
    source = Column(String(20), default="")
    pages = Column(Integer, default=0)
    ocr_conf = Column(Float, default=0)
    seconds = Column(Float, default=0)
    extraction = Column(JSON, default=dict)   # fields, transactions, validations, methods
    case = relationship("Case", back_populates="docs")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id = Column(Integer, primary_key=True)
    ts = Column(DateTime, default=now)
    actor = Column(String(60))
    action = Column(String(60))
    case_id = Column(String(20), index=True)
    payload = Column(Text)
    prev_hash = Column(String(64))
    hash = Column(String(64))


def init_db():
    Base.metadata.create_all(engine)


@contextmanager
def session():
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
