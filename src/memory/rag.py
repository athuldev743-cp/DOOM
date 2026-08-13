import os
from dotenv import load_dotenv

load_dotenv()

CHROMA_PATH = os.getenv("CHROMA_PATH", "./data/chroma")
DOCS_PATH = os.getenv("DOCS_PATH", "./data/documents")

try:
    import chromadb
    from chromadb.utils import embedding_functions
    import fitz

    client = chromadb.PersistentClient(path=CHROMA_PATH)
    embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    collection = client.get_or_create_collection(
        name="doom_docs",
        embedding_function=embedding_fn
    )
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    collection = None


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list:
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i:i+chunk_size])
        chunks.append(chunk)
        i += chunk_size - overlap
    return chunks


def ingest_pdf(filepath: str) -> str:
    if not RAG_AVAILABLE:
        return "RAG not available on server."
    filename = os.path.basename(filepath)
    doc = fitz.open(filepath)
    full_text = ""
    for page in doc:
        full_text += page.get_text()
    doc.close()
    chunks = chunk_text(full_text)
    ids = [f"{filename}_chunk_{i}" for i in range(len(chunks))]
    metadatas = [{"source": filename, "chunk": i} for i in range(len(chunks))]
    try:
        existing = collection.get(where={"source": filename})
        if existing["ids"]:
            collection.delete(ids=existing["ids"])
    except:
        pass
    collection.add(documents=chunks, ids=ids, metadatas=metadatas)
    return f"✓ Ingested {filename} — {len(chunks)} chunks indexed"


def ingest_text(filepath: str) -> str:
    if not RAG_AVAILABLE:
        return "RAG not available on server."
    filename = os.path.basename(filepath)
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        full_text = f.read()
    chunks = chunk_text(full_text)
    ids = [f"{filename}_chunk_{i}" for i in range(len(chunks))]
    metadatas = [{"source": filename, "chunk": i} for i in range(len(chunks))]
    try:
        existing = collection.get(where={"source": filename})
        if existing["ids"]:
            collection.delete(ids=existing["ids"])
    except:
        pass
    collection.add(documents=chunks, ids=ids, metadatas=metadatas)
    return f"✓ Ingested {filename} — {len(chunks)} chunks indexed"


def ingest_folder(folder: str = DOCS_PATH) -> str:
    if not RAG_AVAILABLE:
        return "RAG not available on server."
    results = []
    for filename in os.listdir(folder):
        filepath = os.path.join(folder, filename)
        if filename.endswith(".pdf"):
            results.append(ingest_pdf(filepath))
        elif filename.endswith((".txt", ".md")):
            results.append(ingest_text(filepath))
    if not results:
        return "No documents found in folder."
    return "\n".join(results)


def search_docs(query: str, n_results: int = 3) -> str:
    if not RAG_AVAILABLE:
        return "Document search not available on server."
    try:
        results = collection.query(query_texts=[query], n_results=n_results)
        if not results["documents"][0]:
            return "No relevant documents found."
        output = ""
        for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
            output += f"[{meta['source']}]\n{doc}\n\n"
        return output.strip()
    except Exception as e:
        return f"Search error: {str(e)}"


def list_docs() -> str:
    if not RAG_AVAILABLE:
        return "Document listing not available on server."
    try:
        all_docs = collection.get()
        sources = list(set(m["source"] for m in all_docs["metadatas"]))
        if not sources:
            return "No documents indexed yet."
        return "Indexed documents:\n" + "\n".join(f"- {s}" for s in sources)
    except:
        return "No documents indexed yet."