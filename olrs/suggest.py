# core/suggest.py
from pathlib import Path
import json
from typing import List, Iterable, Set
from whoosh.index import create_in, open_dir, exists_in
from whoosh.fields import Schema, TEXT, ID
from whoosh.analysis import StemmingAnalyzer, RegexTokenizer, LowercaseFilter
from whoosh.query import Prefix, FuzzyTerm
from whoosh.qparser import QueryParser

# Simple synonym store (loadable/modifiable)
SYN_FILE = Path("synonyms.json")
if SYN_FILE.exists():
    with open(SYN_FILE, "r", encoding="utf8") as f:
        SYN = json.load(f)
else:
    SYN = {}

def load_synonyms(path: str):
    global SYN, SYN_FILE
    SYN_FILE = Path(path)
    with open(SYN_FILE, "r", encoding="utf8") as f:
        SYN = json.load(f)

def get_synonyms(word: str) -> List[str]:
    return SYN.get(word.lower(), [])

# Suggest index per language under index_root/<lang>/suggest/
class SuggestManager:
    def __init__(self, index_root: Path, analyzer=None):
        self.index_root = Path(index_root)
        self.analyzer = analyzer or StemmingAnalyzer()
        self._handles = {}  # lang -> whoosh index

    def _suggest_dir(self, lang: str) -> Path:
        d = self.index_root / lang / "suggest"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _get_or_create(self, lang: str):
        if lang in self._handles:
            return self._handles[lang]
        d = self._suggest_dir(lang)
        schema = Schema(term=TEXT(stored=True), weight=ID(stored=True))
        if not exists_in(d):
            ix = create_in(d, schema)
        else:
            ix = open_dir(d)
        self._handles[lang] = ix
        return ix

    def add_terms(self, lang: str, terms: Iterable[str], weight: int = 1):
        """Add/update terms (set of unique tokens)."""
        ix = self._get_or_create(lang)
        w = ix.writer()
        for t in set(terms):
            if not t:
                continue
            # Whoosh writer.update_document will upsert; use term as stored TEXT
            w.update_document(term=str(t), weight=str(weight))
        w.commit()

    def build_terms_from_text(self, text: str) -> Set[str]:
        tokens = []
        for tok in self.analyzer(text):
            # analyzer returns Token objects: tok.text
            tokens.append(getattr(tok, "text", str(tok)))
        # simple dedupe and remove short tokens
        return set([t for t in tokens if len(t) >= 2])

    # ---------------- suggestion APIs ----------------
    def prefix_suggest(self, lang: str, prefix: str, limit: int = 10) -> List[str]:
        ix = self._get_or_create(lang)
        out = []
        with ix.searcher() as s:
            q = Prefix("term", prefix.lower())
            res = s.search(q, limit=limit)
            for r in res:
                out.append(r["term"])
        return out

    def fuzzy_suggest(self, lang: str, word: str, maxdist: int = 1, limit: int = 10) -> List[str]:
        ix = self._get_or_create(lang)
        out = []
        with ix.searcher() as s:
            q = FuzzyTerm("term", word.lower(), maxdist=maxdist)
            res = s.search(q, limit=limit)
            for r in res:
                out.append(r["term"])
        return out

    def combined_suggest(self, lang: str, query: str, limit: int = 10) -> List[str]:
        # prefix -> fuzzy -> synonyms
        out = []
        seen = set()
        prefix = self.prefix_suggest(lang, query, limit)
        fuzzy = self.fuzzy_suggest(lang, query, maxdist=1, limit=limit)
        syn = get_synonyms(query)
        for lst in (prefix, fuzzy, syn):
            for item in lst:
                if item not in seen:
                    seen.add(item)
                    out.append(item)
                    if len(out) >= limit:
                        return out
        return out
