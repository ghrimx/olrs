from abc import ABC, abstractmethod

class SearchBackend(ABC):
    """Abstract base class for a search backend."""

    @abstractmethod
    def index_document(self, doc_id: str, text: str, metadata: dict):
        pass

    @abstractmethod
    def search(self, query: str, lang: str | None = None, limit: int = 20):
        """Return a list of result dicts with at least: path, title, snippet, score."""
        pass

    @abstractmethod
    def commit(self):
        pass

    @abstractmethod
    def clear_index(self):
        pass
