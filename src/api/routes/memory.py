from fastapi import APIRouter

router = APIRouter()


@router.get("/memory")
async def get_memory():
    from src.memory.profile import ProfileManager

    p = ProfileManager()
    profile = p.get_all()
    contacts = p.list_contacts()

    return {
        "profile": profile,
        "contacts": contacts,
    }