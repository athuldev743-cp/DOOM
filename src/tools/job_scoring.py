from src.memory.profile import ProfileManager


def score_job(title: str, description: str = "") -> int:
    """Skill-match percentage against Athul's stored skills — scores against
    title + description combined, since Naukri/Indeed descriptions are often
    thin snippets and the title alone frequently carries the real signal."""
    p = ProfileManager()
    skills = p.get("skills") or "React, Python, FastAPI, PostgreSQL, MongoDB, Docker, LLM"
    combined = f"{title or ''} {description or ''}".lower()

    skill_list = [s.strip().lower() for s in skills.split(",") if s.strip()]
    if not skill_list:
        return 50

    matched = sum(1 for s in skill_list if s in combined)
    return int((matched / len(skill_list)) * 100)