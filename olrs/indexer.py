# index_worker.py
from pathlib import Path
from abc import ABC, abstractmethod

from whoosh.index import create_in, open_dir, FileIndex, exists_in
from whoosh.fields import Schema, TEXT, ID, NUMERIC
from whoosh.qparser import MultifieldParser, OrGroup
from whoosh.query import Term, FuzzyTerm, Or, Phrase
from whoosh.analysis import StemmingAnalyzer, StandardAnalyzer, NgramWordAnalyzer


from tantivy import SchemaBuilder, Index

from db_manager import DbManager
from config import INDEX_DIR
from common import SearchMode

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

    @abstractmethod
    def delete_index(self, kwarg):
        pass


class WhooshBackend:
    """Whoosh backend supporting multiple language indexes and flexible search modes."""

    def __init__(self):
        self.index_root = INDEX_DIR
        self.index_root.mkdir(exist_ok=True)
        self.indexes = {}

    # ---------------------------------------------------
    # Create or get index per language
    # ---------------------------------------------------
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

                # For partial search (substring)
                content_partial=TEXT(stored=False,
                                     analyzer=NgramWordAnalyzer(minsize=3, maxsize=20)),

                # For whole word, phrase, synonyms, fuzzy
                content_exact=TEXT(stored=False,
                                   analyzer=StandardAnalyzer()),

                # Titles/sections are also indexed normally
                title_exact=TEXT(stored=False, analyzer=StandardAnalyzer()),
                section_exact=TEXT(stored=False, analyzer=StandardAnalyzer()),
            )

            if not exists_in(lang_dir):
                self.indexes[lang] = create_in(lang_dir, schema)
            else:
                self.indexes[lang] = open_dir(lang_dir)

        return self.indexes[lang]

    # ---------------------------------------------------
    # Index a single document or page
    # ---------------------------------------------------
    def index_document(self, doc_id, text: str, metadata: dict, lang: str):
        ix: FileIndex = self._get_or_create_index(lang)
        writer = ix.writer()

        writer.update_document(
            doc_id=str(doc_id),
            path=str(metadata.get("path")),
            title=str(metadata.get("title")),
            lang=str(lang),
            page=metadata.get("page", 1),
            section=str(metadata.get("section", "")),

            content_partial=text,
            content_exact=text,

            title_exact=str(metadata.get("title", "")),
            section_exact=str(metadata.get("section", "")),
        )
        writer.commit()

    @staticmethod
    def _get_matched_terms(matched_terms: set):
        terms = set()
        for l in matched_terms:
            byte_string = l[1]
            decoded_string = str(byte_string.decode("utf-8"))
            terms.add(decoded_string)
        return terms

    # ---------------------------------------------------
    # Search method supporting fuzzy / partial / whole
    # ---------------------------------------------------
    def _search(self, query: str, lang=None, mode=SearchMode.PARTIAL, limit=50):
        langs = [lang] if lang else [d.name for d in self.index_root.iterdir() if d.is_dir()]
        all_results = []

        for lg in langs:
            ix: FileIndex = self._get_or_create_index(lg)
            tokens = query.split()
            query_list = []

            # Fields depend on mode
            if mode == SearchMode.PARTIAL:
                fields = ["content_partial"]
            else:
                fields = ["content_exact", "title_exact", "section_exact"]

            for token in tokens:
                token = token.lower()

                # ---------- Partial substring search ----------
                if mode == SearchMode.PARTIAL:
                    qp = MultifieldParser(["content_partial"], schema=ix.schema)
                    query_list.append(qp.parse(token))

                # ---------- Fuzzy search ----------
                elif mode == SearchMode.FUZZY:
                    for field in fields:
                        query_list.append(FuzzyTerm(field, token, maxdist=1))

                # ---------- Exact whole-word / phrase ----------
                elif mode == SearchMode.WHOLE:
                    if len(tokens) > 1:
                        # phrase search
                        for field in fields:
                            query_list.append(Phrase(field, tokens))
                    else:
                        # whole single word
                        for field in fields:
                            query_list.append(Term(field, token))

            final_query = Or(query_list)
            print(f"final_query:{final_query}")

            with ix.searcher() as s:
                res = s.search(final_query, limit=limit, terms=True)
                for r in res:
                    data = dict(r)
                    data["score"] = r.score
                    data["lang"] = lg
                    all_results.append(data)            

        terms = self._get_matched_terms(res.matched_terms())

        print(f"\nterms:{terms}")
        # Sort by score descending
        return sorted(all_results, key=lambda x: -x["score"]), terms
    
    def search(self, query: str, lang=None, mode=SearchMode.PARTIAL, limit=50):

        res, terms = self._search(query, lang=lang, mode=mode, limit=limit)

        if res:
            return res, terms
        
        else:
            if mode == SearchMode.PARTIAL:
                res, terms = self._search(query, lang=lang, mode=SearchMode.FUZZY, limit=limit)
        
        return res, terms

    
    def commit(self, lang=None):
        pass  # handled per-write in Whoosh

    # ----------------------------
    # Clear index
    # ----------------------------
    def clear_index(self, lang=None):
        if lang:
            for f in (self.index_root / lang).glob("*"):
                f.unlink()
        else:
            for subdir in self.index_root.glob("*"):
                for f in subdir.glob("*"):
                    f.unlink()

    def delete_document(self, doc_id: str, lang: str):
        """
        Deletes all pages of a document from the Whoosh index.
        """
        ix: FileIndex = self._get_or_create_index(lang)  # make sure index exists
        writer = ix.writer()
        writer.delete_by_term("doc_id", str(doc_id))
        writer.commit()

    def delete_index(self, fpath: str):
        fpath = str(fpath)
        for lang_dir in self.index_root.iterdir():
            if lang_dir.is_dir():
                ix: FileIndex = self._get_or_create_index(lang_dir.name)
                writer = ix.writer()
                writer.delete_by_term("path", fpath)
                writer.commit()


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


class BackendManager:
    """Manages documents and delegates to the chosen backend."""
    def __init__(self, backend):
        self.backend: WhooshBackend = backend

    def add_page(self, doc_id: str, pdf_path: str, text: str, lang: str, page: int, section: str | None = None):
        """Index a single PDF page or section."""
        metadata = {
            "path": pdf_path,
            "title": Path(pdf_path).stem,
            "page": page,
            "section": section or "",
        }
        # Unique ID = PDF path + page + section
        uid = f"{doc_id}#{pdf_path}#{page}#{section or ''}"
        self.backend.index_document(uid, text, metadata, lang)
        self.backend.commit(lang)

    def search(self, query: str, lang: str, mode):
        return self.backend.search(query, lang, mode)
    
