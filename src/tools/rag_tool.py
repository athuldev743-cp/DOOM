from src.tools.base import BaseTool
from src.tools.schemas import ToolResult, RAGSearchArgs, IngestDocsArgs, ListDocsArgs
import os

try:
    from src.memory.rag import search_docs, ingest_folder, ingest_pdf, list_docs
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False

class RAGSearchTool(BaseTool):
    name = "search_docs"
    description = "Search your personal documents, PDFs, notes and files"
    args_schema = RAGSearchArgs

    @classmethod
    def parse_args(cls, raw: str) -> dict:
        return {"query": raw.strip()}

    def run(self, query: str = "") -> ToolResult:
        if not RAG_AVAILABLE:
            return ToolResult(success=False, message="Document search unavailable on server. Use locally.")
        return ToolResult(success=True, message=search_docs(query))

class IngestDocsTool(BaseTool):
    name = "ingest_docs"
    description = "Index all documents in the documents folder"
    args_schema = IngestDocsArgs

    def run(self) -> ToolResult:
        if not RAG_AVAILABLE:
            return ToolResult(success=False, message="Document indexing unavailable on server.")
        return ToolResult(success=True, message=ingest_folder())

class ListDocsTool(BaseTool):
    name = "list_docs"
    description = "List all indexed documents"
    args_schema = ListDocsArgs

    def run(self) -> ToolResult:
        if not RAG_AVAILABLE:
            return ToolResult(success=False, message="Document listing unavailable on server.")
        return ToolResult(success=True, message=list_docs())