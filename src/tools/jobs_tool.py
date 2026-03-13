try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

from urllib.parse import quote_plus

from src.tools.base import BaseTool
from src.memory.profile import ProfileManager


profile = ProfileManager()


class JobSearchTool(BaseTool):
    name = "job_search"
    description = "Search for relevant job listings"

    def run(self, query: str = "") -> str:
        try:
            from ddgs import DDGS
            p = ProfileManager()
            location = p.get('location') or 'Kochi Kerala'
            target_roles = p.get('target_roles') or 'backend fullstack AI engineer'

            if not query or query.strip() == "":
                query = target_roles

            # Relevant keywords — only show matching jobs
            relevant_keywords = [
                'python', 'backend', 'fastapi', 'django', 'flask',
                'fullstack', 'full stack', 'react', 'node',
                'ai engineer', 'machine learning', 'llm', 'software engineer',
                'software developer', 'web developer', 'api developer',
            ]

            # Keywords to skip
            skip_keywords = [
                'blockchain', 'c#', 'c sharp', 'dotnet', '.net',
                'android', 'ios', 'mobile', 'accounts', 'finance',
                'sales', 'marketing', 'hr ', 'embedded', 'hardware',
                'testing', 'qa ', 'manual test', 'devops only',
                'network', 'security analyst', 'sap', 'oracle',
            ]

            searches = [
                f"python backend developer jobs {location} 2026",
                f"fullstack developer jobs {location} 2026",
                f"software developer python react jobs {location}",
                f"site:linkedin.com/jobs/view backend developer {location}",
                f"site:naukri.com python developer {location} apply",
            ]

            all_results = []
            seen_urls = set()

            with DDGS() as ddgs:
                for search in searches:
                    try:
                        for r in ddgs.text(search, max_results=4):
                            url = r.get('href', '')
                            title = r.get('title', '').lower()
                            body = r.get('body', '').lower()
                            combined = title + ' ' + body

                            if url in seen_urls:
                                continue

                            # Skip irrelevant jobs
                            if any(skip in combined for skip in skip_keywords):
                                continue

                            # Only show relevant jobs
                            if not any(kw in combined for kw in relevant_keywords):
                                continue

                            seen_urls.add(url)
                            all_results.append({
                                'title': r.get('title', ''),
                                'body': r.get('body', '')[:200],
                                'url': url,
                            })
                    except:
                        continue

            if not all_results:
                return (
                    f"No relevant jobs found right now.\n"
                    f"Try searching directly:\n"
                    f"• https://www.linkedin.com/jobs/search/?keywords=python+backend&location=Kochi\n"
                    f"• https://www.naukri.com/python-developer-jobs-in-kochi"
                )

            # Format results
            formatted = f"🔍 Job listings for you in {location}:\n\n"
            for i, r in enumerate(all_results[:8], 1):
                formatted += f"{i}. {r['title']}\n"
                formatted += f"   📝 {r['body'][:150]}\n"
                formatted += f"   🔗 {r['url'][:80]}\n\n"

            formatted += f"Found {len(all_results)} relevant jobs.\n"
            formatted += f"To apply: 'apply for backend at [company name]'"
            return formatted

        except Exception as e:
            return f"Job search error: {str(e)}"


class ScoreJDTool(BaseTool):
    name = "score_jd"
    description = "Score a job description against Athul's resume and skills"

    def run(self, jd: str = "") -> str:
        try:
            p = ProfileManager()
            skills = p.get("skills") or "React Python FastAPI PostgreSQL MongoDB"
            experience = p.get("profession") or "Full Stack Developer"
            projects = p.get("previous_projects") or "AI Ad Generator, Instagram Agent, E-Commerce"

            jd_lower = jd.lower()

            # Supports both comma-separated and space-separated skills
            if "," in skills:
                skill_list = [s.strip().lower() for s in skills.split(",") if s.strip()]
            else:
                skill_list = [s.strip().lower() for s in skills.split() if s.strip()]

            matched = [s for s in skill_list if s in jd_lower]
            missing = [s for s in skill_list if s not in jd_lower]
            score = int((len(matched) / len(skill_list)) * 100) if skill_list else 0

            result = f"📊 JD Match Score: {score}%\n\n"
            result += f"✅ Matched skills: {', '.join(matched) if matched else 'None'}\n"
            result += f"❌ Missing skills: {', '.join(missing) if missing else 'None'}\n\n"
            result += f"👤 Profile: {experience}\n"
            result += f"🛠 Projects: {projects}\n\n"

            if score >= 70:
                result += "🔥 Strong match — apply immediately!"
            elif score >= 40:
                result += "👍 Decent match — worth applying with a good cover letter."
            else:
                result += "⚠️ Low match — consider upskilling first."

            return result

        except Exception as e:
            return f"Score error: {str(e)}"

class CoverLetterTool(BaseTool):
    name = "cover_letter"
    description = "Write a tailored cover letter for a job"

    def run(self, company: str = "", role: str = "") -> str:
        try:
            p = ProfileManager()
            name = p.get("name") or "Athul Dev"
            portfolio = p.get("portfolio") or "https://port-folio-phpa.vercel.app"
            github = p.get("github") or "https://github.com/athuldev743-cp"
            email = p.get("email") or "athuldev743@gmail.com"
            phone = p.get("phone") or "+917034306102"

            role_lower = role.lower()

            # ── BACKEND COVER LETTER ──
            if any(w in role_lower for w in ["backend", "back end", "back-end", "server", "api", "django", "node"]):
                return f"""Dear Hiring Manager,

{company}'s engineering culture and product scale is exactly the kind of environment I want to grow in — and the {role} role is a strong fit for what I do best.

I'm Athul Dev, a Backend Developer from Kochi with 2+ years of experience building production-grade APIs and services using Python, FastAPI, and PostgreSQL. My most recent project, DOOM, is a fully autonomous AI assistant I built from scratch — it handles voice I/O, Gmail automation, real-time job search, PC control, and persistent memory via Neon PostgreSQL. Before that, I built Ekabhumi, an e-commerce platform with Razorpay and Worldline payment integration, and an Instagram AI agent that auto-generates and schedules content using LLMs.

I'm comfortable with REST API design, async Python, Docker, database optimization, and deploying to cloud platforms like Render and Railway. I write clean, documented code and ship fast.

I'd love to bring this energy to {company}. I'm available for a call or technical round at your convenience.

Best regards,
{name} | {email} | {phone}
Portfolio: {portfolio} | GitHub: {github}"""

            # ── FULL STACK COVER LETTER ──
            elif any(w in role_lower for w in ["fullstack", "full stack", "full-stack", "frontend", "react", "web"]):
                return f"""Dear Hiring Manager,

When I saw the {role} opening at {company}, it immediately stood out — it matches exactly the kind of work I've been doing and want to do more of.

I'm Athul Dev, a Full Stack Developer from Kochi. I work across the entire stack — React on the frontend, FastAPI and Node on the backend, PostgreSQL and MongoDB for data, and Docker for deployment. I built Ekabhumi, a full e-commerce platform with product management, cart, checkout, and dual payment gateway integration. I also built an Instagram AI agent with a React dashboard that handles content generation, scheduling, and auto-posting — fully end-to-end.

I'm fast, I ship working products, and I care about both code quality and user experience. I've deployed production apps on Vercel, Render, and Railway and I'm comfortable in fast-moving environments.

I'd love to show you my work and discuss how I can contribute to {company}'s product team.

Best regards,
{name} | {email} | {phone}
Portfolio: {portfolio} | GitHub: {github}"""

            # ── AI ENGINEER COVER LETTER ──
            else:
                return f"""Dear Hiring Manager,

AI is not a side interest for me — it's what I build every day, and the {role} role at {company} is exactly where I want to apply that work.

I'm Athul Dev, an AI Developer from Kochi. I recently built DOOM — a fully autonomous personal AI assistant with tool-calling, RAG, voice I/O, Gmail integration, job search automation, and persistent memory. It uses Groq's LLaMA 3.3 70B as the core LLM with OpenRouter as fallback, ChromaDB for vector search, and edge-tts for real-time voice. I also built an Instagram AI Content Agent that uses LLMs to generate captions, hashtags, and images and posts them automatically via the Instagram Graph API.

I have hands-on experience with LLM integration, prompt engineering, RAG pipelines, FastAPI, and Python. I understand both the engineering and the product side of AI systems — how to make them reliable, fast, and actually useful.

I would love to discuss how my work aligns with what {company} is building in the AI space.

Best regards,
{name} | {email} | {phone}
Portfolio: {portfolio} | GitHub: {github}"""

        except Exception as e:
            return f"Cover letter error: {str(e)}"


class TrackApplicationTool(BaseTool):
    name = "track_application"
    description = "Save a job application to tracker"

    def run(self, company: str = "", role: str = "", status: str = "applied") -> str:
        try:
            import json
            from datetime import datetime

            p = ProfileManager()
            existing = p.get("job_applications")
            apps = json.loads(existing) if existing else []

            apps.append(
                {
                    "company": company,
                    "role": role,
                    "status": status,
                    "date": datetime.now().strftime("%Y-%m-%d"),
                }
            )

            p.set("job_applications", json.dumps(apps), "career")
            return f"✓ Tracked: {role} at {company} — Status: {status}"

        except Exception as e:
            return f"Track error: {str(e)}"


class ListApplicationsTool(BaseTool):
    name = "list_applications"
    description = "List all tracked job applications"

    def run(self) -> str:
        try:
            import json

            p = ProfileManager()
            existing = p.get("job_applications")

            if not existing:
                return "No applications tracked yet."

            apps = json.loads(existing)
            if not apps:
                return "No applications tracked yet."

            result = f"📋 Job Applications ({len(apps)} total):\n\n"

            for a in apps:
                status_emoji = {
                    "applied": "📤",
                    "interview": "🎯",
                    "rejected": "❌",
                    "offer": "🎉",
                    "pending": "⏳",
                }.get(a.get("status", "applied"), "📤")

                result += f"{status_emoji} {a.get('role', 'Unknown')} at {a.get('company', 'Unknown')}\n"
                result += f"   Status: {a.get('status', 'applied')} | Date: {a.get('date', 'unknown')}\n\n"

            return result

        except Exception as e:
            return f"List error: {str(e)}"