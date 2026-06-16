"""soul-companion 长期记忆模块（v3.1）"""
from .store import MemoryStore
from .retrieve import MemoryRetriever
from .embedder import BaseEmbedder as Embedder, create_embedder
from .vector_index import VectorIndex

__all__ = ["MemoryStore", "MemoryRetriever", "Embedder", "create_embedder", "VectorIndex"]
__version__ = "3.1.0"
