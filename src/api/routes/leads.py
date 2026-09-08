from fastapi import APIRouter, Depends, HTTPException
from src.api.deps import get_current_identity, Identity
from src.memory.database import SessionLocal, Visitor

router = APIRouter()


def _serialize(v: Visitor) -> dict:
    return {
        "id": v.id,
        "name": v.name,
        "role": v.role,
        "company": v.company,
        "interest": v.interest,
        "summary": v.summary,
        "first_seen": v.first_seen.isoformat() if v.first_seen else None,
        "last_seen": v.last_seen.isoformat() if v.last_seen else None,
    }


@router.get("/api/leads")
async def list_leads(identity: Identity = Depends(get_current_identity)):
    if not identity.is_owner:
        raise HTTPException(status_code=403, detail="Owner access only")
    db = SessionLocal()
    try:
        visitors = db.query(Visitor).order_by(Visitor.last_seen.desc()).all()
        return {"visitors": [_serialize(v) for v in visitors]}
    finally:
        db.close()


@router.get("/api/leads/{visitor_id}")
async def get_lead(visitor_id: int, identity: Identity = Depends(get_current_identity)):
    if not identity.is_owner:
        raise HTTPException(status_code=403, detail="Owner access only")
    db = SessionLocal()
    try:
        v = db.query(Visitor).filter_by(id=visitor_id).first()
        if not v:
            raise HTTPException(status_code=404, detail="Not found")
        return _serialize(v)
    finally:
        db.close()