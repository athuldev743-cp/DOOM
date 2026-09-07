from ddgs import DDGS
from src.tools.base import BaseTool
from src.tools.schemas import ToolResult, WebSearchArgs

class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Search the web for current information"
    args_schema = WebSearchArgs

    @classmethod
    def parse_args(cls, raw: str) -> dict:
        return {"query": raw.strip()}

    def run(self, query: str = "") -> ToolResult:
        try:
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=5):
                    results.append(
                        f"• {r['title']}\n"
                        f"  {r['body'][:200]}\n"
                        f"  {r['href']}"
                    )
            if not results:
                return ToolResult(success=True, message="No results found.")
            return ToolResult(success=True, message="\n\n".join(results))
        except Exception as e:
            return ToolResult(success=False, message=f"Search error: {str(e)}")