from fastapi import APIRouter, Depends

from src.api.deps import require_owner

router = APIRouter()


@router.get("/memory")
async def get_memory(_identity=Depends(require_owner)):
    from src.memory.profile import ProfileManager

    p = ProfileManager()
    profile = p.get_all()
    contacts = p.list_contacts()

    return {
        "profile": profile,
        "contacts": contacts,
    }
