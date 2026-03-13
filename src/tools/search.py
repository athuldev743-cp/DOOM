from ddgs import DDGS
from src.tools.base import BaseTool

class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Search the web for current information"

    def run(self, query: str = "") -> str:
        try:
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=5):
                    results.append(
                        f"• {r['title']}\n"
                        f"  {r['body'][:200]}\n"
                        f"  {r['href']}"
                    )
            return "\n\n".join(results) if results else "No results found."
        except Exception as e:
            return f"Search error: {str(e)}"