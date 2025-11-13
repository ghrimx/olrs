# index_worker.py
from PyQt6.QtCore import QThread, pyqtSignal
from pathlib import Path

from whoosh.index import create_in, open_dir, FileIndex
from whoosh.fields import Schema, TEXT, ID, NUMERIC
from whoosh.qparser import MultifieldParser

from base import SearchBackend

from db_manager import DbManager
from config import INDEX_DIR

# | Field     | Type              | Purpose                                         |
# | --------- | ----------------- | ----------------------------------------------- |
# | `doc_id`  | string (unique)   | Unique identifier for (pdf_path, page, section) |
# | `path`    | stored            | Full path to the PDF file                       |
# | `title`   | stored            | Title or basename of the PDF                    |
# | `lang`    | stored            | Language of the document                        |
# | `page`    | stored            | Page number                                     |
# | `section` | stored (optional) | Logical section name (e.g. “Article 12”)        |
# | `content` | indexed           | Extracted text of that page or section          |




class IndexWorker(QThread):
    progress = pyqtSignal(object, int, int)      
    finished = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(self, source_id: int, pdf_path: Path, language: str, parent=None):
        super().__init__(parent)
        self.source_id = source_id
        self.pdf_path = pdf_path
        self.language = language

    def run(self):
        try:
            db = DbManager.instance()

            records = extract_pdf_text(self.pdf_path, self.language)
            total = len(records)
            
            embeddings = model.encode([t for _, t, _ in records])

            for i, ((page, text, lemma), emb) in enumerate(zip(records, embeddings)):
                db.insert_vector(self.source_id, page, text, lemma, np_to_blob(emb), self.language)
                self.progress.emit(self.pdf_path, i + 1, total)

            self.finished.emit(total)
        except Exception as e:
            self.error.emit(str(e))


class WhooshBackend(SearchBackend):
    """Whoosh backend supporting multiple language indexes."""
    def __init__(self):
        self.index_root = INDEX_DIR
        self.index_root.mkdir(exist_ok=True)
        self.indexes = {}

    def _get_or_create_index(self, lang: str):
        lang_dir = self.index_root / lang
        lang_dir.mkdir(exist_ok=True)
        if lang not in self.indexes:
            schema = Schema(
                doc_id=ID(stored=True, unique=True),
                path=ID(stored=True),
                title=TEXT(stored=True),
                lang=ID(stored=True),
                page=NUMERIC(stored=True),
                section=TEXT(stored=True),
                content=TEXT(stored=False)
            )
            if not (lang_dir / "MAIN").exists():
                self.indexes[lang] = create_in(lang_dir, schema, indexname="MAIN")
            else:
                self.indexes[lang] = open_dir(lang_dir, indexname="MAIN")
        return self.indexes[lang]

    def index_document(self, doc_id, text: str, metadata: dict, lang: str):
        ix: FileIndex = self._get_or_create_index(lang)
        writer = ix.writer()
        writer.update_document(
            doc_id=str(doc_id),
            path=str(metadata.get("path")),
            title=str(metadata.get("title", "")),
            lang=str(lang),
            page=metadata.get("page", 1),
            section=str(metadata.get("section", "")),
            content=str(text)
        )
        writer.commit()

    def search(self, query, lang=None, limit=20):
        langs = [lang] if lang else [d.name for d in self.index_root.iterdir() if d.is_dir()]
        all_results = []
        for lg in langs:
            ix: FileIndex = self._get_or_create_index(lg)
            qp = MultifieldParser(["content", "title", "section"], schema=ix.schema)
            q = qp.parse(query)
            with ix.searcher() as s:
                res = s.search(q, limit=limit)
                for r in res:
                    data = dict(r)
                    data["lang"] = lg
                    all_results.append(data)
        return sorted(all_results, key=lambda x: -x.get("score", 0))
    
    def commit(self, lang=None):
        pass  # handled per-write in Whoosh
    
    def clear_index(self, lang=None):
        if lang:
            for f in (self.index_root / lang).glob("*"):
                f.unlink()
        else:
            for subdir in self.index_root.glob("*"):
                for f in subdir.glob("*"):
                    f.unlink()
