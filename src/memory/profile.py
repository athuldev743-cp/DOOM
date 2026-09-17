import json
import time
from sqlalchemy import Column, Integer, String, Text, DateTime, func
from sqlalchemy.sql import func as sql_func
from src.memory.database import Base, SessionLocal


class UserProfile(Base):
    __tablename__ = "user_profile"
    id = Column(Integer, primary_key=True)
    key = Column(String(200), unique=True, nullable=False)
    value = Column(Text, nullable=False)
    category = Column(String(100), default="general")
    updated_at = Column(DateTime, server_default=sql_func.now())


class Contact(Base):
    __tablename__ = "contacts"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    phone = Column(String(50), nullable=True)
    whatsapp = Column(String(50), nullable=True)
    email = Column(String(200), nullable=True)
    relationship = Column(String(200), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=sql_func.now())


class ProfileManager:
    # Class-level flag: the seed check only needs to happen ONCE per
    # process lifetime, not once per instantiation. Previously every
    # ProfileManager() call re-ran a DB query just to check this.
    _seeded_this_process = False

    def __init__(self):
        if not ProfileManager._seeded_this_process:
            self._seed_default_projects()
            ProfileManager._seeded_this_process = True

    def set(self, key: str, value: str, category: str = "general"):
        db = SessionLocal()
        try:
            existing = db.query(UserProfile).filter_by(key=key).first()
            if existing:
                existing.value = value
                existing.category = category
            else:
                db.add(UserProfile(key=key, value=value, category=category))
            db.commit()
        finally:
            db.close()

    def get(self, key: str) -> str:
        db = SessionLocal()
        try:
            p = db.query(UserProfile).filter_by(key=key).first()
            return p.value if p else None
        finally:
            db.close()

    def get_all(self) -> dict:
        db = SessionLocal()
        try:
            all_p = db.query(UserProfile).all()
            return {p.key: p.value for p in all_p}
        finally:
            db.close()

    def get_projects(self) -> list:
        raw = self.get("projects_knowledge_base")
        if not raw:
            return []
        try:
            return json.loads(raw)
        except Exception:
            return []

 

    def get_context_dict(self, max_chars: int = 2500, max_entry_chars: int = 400) -> dict:
     t0 = time.perf_counter()
     db = SessionLocal()
     t1 = time.perf_counter()
     print(f"[DB TIMING] session acquire: {(t1-t0)*1000:.1f}ms")
     try:
        rows = (
            db.query(UserProfile.key, UserProfile.value, UserProfile.updated_at)
            .filter(sql_func.length(UserProfile.value) <= max_entry_chars)
            .order_by(UserProfile.updated_at.desc())
            .all()
        )
        t2 = time.perf_counter()
        print(f"[DB TIMING] query execute: {(t2-t1)*1000:.1f}ms")

        selected = {}
        total_chars = 0
        for key, value, _updated_at in rows:
            entry_chars = len(key) + len(value) + 4
            if total_chars + entry_chars > max_chars:
                continue
            selected[key] = value
            total_chars += entry_chars

        return selected
     finally:
        db.close()

    def _seed_default_projects(self):
        if not self.get("projects_knowledge_base"):
            projects = [
                {
                    "name": "DOOM Autonomous AI Voice Assistant",
                    "tech": "Python, FastAPI, Gemini/LLaMA 3.3 70B, ChromaDB, Edge-TTS, Gmail API, Neon PostgreSQL, WebSockets",
                    "highlights": "Built a fully autonomous voice assistant with tool calling, Gmail application dispatch, RAG, and memory persistence.",
                    "relevant_for": ["ai", "backend", "llm", "fastapi", "python", "automation"]
                },
                {
                    "name": "Ekabhumi E-Commerce Platform",
                    "tech": "React, Node.js/Python, PostgreSQL, Dual Payment Gateway (Razorpay & Worldline), Docker",
                    "highlights": "Engineered full stack e-commerce platform with dual payment integration, order tracking, and production cloud deployment.",
                    "relevant_for": ["fullstack", "frontend", "react", "payment", "e-commerce", "node"]
                },
                {
                    "name": "Instagram AI Content Agent",
                    "tech": "Python, LLMs, Instagram Graph API, React Dashboard, Render",
                    "highlights": "Developed an autonomous social media marketing agent that generates captions, designs visual media, and auto-schedules posts.",
                    "relevant_for": ["ai", "fullstack", "marketing", "api", "automation"]
                }
            ]
            self.set("projects_knowledge_base", json.dumps(projects), "career")

    def add_contact(self, name: str, phone: str = None, relationship: str = None, email: str = None, notes: str = None) -> str:
        db = SessionLocal()
        try:
            existing = db.query(Contact).filter(Contact.name.ilike(f"%{name}%")).first()
            if existing:
                if phone: existing.phone = phone
                if relationship: existing.relationship = relationship
                if email: existing.email = email
                if notes: existing.notes = notes
            else:
                db.add(Contact(name=name, phone=phone, whatsapp=phone, relationship=relationship, email=email, notes=notes))
            db.commit()
            return f"✓ Contact saved: {name}"
        finally:
            db.close()

    def find_contact(self, name: str):
        db = SessionLocal()
        try:
            return db.query(Contact).filter(Contact.name.ilike(f"%{name}%")).first()
        finally:
            db.close()