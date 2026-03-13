from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from src.memory.database import Base, SessionLocal

class UserProfile(Base):
    __tablename__ = "user_profile"
    id = Column(Integer, primary_key=True)
    key = Column(String(200), unique=True, nullable=False)
    value = Column(Text, nullable=False)
    category = Column(String(100), default="general")
    updated_at = Column(DateTime, server_default=func.now())

class Contact(Base):
    __tablename__ = "contacts"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    phone = Column(String(50), nullable=True)
    whatsapp = Column(String(50), nullable=True)
    email = Column(String(200), nullable=True)
    relationship = Column(String(200), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

class ProfileManager:
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

    def get_by_category(self, category: str) -> dict:
        db = SessionLocal()
        try:
            all_p = db.query(UserProfile).filter_by(category=category).all()
            return {p.key: p.value for p in all_p}
        finally:
            db.close()

    def add_contact(self, name: str, phone: str = None, relationship: str = None,
                    email: str = None, notes: str = None) -> str:
        db = SessionLocal()
        try:
            existing = db.query(Contact).filter(
                Contact.name.ilike(f"%{name}%")
            ).first()
            if existing:
                if phone: existing.phone = phone
                if relationship: existing.relationship = relationship
                if email: existing.email = email
                if notes: existing.notes = notes
            else:
                db.add(Contact(
                    name=name, phone=phone, whatsapp=phone,
                    relationship=relationship, email=email, notes=notes
                ))
            db.commit()
            return f"✓ Contact saved: {name}"
        finally:
            db.close()

    def find_contact(self, name: str):
        db = SessionLocal()
        try:
            contact = db.query(Contact).filter(
                Contact.name.ilike(f"%{name}%")
            ).first()
            return contact
        finally:
            db.close()

    def list_contacts(self) -> str:
        db = SessionLocal()
        try:
            contacts = db.query(Contact).all()
            if not contacts:
                return "No contacts saved."
            result = "Your contacts:\n"
            for c in contacts:
                result += f"- {c.name}"
                if c.relationship: result += f" ({c.relationship})"
                if c.phone: result += f" — {c.phone}"
                result += "\n"
            return result
        finally:
            db.close()