# index_worker.py
from pathlib import Path
from abc import ABC, abstractmethod

from whoosh.index import create_in, open_dir, FileIndex
from whoosh.fields import Schema, TEXT, ID, NUMERIC
from whoosh.qparser import MultifieldParser

from tantivy import SchemaBuilder, Index

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


class BaseIndexer(ABC):
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


class WhooshBackend(BaseIndexer):
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


class TantivyBackend(BaseIndexer):
    """Tantivy backend with per-language sub-indexes and page/section support."""
    def __init__(self, index_root="indexdir_tantivy"):
        self.index_root = Path(index_root)
        self.index_root.mkdir(exist_ok=True)
        self.indexes = {}

    def _get_or_create_index(self, lang: str):
        lang_dir = self.index_root / lang
        lang_dir.mkdir(exist_ok=True)
        if lang not in self.indexes:
            builder = SchemaBuilder()
            builder.add_text_field("title", stored=True)
            builder.add_text_field("content", stored=False)
            builder.add_text_field("lang", stored=True)
            builder.add_text_field("path", stored=True)
            builder.add_text_field("doc_id", stored=True)
            builder.add_text_field("page", stored=True)
            builder.add_text_field("section", stored=True)
            schema = builder.build()
            if (lang_dir / "meta.json").exists():
                ix = Index(schema, lang_dir)
            else:
                ix = Index.create(schema, lang_dir)
            self.indexes[lang] = ix
        return self.indexes[lang]

    def index_document(self, doc_id, text, metadata, lang):
        ix = self._get_or_create_index(lang)
        writer = ix.writer()
        writer.add_document(doc(
            doc_id=doc_id,
            path=metadata.get("path"),
            title=metadata.get("title", ""),
            lang=lang,
            page=str(metadata.get("page", "")),
            section=metadata.get("section", ""),
            content=text
        ))
        writer.commit()

    def search(self, query, lang=None, limit=20):
        langs = [lang] if lang else [d.name for d in self.index_root.iterdir() if d.is_dir()]
        all_results = []
        for lg in langs:
            ix = self._get_or_create_index(lg)
            searcher = ix.searcher()
            parser = ix.parse_query(query, ["content", "title", "section"])
            results = searcher.search(parser, limit)
            for r in results:
                stored = searcher.doc(r.doc_id)
                stored["lang"] = lg
                all_results.append(stored)
        return all_results
