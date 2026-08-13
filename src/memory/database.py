import os
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, String, Text, DateTime, Boolean, Integer, Index
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import QueuePool

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
print("[DB DEBUG] DATABASE_URL present:", bool(DATABASE_URL))

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

# 1. Define Base BEFORE defining models
Base = declarative_base()

# 2. Define Models
class SeenUrl(Base):
    __tablename__ = "seen_urls"
    url = Column(String, primary_key=True)
    first_seen = Column(DateTime, default=datetime.utcnow)


class DailyJobMatch(Base):
    __tablename__ = "daily_job_matches"
    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String)
    title = Column(String)
    company = Column(String)
    description = Column(Text)
    source = Column(String, default="web")  # "indeed" | "wellfound" | "naukri" | "linkedin" | "web"
    score = Column(Integer, default=0)
    found_at = Column(DateTime, default=datetime.utcnow)
    sent = Column(Boolean, default=False)
    applied = Column(Boolean, default=False)

    __table_args__ = (
        Index("ix_daily_job_matches_sent", "sent"),
    )


class PlatformSession(Base):
    __tablename__ = "platform_sessions"
    platform = Column(String, primary_key=True)
    storage_state = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ApplyQueueItem(Base):
    __tablename__ = "apply_queue"
    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String, nullable=False)   # "naukri" | "wellfound"
    company = Column(String)
    role = Column(String)
    job_url = Column(String)
    status = Column(String, default="pending")  # "pending" | "applied" | "failed" | "needs_review"
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_apply_queue_status", "status"),
    )


# 3. Database Engine & Session Setup
connect_args = {}
engine_kwargs = {
    "poolclass": QueuePool,
    "pool_size": 5,
    "max_overflow": 10,
    "pool_pre_ping": True,
    "pool_recycle": 300,
}

if DATABASE_URL.startswith("postgresql"):
    connect_args = {
        "sslmode": "require",
        "connect_timeout": 10,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    }
    engine_kwargs["connect_args"] = connect_args

engine = create_engine(DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    print("[DB] Tables created successfully")