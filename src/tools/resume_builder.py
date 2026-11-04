"""Deterministic CV and cover-letter generation from the approved master resume.

The job description changes ordering and emphasis only; it never creates new claims.
"""
import json
import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, HRFlowable, KeepTogether

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MASTER_RESUME_PATH = PROJECT_ROOT / "data" / "resumes" / "master_resume.json"
GENERATED_CV_DIR = PROJECT_ROOT / "data" / "generated_cvs"


def load_master_resume():
    with MASTER_RESUME_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _pdf__pdf_escape(value):
    replacements = {"→": "->", "–": "-", "—": "-", "’": "'", "“": '"', "”": '"'}
    text = str(value or "")
    for old, new in replacements.items():
        text = text.replace(old, new)
    return escape(text)


def _tokens(text):
    return set(re.findall(r"[a-z0-9+#.]+", (text or "").lower()))


def _relevance(text, job_text):
    job_tokens = _tokens(job_text)
    source_tokens = _tokens(text)
    aliases = {
        "llm": {"llms", "language", "model", "models"},
        "api": {"apis", "rest", "fastapi"},
        "agent": {"agents", "agentic", "tool"},
        "database": {"databases", "postgresql", "mongodb", "sql"},
        "backend": {"fastapi", "python", "api", "apis"},
        "rag": {"retrieval", "embeddings", "vector", "semantic"},
        "async": {"asyncio", "asyncpg"},
    }
    expanded = set(job_tokens)
    for token in job_tokens:
        expanded.update(aliases.get(token, set()))
    return len(source_tokens.intersection(expanded))


def _ordered(items, text_getter, job_text):
    return sorted(items, key=lambda item: _relevance(text_getter(item), job_text), reverse=True)


def _safe_slug(value):
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug[:55] or "role"


def generated_cv_path(relative_or_absolute):
    candidate = Path(relative_or_absolute)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    root = GENERATED_CV_DIR.resolve()
    resolved = candidate.resolve()
    if root not in resolved.parents:
        raise ValueError("CV path is outside the generated-CV directory")
    return resolved


def _styles():
    base = getSampleStyleSheet()
    return {
        "name": ParagraphStyle("ResumeName", parent=base["Normal"], fontName="Helvetica-Bold",
                               fontSize=17, leading=19, textColor=colors.HexColor("#14213d"), spaceAfter=2),
        "headline": ParagraphStyle("ResumeHeadline", parent=base["Normal"], fontName="Helvetica",
                                   fontSize=8.5, leading=10, textColor=colors.HexColor("#334155"), spaceAfter=4),
        "contact": ParagraphStyle("ResumeContact", parent=base["Normal"], fontName="Helvetica",
                                  fontSize=7.6, leading=9, textColor=colors.HexColor("#475569"), spaceAfter=5),
        "section": ParagraphStyle("ResumeSection", parent=base["Normal"], fontName="Helvetica-Bold",
                                  fontSize=9.1, leading=10, textColor=colors.HexColor("#14213d"),
                                  spaceBefore=5, spaceAfter=2),
        "body": ParagraphStyle("ResumeBody", parent=base["Normal"], fontName="Helvetica",
                               fontSize=7.7, leading=9.3, textColor=colors.HexColor("#1f2937"),
                               spaceAfter=1.4),
        "small": ParagraphStyle("ResumeSmall", parent=base["Normal"], fontName="Helvetica",
                                fontSize=7.4, leading=8.8, textColor=colors.HexColor("#334155"),
                                spaceAfter=1),
        "bullet": ParagraphStyle("ResumeBullet", parent=base["Normal"], fontName="Helvetica",
                                 fontSize=7.45, leading=8.9, leftIndent=8, firstLineIndent=-6,
                                 textColor=colors.HexColor("#1f2937"), spaceAfter=1.2),
    }


def _section(story, title, styles):
    story.append(Paragraph(escape(title.upper()), styles["section"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#94a3b8"),
                            spaceBefore=0, spaceAfter=3))


def _bullet(story, text, styles):
    story.append(Paragraph("• " + escape(text), styles["bullet"]))


def generate_tailored_cv(application_id, job_title, company, job_description):
    resume = load_master_resume()
    job_text = f"{job_title} {company} {job_description or ''}"
    GENERATED_CV_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"application-{int(application_id)}-{_safe_slug(job_title)}.pdf"
    output_path = GENERATED_CV_DIR / filename
    styles = _styles()

    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4,
        rightMargin=13 * mm, leftMargin=13 * mm,
        topMargin=10 * mm, bottomMargin=10 * mm,
        title=f"{resume['name']} - {job_title}",
        author=resume["name"],
    )
    story = [
        Paragraph(escape(resume["name"]), styles["name"]),
        Paragraph(escape(resume["headline"]), styles["headline"]),
    ]
    contact = (
        f"{escape(resume['location'])} | {escape(resume['phone'])} | "
        f"{escape(resume['email'])} | "
        f'<link href="{escape(resume["portfolio"])}" color="#2563eb">Portfolio</link> | '
        f'<link href="{escape(resume["github"])}" color="#2563eb">GitHub</link> | '
        f'<link href="{escape(resume["linkedin"])}" color="#2563eb">LinkedIn</link>'
    )
    story.append(Paragraph(contact, styles["contact"]))
    story.append(Paragraph(f"<b>Target:</b> {escape(job_title)} — {escape(company)}", styles["small"]))

    _section(story, "Professional Summary", styles)
    story.append(Paragraph(escape(resume["summary"]), styles["body"]))

    _section(story, "Technical Skills", styles)
    skill_groups = _ordered(
        resume["skills"], lambda group: group["category"] + " " + " ".join(group["items"]), job_text
    )
    for group in skill_groups:
        items = _ordered(group["items"], lambda item: item, job_text)
        story.append(Paragraph(
            f"<b>{escape(group['category'])}:</b> {escape(', '.join(items))}", styles["small"]
        ))

    _section(story, "Professional Experience", styles)
    for role in resume["experience"]:
        story.append(Paragraph(
            f"<b>{escape(role['role'])} — {escape(role['company'])}</b>"
            f" <font color='#64748b'>| {escape(role['dates'])} | {escape(role['location'])}</font>",
            styles["body"],
        ))
        for item in _ordered(role["bullets"], lambda value: value, job_text):
            _bullet(story, item, styles)

    _section(story, "Selected AI & Software Projects", styles)
    projects = _ordered(
        resume["projects"],
        lambda project: project["name"] + " " + " ".join(project["bullets"]), job_text
    )
    for project in projects:
        title = (
            f"<b>{escape(project['name'])}</b> "
            f"<font color='#64748b'>| {escape(project['date'])}</font> "
            f'<link href="{escape(project["url"])}" color="#2563eb">Project</link>'
        )
        block = [Paragraph(title, styles["body"])]
        for item in _ordered(project["bullets"], lambda value: value, job_text):
            block.append(Paragraph("• " + escape(item), styles["bullet"]))
        story.append(KeepTogether(block))

    _section(story, "Education", styles)
    for item in resume["education"]:
        story.append(Paragraph(
            f"<b>{escape(item['degree'])}</b> <font color='#64748b'>| {escape(item['dates'])}</font>",
            styles["body"],
        ))

    doc.build(story)
    return str(output_path.relative_to(PROJECT_ROOT))


def generate_cover_letter(job_title, company, job_description):
    resume = load_master_resume()
    job_text = f"{job_title} {company} {job_description or ''}"
    projects = _ordered(
        resume["projects"],
        lambda project: project["name"] + " " + " ".join(project["bullets"]), job_text
    )
    experience = resume["experience"][0]
    relevant_experience = _ordered(experience["bullets"], lambda value: value, job_text)[:2]
    relevant_projects = projects[:2]

    lines = [
        "Dear Hiring Team,", "",
        f"I am applying for the {job_title} role at {company}. I bring one year of professional Software Engineering experience at Oquilix, where I built production FastAPI APIs, semantic-search pipelines, and asynchronous database workflows.",
        "", "Relevant work from my projects includes:",
    ]
    for project in relevant_projects:
        best_bullet = _ordered(project["bullets"], lambda value: value, job_text)[0]
        lines.append(f"• {project['name']}: {best_bullet}")
    if relevant_experience:
        lines.extend(["", "In my professional role, I also:"])
        lines.extend([f"• {item}" for item in relevant_experience])
    lines.extend([
        "",
        "My experience with Python, FastAPI, LLM applications, RAG, and backend systems would allow me to contribute to your engineering team.",
        "", "Best regards,", resume["name"], resume["email"], resume["phone"],
        resume["portfolio"], resume["github"],
    ])
    return "\n".join(lines)


def is_valid_recipient_email(value):
    pattern = r"[A-Za-z0-9.!#$%&'*+/=?^_{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+"
    return bool(re.fullmatch(pattern, (value or "").strip()))
