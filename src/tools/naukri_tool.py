from src.tools.base import BaseTool
from src.memory.profile import ProfileManager


class NaukriSearchTool(BaseTool):
    name = "naukri_search"
    description = "Search Naukri.com for live job listings"

    def run(self, query: str = "", location: str = "") -> str:
        try:
            profile = ProfileManager()
            profile_location = profile.get("location") or "Kochi"
            final_location = location.strip() if location else profile_location

            # Build direct Naukri search URLs — no DDG needed
            loc_slug = final_location.lower().split()[0]  # "kochi"
            query_slug = query.lower().strip().replace(" ", "-")

            links = []

            role_links = {
                "backend": [
                    ("Backend Developer Jobs in Kochi", 
                     "https://www.naukri.com/backend-developer-jobs-in-kochi"),
                    ("Python Developer Jobs in Kochi",
                     "https://www.naukri.com/python-developer-jobs-in-kochi"),
                    ("Python Backend Jobs in Kochi",
                     "https://www.naukri.com/python-jobs-in-kochi"),
                    ("FastAPI Developer Jobs",
                     "https://www.naukri.com/fastapi-developer-jobs"),
                    ("Django Developer Jobs in Kochi",
                     "https://www.naukri.com/django-developer-jobs-in-kochi"),
                ],
                "fullstack": [
                    ("Full Stack Developer Jobs in Kochi",
                     "https://www.naukri.com/full-stack-developer-jobs-in-kochi"),
                    ("React Developer Jobs in Kochi",
                     "https://www.naukri.com/react-developer-jobs-in-kochi"),
                    ("Full Stack Python Jobs in Kochi",
                     "https://www.naukri.com/full-stack-python-jobs-in-kochi"),
                ],
                "ai": [
                    ("AI Engineer Jobs in Kochi",
                     "https://www.naukri.com/ai-engineer-jobs-in-kochi"),
                    ("Machine Learning Jobs in Kochi",
                     "https://www.naukri.com/machine-learning-jobs-in-kochi"),
                    ("LLM Developer Jobs",
                     "https://www.naukri.com/llm-developer-jobs"),
                    ("AI ML Developer Jobs in Kerala",
                     "https://www.naukri.com/ai-ml-developer-jobs-in-kerala"),
                ],
            }

            # Pick relevant category
            query_lower = query.lower()
            if any(w in query_lower for w in ['ai', 'machine learning', 'ml', 'llm']):
                category = 'ai'
            elif any(w in query_lower for w in ['fullstack', 'full stack', 'react', 'frontend']):
                category = 'fullstack'
            else:
                category = 'backend'

            links = role_links[category]

            # Also add general search URL
            general_url = (
                f"https://www.naukri.com/{query_slug}-jobs-in-{loc_slug}"
            )

            formatted = f"🔍 Naukri job links for '{query}' in {final_location}:\n\n"
            for i, (title, url) in enumerate(links, 1):
                formatted += f"{i}. {title}\n   🔗 {url}\n\n"

            formatted += f"{len(links)+1}. Search '{query}' directly\n"
            formatted += f"   🔗 {general_url}\n\n"
            formatted += "To apply: 'apply for [role] at [company name]'"

            return formatted

        except Exception as e:
            return f"Naukri search error: {str(e)}"



class NaukriScrapeTool(BaseTool):
    name = "naukri_scrape"
    description = "Search Naukri.com for job listings"

    def run(self, query: str = "", location: str = "") -> str:
        return NaukriSearchTool().run(query=query, location=location)        
