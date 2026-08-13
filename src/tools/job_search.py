import json
import re
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any

from src.tools.base import BaseTool
from src.memory.profile import ProfileManager


class JobSearchTool(BaseTool):
    name = "job_search"
    description = "Search for 50 tech jobs (AI, Python, Full Stack, Backend) and fetch full descriptions."

    def _fetch_full_description(self, url: str) -> str:
        """Fetch destination page and extract full text context."""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            res = requests.get(url, headers=headers, timeout=6)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                # Remove non-content elements
                for element in soup(["script", "style", "nav", "header", "footer", "form"]):
                    element.decompose()
                text = " ".join(soup.stripped_strings)
                # Return primary description window
                return text[:3000]
        except Exception:
            pass
        return ""

    def run(self, query: str = "Python Full Stack AI Developer", location: str = "Kochi Remote India") -> str:
        try:
            from ddgs import DDGS
        except ImportError:
            return "Error: `ddgs` library is not installed. Install it using `pip install duckduckgo_search`."

        p = ProfileManager()
        results: List[Dict[str, Any]] = []
        seen_urls = set()

        search_queries = [
            f"{query} jobs {location} 2026",
            f"site:linkedin.com/jobs/view {query} {location}",
            f"site:naukri.com {query} {location} hiring",
            f"Python FastAPI AI Engineer jobs {location}",
            f"Full Stack Developer React Python remote jobs India"
        ]

        print(f"[JobSearchTool] Searching up to 50 jobs for: '{query}' in '{location}'...")

        with DDGS() as ddgs:
            for q in search_queries:
                if len(results) >= 50:
                    break
                try:
                    for item in ddgs.text(q, max_results=15):
                        if len(results) >= 50:
                            break
                        
                        url = item.get("href", "")
                        title = item.get("title", "")
                        snippet = item.get("body", "")

                        if not url or url in seen_urls:
                            continue

                        seen_urls.add(url)

                        # Extract rough company name from title
                        company = "Hiring Company"
                        if " at " in title:
                            company = title.split(" at ")[-1].split("-")[0].split("|")[0].strip()
                        elif " - " in title:
                            parts = title.split(" - ")
                            if len(parts) > 1:
                                company = parts[1].strip()

                        # Deep fetch full JD context
                        full_jd = self._fetch_full_description(url)
                        description = full_jd if len(full_jd) > 200 else snippet

                        job_id = f"job_{len(results) + 1}"
                        results.append({
                            "id": job_id,
                            "title": title,
                            "company": company,
                            "snippet": snippet,
                            "description": description,
                            "url": url
                        })
                except Exception as err:
                    print(f"[JobSearchTool] Search query failed for '{q}': {err}")

        # Store full search dataset into memory for CoverLetterTool and UI consumers
        p.set("latest_job_search", json.dumps(results))

        summary = f"✅ Successfully fetched {len(results)} jobs with full descriptions.\n\n"
        for j in results[:5]:  # Display preview of top 5
            summary += f"• **{j['title']}** ({j['company']})\n  ID: `{j['id']}` | 🔗 {j['url'][:60]}...\n\n"

        if len(results) > 5:
            summary += f"*...and {len(results) - 5} more stored in memory.*"

        return summary