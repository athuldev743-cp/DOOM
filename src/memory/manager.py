from sqlalchemy.orm import Session
from src.memory.models import Conversation, Message, UserMemory
from src.memory.database import SessionLocal
import uuid

class MemoryManager:
    def __init__(self, session_id: str = None):
        self.session_id = session_id or str(uuid.uuid4())

    def _get_db(self) -> Session:
        return SessionLocal()

    def ensure_conversation(self):
        db = self._get_db()
        try:
            conv = db.query(Conversation).filter_by(session_id=self.session_id).first()
            if not conv:
                conv = Conversation(session_id=self.session_id)
                db.add(conv)
                db.commit()
        finally:
            db.close()

    def save_message(self, role: str, content: str):
        self.ensure_conversation()
        db = self._get_db()
        try:
            msg = Message(session_id=self.session_id, role=role, content=content)
            db.add(msg)
            db.commit()
        finally:
            db.close()

    def load_history(self, limit: int = 20) -> list:
        db = self._get_db()
        try:
            messages = (
                db.query(Message)
                .filter_by(session_id=self.session_id)
                .order_by(Message.created_at.desc())
                .limit(limit)
                .all()
            )
            return [{"role": m.role, "content": m.content} for m in reversed(messages)]
        finally:
            db.close()

    def save_memory(self, key: str, value: str):
        db = self._get_db()
        try:
            mem = db.query(UserMemory).filter_by(key=key).first()
            if mem:
                mem.value = value
            else:
                mem = UserMemory(key=key, value=value)
                db.add(mem)
            db.commit()
        finally:
            db.close()

    def get_memory(self, key: str) -> str:
        db = self._get_db()
        try:
            mem = db.query(UserMemory).filter_by(key=key).first()
            return mem.value if mem else None
        finally:
            db.close()

    def get_all_memories(self) -> dict:
        db = self._get_db()
        try:
            mems = db.query(UserMemory).all()
            return {m.key: m.value for m in mems}
        finally:
            db.close()