"""Local embeddings for GraphRAG (Groq has no embedding endpoint, so this runs offline
and free via sentence-transformers). Text prep mirrors memory.normalise() so closed-case
embeddings and live query embeddings are built the same way."""
from sentence_transformers import SentenceTransformer
from .memory import normalise

_model = None
DIM = 384  # all-MiniLM-L6-v2 output size


def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def embed_text(text):
    """Single string -> list[float] of length DIM."""
    return get_model().encode(text, normalize_embeddings=True).tolist()


def embed_texts(texts):
    """Batch version - much faster for thousands of rows."""
    return get_model().encode(list(texts), normalize_embeddings=True, show_progress_bar=True).tolist()


def closed_case_doc(note, pattern):
    """Same text construction memory.CaseMemory uses internally, exposed standalone."""
    return normalise(note) + " pattern " + str(pattern)