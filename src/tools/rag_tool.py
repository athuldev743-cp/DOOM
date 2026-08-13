from src.tools.base import BaseTool
import os

try:
    from src.memory.rag import search_docs, ingest_folder, ingest_pdf, list_docs
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False

class RAGSearchTool(BaseTool):
    name = "search_docs"
    description = "Search your personal documents, PDFs, notes and files"

    def run(self, query: str = "") -> str:
        if not RAG_AVAILABLE:
            return "Document search unavailable on server. Use locally."
        return search_docs(query)

class IngestDocsTool(BaseTool):
    name = "ingest_docs"
    description = "Index all documents in the documents folder"

    def run(self) -> str:
        if not RAG_AVAILABLE:
            return "Document indexing unavailable on server."
        return ingest_folder()

class ListDocsTool(BaseTool):
    name = "list_docs"
    description = "List all indexed documents"

    def run(self) -> str:
        if not RAG_AVAILABLE:
            return "Document listing unavailable on server."
        return list_docs()