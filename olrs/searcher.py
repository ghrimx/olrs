from pathlib import Path

from indexer import WhooshBackend

class SearchManager:
    """Manages documents and delegates to the chosen backend."""
    def __init__(self, backend):
        self.backend: WhooshBackend = backend

    def add_page(self, pdf_path: str, text: str, lang: str, page: int, section: str | None = None):
        """Index a single PDF page or section."""
        metadata = {
            "path": pdf_path,
            "title": Path(pdf_path).stem,
            "page": page,
            "section": section or "",
        }
        # Unique ID = PDF path + page + section
        doc_id = f"{pdf_path}#{page}#{section or ''}"
        self.backend.index_document(doc_id, text, metadata, lang)
        self.backend.commit(lang)

    def search(self, query: str, lang: str | None = None):
        return self.backend.search(query, lang)

