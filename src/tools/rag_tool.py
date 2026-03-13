from src.tools.base import BaseTool
from src.memory.rag import search_docs, ingest_folder, ingest_pdf, list_docs
import os

class RAGSearchTool(BaseTool):
    name = "search_docs"
    description = "Search your personal documents, PDFs, notes and files"

    def run(self, query: str) -> str:
        return search_docs(query)

class IngestDocsTool(BaseTool):
    name = "ingest_docs"
    description = "Index all documents in the documents folder"

    def run(self) -> str:
        return ingest_folder()

class ListDocsTool(BaseTool):
    name = "list_docs"
    description = "List all indexed documents"

    def run(self) -> str:
        return list_docs()